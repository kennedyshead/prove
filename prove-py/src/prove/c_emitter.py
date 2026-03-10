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
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    VarDecl,
)
from prove.c_types import mangle_name, map_type
from prove.errors import Diagnostic, Severity
from prove.optimizer import EscapeInfo, MemoizationInfo
from prove.symbols import SymbolTable
from prove.types import (
    BOOLEAN,
    DECIMAL,
    ERROR_TY,
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
    }

    def __init__(
        self,
        module: Module,
        symbols: SymbolTable,
        memo_info: "MemoizationInfo | None" = None,
        escape_info: "EscapeInfo | None" = None,
    ) -> None:
        self._module = module
        self._symbols = symbols
        self._memo_info = memo_info
        self._escape_info = escape_info
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
        self._foreign_names: set[str] = set()
        self._foreign_libs: set[str] = set()
        self._current_requires: list[Expr] = []
        self._lookup_tables: dict[str, LookupTypeDef] = {}
        self._store_lookup_types: set[str] = set()
        self._store_var_types: dict[str, str] = {}  # var_name → lookup type name
        self._record_to_value: set[str] = set()  # record names needing Value converters
        self._expected_emit_type: Type | None = None
        self.diagnostics: list[Diagnostic] = []  # for comptime errors
        self.comptime_dependencies: set["Path"] = set()  # files read by comptime
        self._collect_foreign_info()

    def _collect_foreign_info(self) -> None:
        """Scan module for foreign blocks and collect function names + libraries."""
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    self._foreign_libs.add(fb.library)
                    for ff in fb.functions:
                        self._foreign_names.add(ff.name)
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

        # Main
        for decl in self._module.declarations:
            if isinstance(decl, MainDef):
                self._emit_main(decl)
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
        "Parse": "prove_parse.h",
        "Math": "prove_math.h",
        "Convert": "prove_convert.h",
        "Types": "prove_convert.h",
        "List": "prove_list_ops.h",
        "Format": "prove_format.h",
        "Path": "prove_path.h",
        "Error": "prove_error.h",
        "Pattern": "prove_pattern.h",
        "Random": "prove_random.h",
        "Time": "prove_time.h",
        "Bytes": "prove_bytes.h",
        "Hash": "prove_hash_crypto.h",
        "Store": "prove_store.h",
    }

    def _collect_needed_headers(self) -> None:
        """Pre-scan to determine which runtime headers are needed."""
        # Always include the base runtime
        self._needed_headers.add("prove_runtime.h")
        # The hello world always needs strings
        self._needed_headers.add("prove_string.h")
        # IO init_args is always called in main
        self._needed_headers.add("prove_input_output.h")

        # Include headers for imported stdlib modules
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for imp in decl.imports:
                    header = self._STDLIB_HEADERS.get(imp.module)
                    if header:
                        self._needed_headers.add(header)

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

        # Check if binary lookup tables are used
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for td in decl.types:
                    if isinstance(td.body, LookupTypeDef) and td.body.is_binary:
                        self._needed_headers.add("prove_lookup.h")
                        break

        # Check if any async verbs are used
        for fd in self._all_function_defs():
            if fd.verb in ("detached", "attached", "listens"):
                self._needed_headers.add("prove_coro.h")
                break

        # Check if HOF functions are used (map/filter/reduce)
        self._scan_for_hof(self._module)

    def _scan_for_hof(self, module: Module) -> None:
        """Pre-scan AST for map/filter/reduce calls to include prove_hof.h."""

        def _scan_expr(expr: Expr) -> bool:
            if isinstance(expr, CallExpr):
                if isinstance(expr.func, IdentifierExpr) and expr.func.name in HOF_BUILTINS:
                    return True
                for a in expr.args:
                    if _scan_expr(a):
                        return True
            elif isinstance(expr, BinaryExpr):
                return _scan_expr(expr.left) or _scan_expr(expr.right)
            elif isinstance(expr, PipeExpr):
                return _scan_expr(expr.left) or _scan_expr(expr.right)
            return False

        def _scan_stmts(stmts: list) -> bool:
            for s in stmts:
                if isinstance(s, ExprStmt) and _scan_expr(s.expr):
                    return True
                if isinstance(s, VarDecl) and _scan_expr(s.value):
                    return True
            return False

        for decl in module.declarations:
            if isinstance(decl, (FunctionDef, MainDef)):
                if _scan_stmts(decl.body):
                    self._needed_headers.add("prove_hof.h")
                    return

    # ── Output helpers ─────────────────────────────────────────

    def _line(self, text: str) -> None:
        if text:
            self._out.append("    " * self._indent + text)
        else:
            self._out.append("")

    def _tmp(self) -> str:
        self._tmp_counter += 1
        return f"_tmp{self._tmp_counter}"

    def _in_function_with_escape_info(self) -> bool:
        """Check if we're inside a function with escape analysis info."""
        return self._escape_info is not None and self._current_func is not None

    def _get_current_function_name(self) -> str | None:
        """Get the name of the current function being emitted."""
        if isinstance(self._current_func, FunctionDef):
            return self._current_func.name
        return None

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
            table_name = f"_memo_{cand.verb}_{cand.name}"
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

            # Emit #defines for imported stdlib constants
            from prove.stdlib_loader import load_stdlib_constants

            for imp in decl.imports:
                stdlib_consts = load_stdlib_constants(imp.module)
                if not stdlib_consts:
                    continue
                consts_by_name = {c.name: c for c in stdlib_consts}
                for item in imp.items:
                    const = consts_by_name.get(item.name)
                    if const is not None:
                        escaped = self._escape_c_string(const.raw_value)
                        self._line(
                            f'#define {item.name} prove_string_from_cstr("{escaped}")'
                        )
                        any_emitted = True

        if any_emitted:
            self._line("")

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
                            mangled = mangle_name(sig.verb, sig.name, sig.param_types)
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
            # Streams verb: void return, no coroutine
            if decl.verb == "streams":
                sig = self._symbols.resolve_function(
                    decl.verb, decl.name, len(decl.params)
                )
                if not sig:
                    continue
                mangled = mangle_name(decl.verb, decl.name, sig.param_types)
                params: list[str] = []
                for p, pt in zip(decl.params, sig.param_types):
                    ct = map_type(pt)
                    params.append(f"{ct.decl} {p.name}")
                param_str = ", ".join(params) if params else "void"
                self._line(f"void {mangled}({param_str});")
                any_emitted = True
                continue
            # Async verbs get special forward declarations
            if decl.verb in ("detached", "attached", "listens"):
                sig = self._symbols.resolve_function(
                    decl.verb, decl.name, len(decl.params)
                )
                if not sig:
                    continue
                mangled = mangle_name(decl.verb, decl.name, sig.param_types)
                params: list[str] = []
                for p, pt in zip(decl.params, sig.param_types):
                    ct = map_type(pt)
                    params.append(f"{ct.decl} {p.name}")
                if decl.verb == "attached":
                    ret_ct = map_type(sig.return_type)
                    ret_decl = ret_ct.decl
                    param_str = ", ".join(["Prove_Coro *_caller"] + params) if params else "Prove_Coro *_caller"
                    self._line(f"{ret_decl} {mangled}({param_str});")
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
            )
            params = []
            for p, pt in zip(decl.params, sig.param_types):
                ct = map_type(pt)
                params.append(f"{ct.decl} {p.name}")
            param_str = ", ".join(params) if params else "void"
            self._line(f"{ret_decl} {mangled}({param_str});")
            any_emitted = True
        if any_emitted:
            self._line("")

    # ── Function emission ──────────────────────────────────────

    def _emit_function(self, fd: FunctionDef) -> None:
        # Binary functions are C-backed — no Prove body to emit
        if fd.binary:
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

        mangled = mangle_name(fd.verb, fd.name, param_types)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {p.name}")
        param_str = ", ".join(params) if params else "void"

        self._line(f"{ret_decl} {mangled}({param_str}) {{")
        self._indent += 1

        # Enter region for short-lived allocations
        self._line("prove_region_enter(prove_global_region());")
        self._in_region_scope = True

        # Reset locals
        self._locals.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        # Emit assume assertions at function entry
        for assume_expr in fd.assume:
            cond = self._emit_expr(assume_expr)
            self._line(f'if (!({cond})) prove_panic("assumption violated");')

        # Check if explain block has structured conditions (when)
        has_explain_conditions = fd.explain is not None and any(
            e.condition is not None for e in fd.explain.entries
        )

        if has_explain_conditions:
            self._emit_explain_branches(fd, ret_type)
        else:
            # Emit body
            self._emit_body(fd.body, ret_type, is_failable=fd.can_fail)

        # Exit region
        self._line("prove_region_exit(prove_global_region());")
        self._in_region_scope = False
        self._indent -= 1
        self._line("}")
        self._line("")

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

        mangled = mangle_name(fd.verb, fd.name, param_types)
        args_struct = f"_{mangled}_args"
        body_fn = f"_{mangled}_body"

        # ── Arg struct ───────────────────────────────────────────
        self._line(f"typedef struct {{")
        self._indent += 1
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            self._line(f"{ct.decl} {p.name};")
        self._indent -= 1
        self._line(f"}} {args_struct};")
        self._line("")

        # ── Coroutine body function ──────────────────────────────
        self._current_func = fd
        self._current_func_return = sig.return_type if sig else UNIT
        self._locals.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        self._line(f"static void {body_fn}(Prove_Coro *_coro) {{")
        self._indent += 1
        self._line(f"{args_struct} *_a = ({args_struct} *)_coro->arg;")
        # Expose params as local variables
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            self._line(f"{ct.decl} {p.name} = _a->{p.name};")

        if fd.verb == "listens":
            self._emit_listens_body(fd, param_types)
        else:
            # detached / attached: emit body into coro
            for stmt in fd.body:
                self._emit_stmt(stmt)
            if fd.verb == "attached" and sig and sig.return_type is not UNIT:
                # result stored in last emitted expression — already assigned via body
                pass
        self._line("prove_coro_yield(_coro);")
        self._indent -= 1
        self._line("}")
        self._line("")

        # ── Public entry point ───────────────────────────────────
        if fd.verb == "detached":
            params_str = ", ".join(
                f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types)
            ) or "void"
            self._line(f"void {mangled}({params_str}) {{")
            self._indent += 1
            self._line(f"{args_struct} *_a = malloc(sizeof({args_struct}));")
            for p in fd.params:
                self._line(f"_a->{p.name} = {p.name};")
            self._line(f"Prove_Coro *_c = prove_coro_new({body_fn}, PROVE_CORO_STACK_DEFAULT);")
            self._line(f"prove_coro_start(_c, _a);")
            self._indent -= 1
            self._line("}")
            self._line("")

        elif fd.verb == "attached":
            ret_ct = map_type(sig.return_type) if sig else map_type(UNIT)
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
            self._line(f"prove_coro_start(_c, _a);")
            self._line(f"while (!prove_coro_done(_c)) {{")
            self._indent += 1
            self._line(f"prove_coro_yield(_caller);")
            self._line(f"prove_coro_resume(_c);")
            self._indent -= 1
            self._line("}")
            self._line(f"{ret_ct.decl} _result = ({ret_ct.decl})_c->result;")
            self._line(f"prove_coro_free(_c);")
            self._line(f"return _result;")
            self._indent -= 1
            self._line("}")
            self._line("")

        elif fd.verb == "listens":
            params_list = [f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types)]
            params_str = ", ".join(["Prove_Coro *_coro"] + params_list) if params_list else "Prove_Coro *_coro"
            self._line(f"void {mangled}({params_str}) {{")
            self._indent += 1
            self._line(f"{args_struct} *_a = malloc(sizeof({args_struct}));")
            for p in fd.params:
                self._line(f"_a->{p.name} = {p.name};")
            self._line(f"Prove_Coro *_c = prove_coro_new({body_fn}, PROVE_CORO_STACK_DEFAULT);")
            self._line(f"prove_coro_start(_c, _a);")
            self._line(f"while (!prove_coro_done(_c)) prove_coro_resume(_c);")
            self._line(f"prove_coro_free(_c);")
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
                idx = next(
                    (i for i, n in enumerate(sig.param_names) if n == p.name), None
                )
                if idx is not None and idx < len(sig.param_types):
                    param_types.append(sig.param_types[idx])
                    continue
            param_types.append(INTEGER)

        ret_type = sig.return_type if sig else UNIT
        self._current_func_return = ret_type
        self._current_func = fd
        self._current_requires = fd.requires

        mangled = mangle_name(fd.verb, fd.name, param_types)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {p.name}")
        param_str = ", ".join(params) if params else "void"

        self._line(f"void {mangled}({param_str}) {{")
        self._indent += 1

        self._line("prove_region_enter(prove_global_region());")
        self._in_region_scope = True

        self._locals.clear()
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

        self._line("prove_region_exit(prove_global_region());")
        self._in_region_scope = False
        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_listens_body(self, fd: FunctionDef, param_types: list) -> None:
        """Emit the cooperative loop for a listens verb."""
        self._line("while (1) {")
        self._indent += 1
        self._line("if (prove_coro_cancelled(_coro)) break;")
        self._line("prove_coro_yield(_coro);")
        self._line("if (prove_coro_cancelled(_coro)) break;")
        # The match expression is the body
        for stmt in fd.body:
            self._emit_stmt(stmt)
        self._indent -= 1
        self._line("}")

    def _emit_main(self, md: MainDef) -> None:
        self._current_func = md
        self._current_func_return = UNIT
        self._in_main = True
        self._locals.clear()
        self._current_requires = []

        self._line("int main(int argc, char **argv) {")
        self._indent += 1

        self._line("prove_runtime_init();")
        self._line("prove_io_init_args(argc, argv);")

        # Emit body statements
        for stmt in md.body:
            self._emit_stmt(stmt)

        self._line("prove_runtime_cleanup();")
        self._line("return 0;")
        self._indent -= 1
        self._line("}")
        self._line("")
        self._in_main = False

    # ── Type resolution helpers ────────────────────────────────

    def _resolve_prim_type(self, ty: Type) -> Type:
        """Resolve PrimitiveType to its actual type if it's a user-defined name.

        Handles cases like User:[Mutable] being stored as PrimitiveType("User", ("Mutable",))
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
        if isinstance(expr, (StringLit, TripleStringLit, StringInterp, PathLit)):
            return STRING
        if isinstance(expr, RawStringLit):
            return PrimitiveType("String", ("Reg",))
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
            narrowed_types = [
                self._narrow_for_requires(a, t)
                for a, t in zip(expr.args, actual_types)
            ] if actual_types else []
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arg_types=narrowed_types if narrowed_types else None,
                )
            elif narrowed_types:
                # Re-resolve with narrowed types if initial sig doesn't match
                from prove.types import types_compatible, TypeVariable as TV
                if sig.param_types and not all(
                    isinstance(p, TV) or types_compatible(p, a)
                    for p, a in zip(sig.param_types, narrowed_types)
                ):
                    better = self._symbols.resolve_function_any(
                        name, narrowed_types,
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
                return sig.return_type
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
                    actual_types = [self._infer_expr_type(a) for a in expr.args]
                    bindings = resolve_type_vars(
                        sig.param_types,
                        actual_types,
                    )
                    return substitute_type_vars(ret.args[0], bindings)
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
