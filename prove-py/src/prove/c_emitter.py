"""Generate C source code from a checked Prove Module + SymbolTable."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prove._emit_calls import CallEmitterMixin
from prove._emit_exprs import ExprEmitterMixin
from prove._emit_stmts import StmtEmitterMixin
from prove._emit_types import TypeEmitterMixin
from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FloatLit,
    ForeignFunction,
    FunctionDef,
    IdentifierExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LookupAccessExpr,
    LookupTypeDef,
    MainDef,
    MatchExpr,
    Module,
    ModuleDecl,
    PathLit,
    PipeExpr,
    RawStringLit,
    RegexLit,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    VarDecl,
)
from prove.c_types import mangle_name, map_type, safe_c_name
from prove.errors import Diagnostic, Severity
from prove.optimizer import EscapeInfo, MemoizationInfo
from prove.symbols import SymbolTable
from prove.types import (
    BOOLEAN,
    DECIMAL,
    ERROR_TY,
    FLOAT,
    HOF_BUILTINS,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    StructType,
    Type,
    resolve_type_vars,
    substitute_type_vars,
)


class CEmitter(
    TypeEmitterMixin,
    StmtEmitterMixin,
    ExprEmitterMixin,
    CallEmitterMixin,
):
    """Emit C source from a type-checked Prove module."""

    # Known foreign library → C header mapping
    _FOREIGN_HEADERS: dict[str, str] = {
        "libm": "math.h",
        "libpthread": "pthread.h",
        "libdl": "dlfcn.h",
        "librt": "time.h",
        "libpython3": "Python.h",
        "libjvm": "jni.h",
    }

    def __init__(
        self,
        module: Module,
        symbols: SymbolTable,
        memo_info: "MemoizationInfo | None" = None,
        escape_info: "EscapeInfo | None" = None,  # noqa: E501
        *,
        optimize: bool = False,
    ) -> None:
        self._module = module
        self._symbols = symbols
        self._memo_info = memo_info
        self._escape_info = escape_info
        self._release_mode = optimize
        self._out: list[str] = []
        self._indent = 0
        self._tmp_counter = 0
        self._lambdas: list[str] = []  # hoisted lambda definitions
        self._locals: dict[str, Type] = {}  # local var -> type for inference
        self._needed_headers: set[str] = set()
        self._current_func_return: Type = UNIT
        self._current_func: FunctionDef | None = None
        self._in_main = False
        self._in_tail_loop = False
        self._in_region_scope = False
        self._in_return_position = False
        self._in_streams_loop = False
        self._in_listens_loop = False
        self._in_renders_loop = False
        self._foreign_names: set[str] = set()
        self._foreign_fns: list[ForeignFunction] = []
        self._foreign_libs: set[str] = set()
        self._current_requires: list[Expr] = []
        self._lookup_tables: dict[str, LookupTypeDef] = {}
        self._store_lookup_types: set[str] = set()
        self._dispatch_vars: dict[str, tuple[str, object]] = {}  # var -> (table_name, key_expr)
        self._store_var_types: dict[str, str] = {}  # var_name → lookup type name
        self._record_to_value: set[str] = set()  # record names needing Value converters
        self._expected_emit_type: Type | None = None
        self.diagnostics: list[Diagnostic] = []  # for comptime errors
        self.comptime_dependencies: set["Path"] = set()  # files read by comptime
        self._string_literal_cache: dict[str, str] = {}  # escaped literal → tmp var name
        self._in_hof_inline = False  # True when emitting inline HOF loop body
        self._fused_reduce_results: list[str] = []  # accum vars from multi-reduce
        self._fused_object_cache: tuple[str, str] | None = None  # type: ignore[assignment]  # (param, var) for CSE
        self._used_names: set[str] = set()  # collision tracking for _named_tmp()
        # Row-polymorphism monomorphisation state
        self._struct_templates: dict[tuple[str, str, int], FunctionDef] = {}
        self._struct_specialisations: dict[tuple, str] = {}
        self._struct_specialisation_queue: list[tuple[FunctionDef, list[Type]]] = []
        self._lambda_captures: dict[int, list[str]] = {}
        # Module name for namespaced mangling (user modules only, not stdlib)
        self._module_name: str | None = None
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                from prove.stdlib_loader import is_stdlib_module

                if not is_stdlib_module(decl.name) and decl.name.lower() != "main":
                    self._module_name = decl.name.lower()
                break
        self._collect_foreign_info()

    def _sig_module(self, sig) -> str | None:
        """Return module name for mangling, or None for stdlib/Main modules."""
        if not sig.module:
            return None
        from prove.stdlib_loader import is_stdlib_module

        # Stdlib modules are compiled without module prefix
        if is_stdlib_module(sig.module) or is_stdlib_module(sig.module.capitalize()):
            return None
        if sig.module == "main":
            return None
        return sig.module

    def _collect_foreign_info(self) -> None:
        """Scan module for foreign blocks and collect function names + libraries."""
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    self._foreign_libs.add(fb.library)
                    for ff in fb.functions:
                        self._foreign_names.add(ff.name)
                        self._foreign_fns.append(ff)
                for td in decl.types:
                    if isinstance(td.body, LookupTypeDef):
                        self._lookup_tables[td.name] = td.body
                        if td.body.is_store_backed:
                            self._store_lookup_types.add(td.name)

    def _all_type_defs(self) -> list[TypeDef]:
        """Collect all TypeDef nodes from ModuleDecl blocks."""
        result: list[TypeDef] = []
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                result.extend(decl.types)
        return result

    def _all_function_defs(self) -> list[FunctionDef]:
        """Collect all FunctionDef nodes from top-level and ModuleDecl body."""
        result: list[FunctionDef] = []
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                result.append(decl)
            elif isinstance(decl, ModuleDecl):
                for bd in decl.body:
                    if isinstance(bd, FunctionDef):
                        result.append(bd)
        return result

    # ── Public API ─────────────────────────────────────────────

    def emit(self) -> str:
        """Generate the complete C source for the module."""
        # Collect what we need first (dry run for headers)
        self._collect_needed_headers()

        # Emit includes
        self._emit_includes()
        self._emit_foreign_extern_decls()
        self._line("")

        # Forward declarations for types
        self._emit_type_forwards()

        # Type definitions
        for td in self._all_type_defs():
            self._emit_type_def(td)

        # Record-to-Value converters (after type defs, before functions)
        self._emit_record_to_value_converters()

        # Memoization tables for pure functions
        self._emit_memo_tables()

        # Module-level constants
        self._emit_constants()

        # Forward declarations for user functions
        self._emit_function_forwards()

        # Forward declarations for imported local functions
        self._emit_imported_function_forwards()

        # Hoisted lambdas will be inserted here (placeholder position)
        lambda_pos = len(self._out)

        # Function definitions
        for fd in self._all_function_defs():
            self._emit_function(fd)

        # Emit monomorphised Struct specialisations
        self._drain_struct_specialisations()

        # Main (may be top-level or inside a ModuleDecl)
        for decl in self._module.declarations:
            if isinstance(decl, MainDef):
                self._emit_main(decl)
                break
            elif isinstance(decl, ModuleDecl):
                for item in decl.body:
                    if isinstance(item, MainDef):
                        self._emit_main(item)
                        break

        # Insert hoisted lambdas before functions
        if self._lambdas:
            for lam in reversed(self._lambdas):
                self._out.insert(lambda_pos, lam)

        # Insert any headers discovered during body emission
        late_headers = sorted(self._needed_headers - self._emitted_headers)
        if late_headers:
            for i, h in enumerate(late_headers):
                self._out.insert(self._include_insert_pos + i, f'#include "{h}"')

        return "\n".join(self._out) + "\n"

    # ── Header collection ──────────────────────────────────────

    # Stdlib module name → C runtime header
    _STDLIB_HEADERS: dict[str, str] = {
        "Character": "prove_character.h",
        "Text": "prove_text.h",
        "Table": "prove_table.h",
        "System": "prove_input_output.h",
        "IO": "prove_input_output.h",
        "Parse": "prove_parse.h",
        "Math": "prove_math.h",
        "Convert": "prove_convert.h",
        "Types": "prove_convert.h",
        "List": "prove_list_ops.h",
        "Sequence": "prove_list_ops.h",
        "Array": "prove_array.h",
        "Format": "prove_format.h",
        "Path": "prove_path.h",
        "Error": "prove_error.h",
        "Pattern": "prove_pattern.h",
        "Random": "prove_random.h",
        "Time": "prove_time.h",
        "Bytes": "prove_bytes.h",
        "Hash": "prove_hash_crypto.h",
        "Log": "prove_input_output.h",
        "Network": "prove_network.h",
        "Store": "prove_store.h",
        "Language": "prove_language.h",
    }

    def _module_uses_strings(self) -> bool:
        """Return True if the module uses strings in any function signature or literal."""
        from prove.ast_nodes import (
            Assignment,
        )

        _STRING_NODES = (
            StringLit,
            StringInterp,
            TripleStringLit,
            PathLit,
            RawStringLit,
            RegexLit,
        )

        # Check function signatures for String types
        for (_verb, _name), sigs in self._symbols.all_functions().items():
            for sig in sigs:
                for pt in sig.param_types:
                    ct = map_type(pt)
                    if ct.header == "prove_string.h":
                        return True
                ct = map_type(sig.return_type)
                if ct.header == "prove_string.h":
                    return True

        # Walk declarations for string literal nodes
        def _has_string_node(expr: object) -> bool:
            if isinstance(expr, _STRING_NODES):
                return True
            if isinstance(expr, BinaryExpr):
                return _has_string_node(expr.left) or _has_string_node(expr.right)
            if isinstance(expr, CallExpr):
                return any(_has_string_node(a) for a in expr.args)
            if isinstance(expr, PipeExpr):
                return _has_string_node(expr.left) or _has_string_node(expr.right)
            if isinstance(expr, MatchExpr):
                if expr.subject and _has_string_node(expr.subject):
                    return True
                return any(any(_has_string_stmt(s) for s in arm.body) for arm in expr.arms)
            if isinstance(expr, FailPropExpr):
                return _has_string_node(expr.expr)
            if isinstance(expr, UnaryExpr):
                return _has_string_node(expr.operand)
            if isinstance(expr, IndexExpr):
                return _has_string_node(expr.obj) or _has_string_node(expr.index)
            if isinstance(expr, FieldExpr):
                return _has_string_node(expr.obj)
            if isinstance(expr, ListLiteral):
                return any(_has_string_node(e) for e in expr.elements)
            return False

        def _has_string_stmt(stmt: object) -> bool:
            if isinstance(stmt, VarDecl):
                return _has_string_node(stmt.value)
            if isinstance(stmt, ExprStmt):
                return _has_string_node(stmt.expr)
            if isinstance(stmt, Assignment):
                return _has_string_node(stmt.value)
            if isinstance(stmt, MatchExpr):
                return _has_string_node(stmt)
            return False

        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                if any(_has_string_stmt(s) for s in decl.body):
                    return True
            elif isinstance(decl, MainDef):
                if any(_has_string_stmt(s) for s in decl.body):
                    return True
            elif isinstance(decl, ModuleDecl):
                for bd in decl.body:
                    if isinstance(bd, FunctionDef):
                        if any(_has_string_stmt(s) for s in bd.body):
                            return True
                # Check constants for string values
                for const in decl.constants:
                    if isinstance(const.value, _STRING_NODES):
                        return True

        return False

    def _collect_needed_headers(self) -> None:
        """Pre-scan to determine which runtime headers are needed."""
        # Always include the base runtime
        self._needed_headers.add("prove_runtime.h")

        # String header: only when strings are actually used
        has_main = False
        for d in self._module.declarations:
            if isinstance(d, MainDef):
                has_main = True
                break
            if isinstance(d, ModuleDecl):
                for item in d.body:
                    if isinstance(item, MainDef):
                        has_main = True
                        break
                if has_main:
                    break
        if has_main or self._module_uses_strings():
            self._needed_headers.add("prove_string.h")

        # IO header: only when main exists (prove_io_init_args) or System imported
        if has_main:
            self._needed_headers.add("prove_input_output.h")

        # Scan function signatures and types for what we need
        for (_verb, _name), sigs in self._symbols.all_functions().items():
            for sig in sigs:
                for pt in sig.param_types:
                    ct = map_type(pt)
                    if ct.header:
                        self._needed_headers.add(ct.header)
                ct = map_type(sig.return_type)
                if ct.header:
                    self._needed_headers.add(ct.header)

        # Single pass over declarations for imports, lookup tables, async verbs, and HOF
        found_hof = False
        found_coro = False
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for imp in decl.imports:
                    header = self._STDLIB_HEADERS.get(imp.module)
                    if header:
                        self._needed_headers.add(header)
                for td in decl.types:
                    if isinstance(td.body, LookupTypeDef) and td.body.is_binary:
                        self._needed_headers.add("prove_lookup.h")
                if not found_coro:
                    for inner in decl.body:
                        if isinstance(inner, FunctionDef) and inner.verb in (
                            "detached",
                            "attached",
                            "listens",
                            "renders",
                        ):
                            self._needed_headers.add("prove_coro.h")
                            found_coro = True
                            break
            if isinstance(decl, (FunctionDef, MainDef)):
                if not found_hof and self._stmts_use_hof(decl.body):
                    self._needed_headers.add("prove_hof.h")
                    found_hof = True
            if isinstance(decl, FunctionDef):
                if not found_coro and decl.verb in ("detached", "attached", "listens", "renders"):
                    self._needed_headers.add("prove_coro.h")
                    found_coro = True
                if decl.verb == "renders":
                    self._needed_headers.add("prove_terminal.h")
                    self._needed_headers.add("prove_event.h")

    @staticmethod
    def _expr_uses_hof(expr: Expr) -> bool:
        """Check if an expression contains HOF builtin calls."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr) and expr.func.name in HOF_BUILTINS:
                return True
            return any(CEmitter._expr_uses_hof(a) for a in expr.args)
        if isinstance(expr, BinaryExpr):
            return CEmitter._expr_uses_hof(expr.left) or CEmitter._expr_uses_hof(expr.right)
        if isinstance(expr, PipeExpr):
            return CEmitter._expr_uses_hof(expr.left) or CEmitter._expr_uses_hof(expr.right)
        return False

    @staticmethod
    def _stmts_use_hof(stmts: list) -> bool:
        """Check if any statement in a list uses HOF builtins."""
        for s in stmts:
            if isinstance(s, ExprStmt) and CEmitter._expr_uses_hof(s.expr):
                return True
            if isinstance(s, VarDecl) and CEmitter._expr_uses_hof(s.value):
                return True
        return False

    # ── Output helpers ─────────────────────────────────────────

    def _line(self, text: str) -> None:
        if text:
            self._out.append("    " * self._indent + text)
        else:
            self._out.append("")

    def _tmp(self) -> str:
        self._tmp_counter += 1
        return f"_tmp{self._tmp_counter}"

    def _named_tmp(self, hint: str) -> str:
        """Generate a readable temp name from hint, avoiding collisions."""
        if hint not in self._used_names and hint not in self._locals:
            self._used_names.add(hint)
            return hint
        n = 2
        while f"{hint}{n}" in self._used_names or f"{hint}{n}" in self._locals:
            n += 1
        name = f"{hint}{n}"
        self._used_names.add(name)
        return name

    def _in_function_with_escape_info(self) -> bool:
        """Check if we're inside a function with escape analysis info."""
        return self._escape_info is not None and self._current_func is not None

    def _get_current_function_name(self) -> str | None:
        """Get the name of the current function being emitted."""
        if isinstance(self._current_func, FunctionDef):
            return self._current_func.name
        return None

    def _can_elide_retain(self, var_name: str) -> bool:
        """True if retain/release for var_name can be skipped in release mode."""
        if not self._release_mode:
            return False
        if self._escape_info is None:
            return False
        func_name = self._get_current_function_name()
        if func_name is None:
            return False
        return not self._escape_info.escapes(func_name, var_name)

    def _use_region_allocation(self, var_name: str | None = None) -> bool:
        """Check if we should use region allocation for this allocation.

        If var_name is provided, check if that specific variable escapes.
        Otherwise, conservatively use region allocation for intermediate values.
        """
        if self._in_return_position:
            return False

        if not self._in_function_with_escape_info():
            return False

        func_name = self._get_current_function_name()
        if func_name is None:
            return False

        # If we know the variable name, check if it escapes
        if var_name is not None:
            if self._escape_info.escapes(func_name, var_name):
                return False  # Escaping - use malloc

        # For now, use region allocation for everything inside functions
        # This is safe because:
        # - Return values are copied before region exit
        # - The global region persists across function calls
        return True

    def _get_region_ptr(self) -> str:
        """Get the region pointer to use for allocations."""
        return "prove_global_region()"

    def _needs_region_scope(self, fd: FunctionDef) -> bool:
        """Check if function body contains nodes that trigger region allocation.

        Region allocation (prove_string_*_region, prove_list_new_region) is only
        emitted for string/list literals when _use_region_allocation() returns True.
        If the body has none, the prove_region_enter/exit pair is pure overhead
        (a 4096-byte malloc + free per call).
        """
        from prove.ast_nodes import (
            Assignment,
            AsyncCallExpr,
            CommentStmt,
            FieldAssignment,
            TailContinue,
            TailLoop,
            ValidExpr,
            WhileLoop,
        )

        _REGION_NODES = (
            StringLit,
            TripleStringLit,
            RawStringLit,
            PathLit,
            RegexLit,
            StringInterp,
            ListLiteral,
        )

        def _expr_alloc(expr: Any) -> bool:
            if isinstance(expr, _REGION_NODES):
                return True
            if isinstance(expr, BinaryExpr):
                return _expr_alloc(expr.left) or _expr_alloc(expr.right)
            if isinstance(expr, UnaryExpr):
                return _expr_alloc(expr.operand)
            if isinstance(expr, CallExpr):
                return _expr_alloc(expr.func) or any(_expr_alloc(a) for a in expr.args)
            if isinstance(expr, PipeExpr):
                return _expr_alloc(expr.left) or _expr_alloc(expr.right)
            if isinstance(expr, FieldExpr):
                return _expr_alloc(expr.obj)
            if isinstance(expr, IndexExpr):
                return _expr_alloc(expr.obj) or _expr_alloc(expr.index)
            if isinstance(expr, MatchExpr):
                if _expr_alloc(expr.subject):
                    return True
                return any(_expr_alloc(arm.body) for arm in expr.arms)
            if isinstance(expr, FailPropExpr):
                return _expr_alloc(expr.expr)
            if isinstance(expr, ValidExpr):
                return expr.args is not None and any(_expr_alloc(a) for a in expr.args)
            if isinstance(expr, ComptimeExpr):
                return any(_stmt_alloc(s) for s in expr.body)
            if isinstance(expr, LambdaExpr):
                return any(_stmt_alloc(s) for s in expr.body)
            if isinstance(expr, AsyncCallExpr):
                return _expr_alloc(expr.expr)
            return False

        def _stmt_alloc(stmt: Any) -> bool:
            if isinstance(stmt, VarDecl):
                return _expr_alloc(stmt.value)
            if isinstance(stmt, Assignment):
                return _expr_alloc(stmt.value)
            if isinstance(stmt, FieldAssignment):
                return _expr_alloc(stmt.value)
            if isinstance(stmt, ExprStmt):
                return _expr_alloc(stmt.expr)
            if isinstance(stmt, TailLoop):
                return any(_stmt_alloc(s) for s in stmt.body)
            if isinstance(stmt, TailContinue):
                return any(_expr_alloc(e) for _, e in stmt.assignments)
            if isinstance(stmt, WhileLoop):
                return _expr_alloc(stmt.break_cond) or any(_stmt_alloc(s) for s in stmt.body)
            if isinstance(stmt, CommentStmt):
                return False
            if isinstance(stmt, MatchExpr):
                return _expr_alloc(stmt)
            # Conservative default
            return True

        return any(_stmt_alloc(s) for s in fd.body)

    # ── Includes ───────────────────────────────────────────────

    def _emit_includes(self) -> None:
        self._line("#include <stdint.h>")
        self._line("#include <stdbool.h>")
        self._line("#include <stdlib.h>")
        self._line("#include <stdio.h>")
        self._line("#include <string.h>")
        self._line('#include "prove_region.h"')
        # Foreign library headers
        for lib in sorted(self._foreign_libs):
            header = self._FOREIGN_HEADERS.get(lib)
            if header:
                self._line(f"#include <{header}>")
        self._include_insert_pos = len(self._out)
        for h in sorted(self._needed_headers):
            self._line(f'#include "{h}"')
        self._emitted_headers = set(self._needed_headers)

    def _emit_foreign_extern_decls(self) -> None:
        """Emit extern C declarations for foreign (FFI) functions."""
        if not self._foreign_fns:
            return
        self._line("")
        self._line("/* Foreign function declarations */")
        for ff in self._foreign_fns:
            sig = self._symbols.resolve_function_any(ff.name, arity=len(ff.params))
            if sig is None:
                continue
            ret_c = map_type(sig.return_type).decl
            if sig.param_types:
                params_c = ", ".join(map_type(pt).decl for pt in sig.param_types)
            else:
                params_c = "void"
            self._line(f"extern {ret_c} {ff.name}({params_c});")

    # ── Memoization ────────────────────────────────────────────

    def _emit_memo_tables(self) -> None:
        """Emit memoization tables for pure functions."""
        if not self._memo_info:
            return
        candidates = self._memo_info.get_candidates()
        if not candidates:
            return

        self._line("/* Memoization tables for pure functions */")
        self._line("")

        for cand in candidates:
            mod_prefix = f"{self._module_name}_" if self._module_name else ""
            table_name = f"_memo_{mod_prefix}{cand.verb}_{cand.name}"
            table_size = 32

            self._line(f"/* {table_name}: {cand.param_count} params, {cand.body_size} stmts */")
            self._line(f"typedef struct {table_name}_entry {{")
            self._indent += 1
            self._line("uint64_t key;")
            sig = self._symbols.resolve_function(cand.verb, cand.name, cand.param_count)
            ret_type = sig.return_type if sig else None
            if ret_type:
                if isinstance(ret_type, PrimitiveType) and ret_type.name == "Integer":
                    self._line("int64_t value;")
                elif isinstance(ret_type, PrimitiveType) and ret_type.name == "Boolean":
                    self._line("bool value;")
                else:
                    self._line("void* value;")
            else:
                self._line("void* value;")
            self._line("bool valid;")
            self._indent -= 1
            self._line(f"}} {table_name}_entry;")
            self._line(f"static {table_name}_entry {table_name}[{table_size}] = {{0}};")
            self._line("")

    def _get_memo_key(self, cand: Any, args: list[str]) -> str:
        """Generate hash key computation from arguments."""
        if not args:
            return "0"
        key_expr = f"(uint64_t)({args[0]})"
        for arg in args[1:]:
            key_expr = f"(({key_expr}) * 31 + (uint64_t)({arg}))"
        return key_expr

    # ── Constants ──────────────────────────────────────────────

    def _emit_constants(self) -> None:
        """Emit #define macros for module-level constants."""
        any_emitted = False
        for decl in self._module.declarations:
            if not isinstance(decl, ModuleDecl):
                continue
            for const in decl.constants:
                name = const.name.upper()
                val = const.value
                if isinstance(val, StringLit):
                    escaped = self._escape_c_string(val.value)
                    self._line(f'#define {name} prove_string_from_cstr("{escaped}")')
                elif isinstance(val, IntegerLit):
                    self._line(f"#define {name} {val.value}L")
                elif isinstance(val, BooleanLit):
                    self._line(f"#define {name} {'true' if val.value else 'false'}")
                elif isinstance(val, DecimalLit):
                    self._line(f"#define {name} {val.value}")
                elif isinstance(val, FloatLit):
                    # Strip the 'f' suffix for C code
                    self._line(f"#define {name} {val.value[:-1]}")
                elif isinstance(val, PathLit):
                    escaped = self._escape_c_string(val.value)
                    self._line(f'#define {name} prove_string_from_cstr("{escaped}")')
                elif isinstance(val, ComptimeExpr):
                    result = self._eval_comptime(const, val)
                    if result is not None:
                        c_code = self._comptime_result_to_c(result)
                        self._line(f"#define {name} {c_code}")
                    else:
                        self._line(f"/* comptime evaluation failed for {name} */")
                else:
                    self._line(f"#define {name} {self._emit_expr(val)}")
                any_emitted = True

            # Emit #defines for imported constants (stdlib and local)
            from prove.stdlib_loader import load_stdlib_constants

            for imp in decl.imports:
                # Check for constant imports (explicit verb or ALL_CAPS names)
                const_items = [
                    item
                    for item in imp.items
                    if item.verb == "constants"
                    or (
                        item.verb is None
                        and len(item.name) >= 2
                        and all(c.isupper() or c.isdigit() or c == "_" for c in item.name)
                    )
                ]
                if not const_items:
                    continue

                # Try stdlib constants first
                stdlib_consts = load_stdlib_constants(imp.module)
                consts_by_name = {c.name: c for c in stdlib_consts}

                for item in const_items:
                    stdlib_const = consts_by_name.get(item.name)
                    if stdlib_const is not None:
                        escaped = self._escape_c_string(stdlib_const.raw_value)
                        self._line(f'#define {item.name} prove_string_from_cstr("{escaped}")')
                        any_emitted = True
                        continue

                    # Try local module constants
                    local_const = self._resolve_local_constant(imp.module, item.name)
                    if local_const is not None:
                        self._line(f"#define {item.name} {local_const}")
                        any_emitted = True

        if any_emitted:
            self._line("")

    def _resolve_local_constant(self, module_name: str, const_name: str) -> str | None:
        """Resolve a constant from a sibling local module, returning C code."""
        from pathlib import Path

        source_file = self._module.span.file
        if not source_file:
            return None
        src_dir = Path(source_file).parent

        # Find the sibling module file (case-insensitive match)
        target = None
        for prv in src_dir.glob("*.prv"):
            if prv.stem.lower() == module_name.lower():
                target = prv
                break
        if target is None:
            return None

        try:
            from prove.lexer import Lexer as _Lexer
            from prove.parser import Parser as _Parser

            tokens = _Lexer(target.read_text(), str(target)).lex()
            mod = _Parser(tokens, str(target)).parse()
        except Exception:
            return None

        for decl in mod.declarations:
            if not isinstance(decl, ModuleDecl):
                continue
            for cd in decl.constants:
                if cd.name != const_name:
                    continue
                val = cd.value
                if isinstance(val, StringLit):
                    return f'prove_string_from_cstr("{self._escape_c_string(val.value)}")'
                if isinstance(val, IntegerLit):
                    return f"{val.value}L"
                if isinstance(val, BooleanLit):
                    return "true" if val.value else "false"
                if isinstance(val, ComptimeExpr):
                    result = self._eval_comptime(cd, val)
                    if result is not None:
                        return self._comptime_result_to_c(result)
                return None
        return None

    def _eval_comptime(self, const: ConstantDef, expr: ComptimeExpr) -> object | None:
        """Evaluate a comptime expression and return the result."""
        from pathlib import Path

        from prove.interpreter import ComptimeInterpreter

        source_dir = Path(self._module.span.file).parent if self._module.span.file else Path(".")
        # Collect user-defined pure functions for comptime evaluation
        func_defs: dict[str, "FunctionDef"] = {}
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                func_defs[decl.name] = decl
            elif isinstance(decl, ModuleDecl):
                for d in decl.body:
                    if isinstance(d, FunctionDef):
                        func_defs[d.name] = d
        interpreter = ComptimeInterpreter(module_source_dir=source_dir, function_defs=func_defs)
        try:
            result = interpreter.evaluate(expr)
            self.comptime_dependencies.update(result.dependencies)
            return result.value
        except Exception as e:
            diag = Diagnostic(
                severity=Severity.ERROR,
                code="E417",
                message=f"comptime evaluation failed: {type(e).__name__}: {e}",
                labels=[],
            )
            self.diagnostics.append(diag)
            return None

    def _comptime_result_to_c(self, value: object) -> str:
        """Convert a Python value to C code."""
        if value is None:
            return "((void*)0)"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return f"{value}L"
        if isinstance(value, float):
            return str(value)
        if isinstance(value, str):
            escaped = self._escape_c_string(value)
            return f'prove_string_from_cstr("{escaped}")'
        if isinstance(value, list):
            if not value:
                return "prove_list_empty()"
            elems = ", ".join(self._comptime_result_to_c(v) for v in value)
            return f"prove_list_from_array({elems})"
        return "((void*)0)"

    # ── Function forwards ──────────────────────────────────────

    def _emit_imported_function_forwards(self) -> None:
        """Emit forward declarations for functions imported from local modules."""
        from prove.stdlib_loader import is_stdlib_module

        # Collect local function names defined in THIS module to avoid duplicates
        local_func_names: set[tuple[str | None, str]] = set()
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef) and not decl.binary:
                local_func_names.add((decl.verb, decl.name))

        any_emitted = False
        seen: set[str] = set()  # track by mangled name to avoid duplicates

        for decl in self._module.declarations:
            if not isinstance(decl, ModuleDecl):
                continue
            for imp in decl.imports:
                # Skip stdlib modules — they use C runtime functions
                if is_stdlib_module(imp.module):
                    continue
                for item in imp.items:
                    # Skip type imports
                    is_type_import = item.verb == "types" or (
                        item.verb is None and item.name[:1].isupper()
                    )
                    if is_type_import:
                        continue
                    # Find all verb overloads for this imported function
                    for (verb, fname), sigs in self._symbols.all_functions().items():
                        if fname != item.name:
                            continue
                        if (verb, fname) in local_func_names:
                            continue
                        for sig in sigs:
                            if sig.name in self._foreign_names:
                                continue
                            mangled = mangle_name(
                                sig.verb, sig.name, sig.param_types, module=self._sig_module(sig)
                            )
                            if mangled in seen:
                                continue
                            seen.add(mangled)
                            ret_type = BOOLEAN if sig.verb == "validates" else sig.return_type
                            ret_ct = map_type(ret_type)
                            ret_decl = ret_ct.decl
                            if sig.can_fail:
                                ret_decl = "Prove_Result"
                            params: list[str] = []
                            for pname, pt in zip(sig.param_names, sig.param_types):
                                ct = map_type(pt)
                                params.append(f"{ct.decl} {pname}")
                            param_str = ", ".join(params) if params else "void"
                            self._line(f"{ret_decl} {mangled}({param_str});")
                            any_emitted = True
        if any_emitted:
            self._line("")

    def _emit_function_forwards(self) -> None:
        """Emit forward declarations for all user-defined functions."""
        any_emitted = False
        for decl in self._all_function_defs():
            if decl.binary:
                continue
            # Struct-polymorphic templates: skip forward decl
            if self._is_struct_polymorphic(decl):
                continue
            # Streams verb: void return (or Prove_Result if failable), no coroutine
            if decl.verb == "streams":
                sig = self._symbols.resolve_function(decl.verb, decl.name, len(decl.params))
                if not sig:
                    continue
                mangled = mangle_name(
                    decl.verb, decl.name, sig.param_types, module=self._module_name
                )
                params: list[str] = []
                for p, pt in zip(decl.params, sig.param_types):
                    ct = map_type(pt)
                    params.append(f"{ct.decl} {safe_c_name(p.name)}")
                param_str = ", ".join(params) if params else "void"
                ret_decl = "Prove_Result" if sig.can_fail else "void"
                self._line(f"{ret_decl} {mangled}({param_str});")
                any_emitted = True
                continue
            # Async verbs get special forward declarations
            if decl.verb in ("detached", "attached", "listens", "renders"):
                sig = self._symbols.resolve_function(decl.verb, decl.name, len(decl.params))
                if not sig:
                    continue
                mangled = mangle_name(
                    decl.verb, decl.name, sig.param_types, module=self._module_name
                )
                params: list[str] = []
                for p, pt in zip(decl.params, sig.param_types):
                    ct = map_type(pt)
                    params.append(f"{ct.decl} {safe_c_name(p.name)}")
                if decl.verb == "attached":
                    ret_ct = map_type(sig.return_type)
                    ret_decl = ret_ct.decl
                    param_str = (
                        ", ".join(["Prove_Coro *_caller"] + params)
                        if params
                        else "Prove_Coro *_caller"
                    )  # noqa: E501
                    self._line(f"{ret_decl} {mangled}({param_str});")
                elif decl.verb in ("listens", "renders"):
                    param_str = ", ".join(params) if params else "void"
                    self._line(f"void {mangled}({param_str});")
                else:
                    param_str = ", ".join(params) if params else "void"
                    self._line(f"void {mangled}({param_str});")
                any_emitted = True
                continue
            sig = self._symbols.resolve_function(
                decl.verb,
                decl.name,
                len(decl.params),
            )
            if not sig:
                continue
            ret_type = BOOLEAN if decl.verb == "validates" else sig.return_type
            ret_ct = map_type(ret_type)
            ret_decl = ret_ct.decl
            if decl.can_fail:
                ret_decl = "Prove_Result"
            mangled = mangle_name(
                decl.verb,
                decl.name,
                sig.param_types,
                module=self._module_name,
            )
            params = []
            for p, pt in zip(decl.params, sig.param_types):
                ct = map_type(pt)
                params.append(f"{ct.decl} {safe_c_name(p.name)}")
            param_str = ", ".join(params) if params else "void"
            self._line(f"{ret_decl} {mangled}({param_str});")
            any_emitted = True
        if any_emitted:
            self._line("")

    # ── Function emission ──────────────────────────────────────

    def _is_struct_polymorphic(self, fd: FunctionDef) -> bool:
        """Check if a function has any Struct-typed parameters."""
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if not sig:
            return False
        return any(isinstance(pt, StructType) for pt in sig.param_types)

    def _emit_function(self, fd: FunctionDef) -> None:
        # Struct-polymorphic functions are templates — skip direct emission
        if self._is_struct_polymorphic(fd):
            key = (fd.verb, fd.name, len(fd.params))
            self._struct_templates[key] = fd
            return

        # Binary functions are C-backed — no Prove body to emit
        if fd.binary:
            return

        # Renders verb: event-driven render loop
        if fd.verb == "renders":
            self._emit_renders_function(fd)
            return

        # Async verbs get specialized emission
        if fd.verb in ("detached", "attached", "listens"):
            self._emit_async_function(fd)
            return

        # Streams verb: blocking loop with match body
        if fd.verb == "streams":
            self._emit_streams_function(fd)
            return

        # Resolve types
        param_types: list[Type] = []
        for p in fd.params:
            sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
            if sig:
                idx = next((i for i, n in enumerate(sig.param_names) if n == p.name), None)
                if idx is not None and idx < len(sig.param_types):
                    param_types.append(sig.param_types[idx])
                    continue
            param_types.append(INTEGER)

        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        ret_type = sig.return_type if sig else UNIT
        # validates has implicit Boolean return
        if fd.verb == "validates":
            ret_type = BOOLEAN
        # Resolve PrimitiveType to actual type (e.g. User:[Mutable] → RecordType)
        ret_type = self._resolve_prim_type(ret_type)
        self._current_func_return = ret_type
        self._current_func = fd
        self._current_requires = fd.requires

        # Map to C types
        ret_ct = map_type(ret_type)
        ret_decl = ret_ct.decl

        # Any failable function returns Prove_Result in C
        if fd.can_fail:
            ret_decl = "Prove_Result"

        mangled = mangle_name(fd.verb, fd.name, param_types, module=self._module_name)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {safe_c_name(p.name)}")
        param_str = ", ".join(params) if params else "void"

        self._line(f"{ret_decl} {mangled}({param_str}) {{")
        self._indent += 1

        # Enter region for short-lived allocations (skip for pure numeric functions)
        if self._needs_region_scope(fd):
            self._line("prove_region_enter(prove_global_region());")
            self._in_region_scope = True
        else:
            self._in_region_scope = False

        # Reset locals
        self._locals.clear()
        self._used_names.clear()
        self._string_literal_cache.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        # Retain pointer params at entry — the epilogue releases all locals
        # including params, but recursive calls or stdlib functions that
        # return their input may also release them.  The entry retain
        # ensures the outer scope's reference stays alive.
        # Skip Verb/FunctionType params — function pointers, not heap objects.
        for p, pt in zip(fd.params, param_types):
            if isinstance(pt, PrimitiveType) and pt.name == "Verb":
                continue
            if isinstance(pt, FunctionType):
                continue
            ct = map_type(pt)
            if ct.is_pointer:
                self._line(f"prove_retain({p.name});")

        # Emit assume assertions at function entry
        for assume_expr in fd.assume:
            cond = self._emit_expr(assume_expr)
            self._line(f'if (!({cond})) prove_panic("assumption violated");')

        # Emit believe assertions (always present — believe is explicitly uncertain)
        for believe_expr in fd.believe:
            cond = self._emit_expr(believe_expr)
            self._line(f'if (!({cond})) prove_panic("believe violation");')

        # Check if explain block has structured conditions (when)
        has_explain_conditions = fd.explain is not None and any(
            e.condition is not None for e in fd.explain.entries
        )

        if has_explain_conditions:
            self._emit_explain_branches(fd, ret_type)
        else:
            # Emit body
            self._emit_body(fd.body, ret_type, is_failable=fd.can_fail)

        # Exit region (only if we entered one)
        if self._in_region_scope:
            self._line("prove_region_exit(prove_global_region());")
            self._in_region_scope = False
        self._indent -= 1
        self._line("}")
        self._line("")

    def _request_struct_specialisation(self, fd: FunctionDef, concrete_types: list[Type]) -> str:
        """Request a monomorphised copy of a Struct-polymorphic function.

        Returns the mangled name for the specialisation.
        """
        key = (fd.verb, fd.name, tuple(concrete_types))
        if key in self._struct_specialisations:
            return self._struct_specialisations[key]
        mangled = mangle_name(fd.verb, fd.name, concrete_types, module=self._module_name)
        self._struct_specialisations[key] = mangled
        self._struct_specialisation_queue.append((fd, concrete_types))
        return mangled

    def _emit_struct_specialisation(self, fd: FunctionDef, concrete_types: list[Type]) -> None:
        """Emit a monomorphised copy of a Struct-polymorphic function."""
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if not sig:
            return
        ret_type = sig.return_type
        if fd.verb == "validates":
            ret_type = BOOLEAN
        ret_type = self._resolve_prim_type(ret_type)
        self._current_func_return = ret_type
        self._current_func = fd
        self._current_requires = fd.requires

        ret_ct = map_type(ret_type)
        ret_decl = ret_ct.decl
        if fd.can_fail:
            ret_decl = "Prove_Result"

        mangled = mangle_name(fd.verb, fd.name, concrete_types, module=self._module_name)

        # Build params and forward declaration
        params: list[str] = []
        for p, pt in zip(fd.params, concrete_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {safe_c_name(p.name)}")
        param_str = ", ".join(params) if params else "void"

        # Forward declaration for the specialisation
        self._line(f"{ret_decl} {mangled}({param_str});")

        self._line(f"{ret_decl} {mangled}({param_str}) {{")
        self._indent += 1

        if self._needs_region_scope(fd):
            self._line("prove_region_enter(prove_global_region());")
            self._in_region_scope = True
        else:
            self._in_region_scope = False

        self._locals.clear()
        self._used_names.clear()
        self._string_literal_cache.clear()
        for p, pt in zip(fd.params, concrete_types):
            self._locals[p.name] = pt

        for p, pt in zip(fd.params, concrete_types):
            ct = map_type(pt)
            if ct.is_pointer:
                self._line(f"prove_retain({p.name});")

        for assume_expr in fd.assume:
            cond = self._emit_expr(assume_expr)
            self._line(f'if (!({cond})) prove_panic("assumption violated");')

        for believe_expr in fd.believe:
            cond = self._emit_expr(believe_expr)
            self._line(f'if (!({cond})) prove_panic("believe violation");')

        has_explain_conditions = fd.explain is not None and any(
            e.condition is not None for e in fd.explain.entries
        )
        if has_explain_conditions:
            self._emit_explain_branches(fd, ret_type)
        else:
            self._emit_body(fd.body, ret_type, is_failable=fd.can_fail)

        if self._in_region_scope:
            self._line("prove_region_exit(prove_global_region());")
            self._in_region_scope = False
        self._indent -= 1
        self._line("}")
        self._line("")

    def _drain_struct_specialisations(self) -> None:
        """Emit all queued Struct specialisations (may queue more during emission)."""
        while self._struct_specialisation_queue:
            fd, concrete_types = self._struct_specialisation_queue.pop(0)
            self._emit_struct_specialisation(fd, concrete_types)

    def _emit_async_function(self, fd: FunctionDef) -> None:
        """Emit a detached/attached/listens async function."""
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if not sig:
            return
        param_types: list[type] = []
        for p in fd.params:
            s = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
            if s:
                idx = next((i for i, n in enumerate(s.param_names) if n == p.name), None)
                if idx is not None and idx < len(s.param_types):
                    param_types.append(s.param_types[idx])
                    continue
            from prove.types import INTEGER

            param_types.append(INTEGER)

        mangled = mangle_name(fd.verb, fd.name, param_types, module=self._module_name)
        args_struct = f"_{mangled}_args"
        body_fn = f"_{mangled}_body"

        # ── Arg struct ───────────────────────────────────────────
        self._line("typedef struct {")
        self._indent += 1
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            self._line(f"{ct.decl} {safe_c_name(p.name)};")
        self._indent -= 1
        self._line(f"}} {args_struct};")
        self._line("")

        # ── Coroutine body function ──────────────────────────────
        self._current_func = fd
        self._current_func_return = sig.return_type if sig else UNIT
        self._locals.clear()
        self._used_names.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt  # type: ignore[assignment]

        self._line(f"static void {body_fn}(Prove_Coro *_coro) {{")
        self._indent += 1
        self._line(f"{args_struct} *_a = ({args_struct} *)_coro->arg;")
        # Expose params as local variables
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            cn = safe_c_name(p.name)
            self._line(f"{ct.decl} {cn} = _a->{cn};")

        if fd.verb == "listens":
            self._emit_listens_body(fd, param_types)
        else:
            # detached / attached: emit body into coro
            ret_type = sig.return_type if sig else UNIT
            is_struct_return = (
                fd.verb == "attached"
                and ret_type is not UNIT
                and isinstance(ret_type, AlgebraicType)
            )
            for i, stmt in enumerate(fd.body):
                if is_struct_return and i == len(fd.body) - 1:
                    # Last statement: capture result and heap-allocate
                    e = self._stmt_expr(stmt)
                    if e is not None:
                        result_val = self._emit_expr(e)
                        ret_ct = map_type(ret_type)
                        self._line(f"{ret_ct.decl} _result_val = {result_val};")
                        self._line(f"{ret_ct.decl} *_result_ptr = malloc(sizeof({ret_ct.decl}));")
                        self._line("*_result_ptr = _result_val;")
                        self._line("_coro->result = _result_ptr;")
                    else:
                        self._emit_stmt(stmt)
                else:
                    self._emit_stmt(stmt)
        self._line("prove_coro_yield(_coro);")
        self._indent -= 1
        self._line("}")
        self._line("")

        # ── Public entry point ───────────────────────────────────
        if fd.verb == "detached":
            params_str = (
                ", ".join(f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types))
                or "void"
            )
            self._line(f"void {mangled}({params_str}) {{")
            self._indent += 1
            self._line(f"{args_struct} *_a = malloc(sizeof({args_struct}));")
            for p in fd.params:
                self._line(f"_a->{p.name} = {p.name};")
            self._line(f"Prove_Coro *_c = prove_coro_new({body_fn}, PROVE_CORO_STACK_DEFAULT);")
            self._line("prove_coro_start(_c, _a);")
            self._indent -= 1
            self._line("}")
            self._line("")

        elif fd.verb == "attached":
            ret_ct = map_type(sig.return_type) if sig else map_type(UNIT)
            ret_type = sig.return_type if sig else UNIT
            is_struct_return = isinstance(ret_type, AlgebraicType)
            caller_params = ["Prove_Coro *_caller"] + [
                f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types)
            ]
            params_str = ", ".join(caller_params)
            self._line(f"{ret_ct.decl} {mangled}({params_str}) {{")
            self._indent += 1
            self._line(f"{args_struct} *_a = malloc(sizeof({args_struct}));")
            for p in fd.params:
                self._line(f"_a->{p.name} = {p.name};")
            self._line(f"Prove_Coro *_c = prove_coro_new({body_fn}, PROVE_CORO_STACK_DEFAULT);")
            self._line("prove_coro_start(_c, _a);")
            self._line("while (!prove_coro_done(_c)) {")
            self._indent += 1
            self._line("prove_coro_yield(_caller);")
            self._line("prove_coro_resume(_c);")
            self._indent -= 1
            self._line("}")
            if is_struct_return:
                self._line(f"{ret_ct.decl} _result = *({ret_ct.decl}*)_c->result;")
                self._line(f"free(({ret_ct.decl}*)_c->result);")
            else:
                self._line(f"{ret_ct.decl} _result = ({ret_ct.decl})(intptr_t)_c->result;")
            self._line("prove_coro_free(_c);")
            self._line("return _result;")
            self._indent -= 1
            self._line("}")
            self._line("")

        elif fd.verb == "listens":
            # Listens manages its own coroutine — no _coro param needed
            params_list = [f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types)]
            params_str = ", ".join(params_list) if params_list else "void"
            self._line(f"void {mangled}({params_str}) {{")
            self._indent += 1
            self._line(f"{args_struct} *_a = malloc(sizeof({args_struct}));")
            for p in fd.params:
                self._line(f"_a->{p.name} = {p.name};")
            self._line(f"Prove_Coro *_c = prove_coro_new({body_fn}, PROVE_CORO_STACK_DEFAULT);")
            self._line("prove_coro_start(_c, _a);")
            self._line("while (!prove_coro_done(_c)) prove_coro_resume(_c);")
            self._line("prove_coro_free(_c);")
            self._indent -= 1
            self._line("}")
            self._line("")

    def _emit_streams_function(self, fd: FunctionDef) -> None:
        """Emit a streams verb function — blocking loop with match body."""
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if not sig:
            return

        param_types: list[Type] = []
        for p in fd.params:
            if sig:
                idx = next((i for i, n in enumerate(sig.param_names) if n == p.name), None)
                if idx is not None and idx < len(sig.param_types):
                    param_types.append(sig.param_types[idx])
                    continue
            param_types.append(INTEGER)

        ret_type = sig.return_type if sig else UNIT
        self._current_func_return = ret_type
        self._current_func = fd
        self._current_requires = fd.requires

        mangled = mangle_name(fd.verb, fd.name, param_types, module=self._module_name)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {safe_c_name(p.name)}")
        param_str = ", ".join(params) if params else "void"

        ret_decl = "Prove_Result" if sig.can_fail else "void"
        self._line(f"{ret_decl} {mangled}({param_str}) {{")
        self._indent += 1

        if sig.can_fail:
            self._line("Prove_Result _streams_err = prove_result_ok();")

        if self._needs_region_scope(fd):
            self._line("prove_region_enter(prove_global_region());")
            self._in_region_scope = True

        self._locals.clear()
        self._used_names.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        # Blocking loop — match body handles dispatch and exit
        self._line("while (1) {")
        self._indent += 1
        self._in_streams_loop = True
        for stmt in fd.body:
            self._emit_stmt(stmt)
        self._in_streams_loop = False
        self._indent -= 1
        self._line("}")
        self._line("_streams_exit:;")

        if self._in_region_scope:
            self._line("prove_region_exit(prove_global_region());")
            self._in_region_scope = False
        if sig.can_fail:
            self._line("return _streams_err;")
        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_listens_body(self, fd: FunctionDef, param_types: list) -> None:
        """Emit the listens dispatcher: iterate pre-started workers, match on results."""
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        event_type = sig.event_type if sig else None

        if fd.params:
            workers_param = fd.params[0].name
            # Iterate workers (pre-started coroutines in the list)
            self._line(f"for (int _i = 0; _i < {workers_param}->length; _i++) {{")
            self._indent += 1
            self._line(f"Prove_Coro *_child = (Prove_Coro*)prove_list_get({workers_param}, _i);")
            # Resume worker until done
            self._line("while (!prove_coro_done(_child)) {")
            self._indent += 1
            self._line("prove_coro_resume(_child);")
            self._line("prove_coro_yield(_coro);")
            self._indent -= 1
            self._line("}")
            # Extract result as the event type
            if event_type:
                ct = map_type(event_type)
                self._line(f"{ct.decl} _ev = *({ct.decl}*)_child->result;")
                self._line(f"free(({ct.decl}*)_child->result);")
                self._locals["_ev"] = event_type
            self._line("prove_coro_free(_child);")
            # Match dispatch on _ev
            self._in_listens_loop = True
            for stmt in fd.body:
                self._emit_stmt(stmt)
            self._in_listens_loop = False
            self._indent -= 1
            self._line("}")

        self._line("_listens_exit:;")

    def _emit_renders_function(self, fd: FunctionDef) -> None:
        """Emit a renders verb function — event-driven render loop.

        The renders function:
        1. Initializes state from state_init
        2. Creates worker coroutines from the List<Attached> parameter
        3. Enters a blocking event loop that dispatches events to the match body
        4. Workers (attached callbacks) feed events into the queue
        5. Exit arm breaks the loop
        """
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if not sig:
            return

        param_types: list[Type] = []
        for p in fd.params:
            if sig:
                idx = next((i for i, n in enumerate(sig.param_names) if n == p.name), None)
                if idx is not None and idx < len(sig.param_types):
                    param_types.append(sig.param_types[idx])
                    continue
            param_types.append(INTEGER)

        self._current_func = fd
        self._current_func_return = UNIT
        self._current_requires = fd.requires

        mangled = mangle_name(fd.verb, fd.name, param_types, module=self._module_name)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {safe_c_name(p.name)}")
        param_str = ", ".join(params) if params else "void"

        self._line(f"void {mangled}({param_str}) {{")
        self._indent += 1

        if self._needs_region_scope(fd):
            self._line("prove_region_enter(prove_global_region());")
            self._in_region_scope = True

        self._locals.clear()
        self._used_names.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        # Initialize the event queue
        self._line("Prove_EventNodeQueue *_eq = prove_event_queue_new();")

        # Initialize terminal backend
        self._line("prove_terminal_init(_eq);")

        event_type = sig.event_type if sig else None

        # Blocking event loop — receive events from queue, dispatch via match
        self._line("while (1) {")
        self._indent += 1
        self._line("Prove_EventNode *_node = prove_event_queue_recv(_eq, NULL);")
        self._line("if (!_node) break;")

        if event_type:
            ct = map_type(event_type)
            self._line(f"{ct.decl} _ev;")
            self._line("_ev.tag = _node->tag;")
            self._line("if (_node->payload) {")
            self._indent += 1
            self._line(f"_ev = *({ct.decl}*)_node->payload;")
            self._line("free(_node->payload);")
            self._indent -= 1
            self._line("} else {")
            self._indent += 1
            self._line("_ev.tag = _node->tag;")
            self._indent -= 1
            self._line("}")
            self._locals["_ev"] = event_type

        self._line("free(_node);")

        # Dispatch
        self._in_renders_loop = True
        for stmt in fd.body:
            self._emit_stmt(stmt)
        self._in_renders_loop = False
        self._indent -= 1
        self._line("}")
        self._line("_renders_exit:;")

        # Cleanup
        self._line("prove_terminal_cleanup();")
        self._line("prove_event_queue_free(_eq);")

        if self._in_region_scope:
            self._line("prove_region_exit(prove_global_region());")
            self._in_region_scope = False
        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_main(self, md: MainDef) -> None:
        self._current_func = md  # type: ignore[assignment]
        self._current_func_return = UNIT
        self._in_main = True
        self._locals.clear()
        self._used_names.clear()
        self._string_literal_cache.clear()
        self._current_requires = []

        self._line("int main(int argc, char **argv) {")
        self._indent += 1

        self._line("prove_runtime_init();")
        self._line("prove_io_init_args(argc, argv);")

        # Emit body statements
        for stmt in md.body:
            self._emit_stmt(stmt)

        self._line("")
        self._line("prove_runtime_cleanup();")
        self._line("return 0;")
        self._indent -= 1
        self._line("}")
        self._line("")
        self._in_main = False

    # ── Type resolution helpers ────────────────────────────────

    def _resolve_prim_type(self, ty: Type) -> Type:
        """Resolve PrimitiveType to its actual type if it's a user-defined name.

        Handles cases like User:[Mutable] being stored as PrimitiveType("User", ...)
        when it should be RecordType("User", ...).
        """
        if isinstance(ty, PrimitiveType):
            resolved = self._symbols.resolve_type(ty.name)
            if isinstance(resolved, (RecordType, AlgebraicType)):
                return resolved
        return ty

    # ── Type inference (lightweight) ───────────────────────────

    def _infer_expr_type(self, expr: Expr) -> Type:
        """Lightweight type inference mirroring the checker."""
        if isinstance(expr, IntegerLit):
            return INTEGER
        if isinstance(expr, DecimalLit):
            return DECIMAL
        if isinstance(expr, FloatLit):
            return FLOAT
        if isinstance(expr, (StringLit, TripleStringLit, StringInterp, PathLit, RegexLit)):
            return STRING
        if isinstance(expr, RawStringLit):
            return PrimitiveType("String", ((None, "Reg"),))
        if isinstance(expr, BooleanLit):
            return BOOLEAN
        if isinstance(expr, CharLit):
            return PrimitiveType("Character")

        if isinstance(expr, IdentifierExpr):
            # Check locals first
            if expr.name in self._locals:
                return self._locals[expr.name]
            sym = self._symbols.lookup(expr.name)
            if sym:
                return sym.resolved_type
            return ERROR_TY

        if isinstance(expr, TypeIdentifierExpr):
            resolved = self._symbols.resolve_type(expr.name)
            if resolved:
                return resolved
            return ERROR_TY

        if isinstance(expr, BinaryExpr):
            if expr.op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||"):
                return BOOLEAN
            left_ty = self._infer_expr_type(expr.left)
            return left_ty

        if isinstance(expr, UnaryExpr):
            if expr.op == "!":
                return BOOLEAN
            return self._infer_expr_type(expr.operand)

        if isinstance(expr, CallExpr):
            return self._infer_call_type(expr)

        if isinstance(expr, FieldExpr):
            obj_type = self._infer_expr_type(expr.obj)
            if isinstance(obj_type, RecordType):
                ft = obj_type.fields.get(expr.field)
                if ft:
                    return ft
            if isinstance(obj_type, StructType):
                ft = obj_type.required_fields.get(expr.field)
                if ft:
                    return ft
            if isinstance(obj_type, GenericInstance) and obj_type.base_name == "Table":
                return obj_type.args[0] if obj_type.args else INTEGER
            return ERROR_TY

        if isinstance(expr, PipeExpr):
            return self._infer_pipe_type(expr)

        if isinstance(expr, FailPropExpr):
            inner = self._infer_expr_type(expr.expr)
            if isinstance(inner, GenericInstance) and inner.base_name == "Result":
                if inner.args:
                    return inner.args[0]
            # Failable function with concrete return type (not Result<Value>)
            if not isinstance(inner, ErrorType):
                return inner
            return ERROR_TY

        if isinstance(expr, MatchExpr):
            return self._infer_match_result_type(expr)

        if isinstance(expr, ListLiteral):
            if expr.elements:
                return ListType(self._infer_expr_type(expr.elements[0]))
            return ListType(INTEGER)

        if isinstance(expr, LambdaExpr):
            return FunctionType([], UNIT)

        if isinstance(expr, IndexExpr):
            obj_type = self._infer_expr_type(expr.obj)
            if isinstance(obj_type, ListType):
                return obj_type.element
            return ERROR_TY

        if isinstance(expr, LookupAccessExpr):
            return self._infer_lookup_type(expr)

        if isinstance(expr, StoreLookupExpr):
            # Return the expected emit type or Integer as fallback
            if self._expected_emit_type:
                return self._expected_emit_type
            return INTEGER

        return ERROR_TY

    def _infer_call_type(self, expr: CallExpr) -> Type:
        n = len(expr.args)
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            actual_types = [self._infer_expr_type(a) for a in expr.args] if expr.args else []
            narrowed_types = (
                [self._narrow_for_requires(a, t) for a, t in zip(expr.args, actual_types)]
                if actual_types
                else []
            )
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arg_types=narrowed_types if narrowed_types else None,
                )
            elif narrowed_types:
                # Re-resolve with narrowed types if initial sig doesn't match
                from prove.types import TypeVariable as TV
                from prove.types import types_compatible

                if sig.param_types and not all(
                    isinstance(p, TV) or types_compatible(p, a)
                    for p, a in zip(sig.param_types, narrowed_types)
                ):
                    better = self._symbols.resolve_function_any(
                        name,
                        narrowed_types,
                    )
                    if better is not None:
                        sig = better
            if sig:
                ret = sig.return_type
                # Resolve type variables using actual arg types
                if actual_types and sig.param_types:
                    bindings = resolve_type_vars(
                        sig.param_types,
                        actual_types,
                    )
                    ret = substitute_type_vars(ret, bindings)
                if (
                    sig.module
                    and isinstance(ret, GenericInstance)
                    and ret.base_name in ("Option", "Result")
                    and ret.args
                    and self._is_requires_narrowed(
                        name,
                        expr.args,
                        sig.module,
                    )
                ):
                    return ret.args[0]
                return ret
        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n,
                )
            if sig:
                ret = sig.return_type
                if expr.args and sig.param_types:
                    actual_types = [self._infer_expr_type(a) for a in expr.args]
                    bindings = resolve_type_vars(sig.param_types, actual_types)
                    ret = substitute_type_vars(ret, bindings)
                return ret
            resolved = self._symbols.resolve_type(name)
            if resolved:
                return resolved
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            module_name = expr.func.obj.name
            name = expr.func.field
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n,
                )
            if sig:
                ret = sig.return_type
                if expr.args and sig.param_types:
                    actual_types = [self._infer_expr_type(a) for a in expr.args]
                    bindings = resolve_type_vars(
                        sig.param_types,
                        actual_types,
                    )
                    ret = substitute_type_vars(ret, bindings)
                if (
                    isinstance(ret, GenericInstance)
                    and ret.base_name in ("Option", "Result")
                    and ret.args
                    and self._is_requires_narrowed(
                        name,
                        expr.args,
                        module_name,
                    )
                ):
                    return ret.args[0]
                return ret
        return ERROR_TY

    def _infer_pipe_type(self, expr: PipeExpr) -> Type:
        left_ty = self._infer_expr_type(expr.left)
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=1,
                )
            if sig:
                bindings = resolve_type_vars(sig.param_types, [left_ty])
                return substitute_type_vars(sig.return_type, bindings)
        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            # HOF builtins: infer concrete return types
            if name == "filter":
                # filter preserves list element type
                return left_ty
            if name == "map":
                # map return type depends on the lambda/function
                if isinstance(left_ty, ListType):
                    fn_expr = expr.right.args[0] if expr.right.args else None
                    if isinstance(fn_expr, LambdaExpr):
                        saved = dict(self._locals)
                        if fn_expr.params:
                            self._locals[fn_expr.params[0]] = left_ty.element
                        result_ty = self._infer_expr_type(fn_expr.body)
                        self._locals = saved
                        return ListType(result_ty)
                return left_ty
            if name == "reduce":
                # reduce return type is the accumulator type
                if expr.right.args:
                    return self._infer_expr_type(expr.right.args[0])
                return left_ty
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=total,
                )
            if sig:
                extra_arg_types = [self._infer_expr_type(a) for a in expr.right.args]
                all_arg_types = [left_ty] + extra_arg_types
                bindings = resolve_type_vars(sig.param_types, all_arg_types)
                return substitute_type_vars(sig.return_type, bindings)
        return ERROR_TY

    # ── Utilities ──────────────────────────────────────────────

    def _default_for_type(self, ty: Type) -> str:
        """Return a C default value expression for a type."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "String":
                return 'prove_string_from_cstr("")'
            if ty.name == "Boolean":
                return "false"
        return "0"

    @staticmethod
    def _escape_c_string(s: str) -> str:
        """Escape a string for C source."""
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace("\x1b", "\\x1b")
        )
