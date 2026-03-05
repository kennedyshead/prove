"""Generate C source code from a checked Prove Module + SymbolTable."""

from __future__ import annotations

from typing import Any

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryDef,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentStmt,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    ExplainEntry,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupTypeDef,
    MainDef,
    MatchExpr,
    Module,
    ModuleDecl,
    PathLit,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RegexLit,
    Stmt,
    StringInterp,
    StringLit,
    TailContinue,
    TailLoop,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)
from prove.c_types import CType, mangle_name, mangle_type_name, map_type
from prove.errors import Diagnostic, Severity
from prove.optimizer import MemoizationInfo
from prove.symbols import FunctionSignature, SymbolTable
from prove.types import (
    BOOLEAN,
    DECIMAL,
    ERROR_TY,
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
    RefinementType,
    Type,
    UnitType,
    resolve_type_vars,
    substitute_type_vars,
)

# Built-in functions that map directly to runtime calls
_BUILTIN_MAP: dict[str, str] = {
    "clamp": "prove_clamp",
}


def _get_type_key(ty: Type | None) -> str | None:
    """Get a type key string for overload dispatch.

    For generic types (ListType, GenericInstance), produces richer keys
    like "List<Integer>" instead of just "List".
    """
    if ty is None:
        return None
    if isinstance(ty, ListType):
        inner = getattr(ty.element, "name", "T")
        return f"List<{inner}>"
    if isinstance(ty, GenericInstance):
        args = ",".join(getattr(a, "name", "T") for a in ty.args)
        return f"{ty.base_name}<{args}>"
    return getattr(ty, "name", None)


class CEmitter:
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
    ) -> None:
        self._module = module
        self._symbols = symbols
        self._memo_info = memo_info
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
        self._foreign_names: set[str] = set()
        self._foreign_libs: set[str] = set()
        self._current_requires: list[Expr] = []
        self._lookup_tables: dict[str, LookupTypeDef] = {}
        self._record_to_value: set[str] = set()  # record names needing Value converters
        self.diagnostics: list[Diagnostic] = []  # for comptime errors
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

    def _all_type_defs(self) -> list[TypeDef]:
        """Collect all TypeDef nodes from ModuleDecl blocks."""
        result: list[TypeDef] = []
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                result.extend(decl.types)
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
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                self._emit_function(decl)

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
        "List": "prove_list_ops.h",
        "Format": "prove_format.h",
        "Path": "prove_path.h",
        "Error": "prove_error.h",
        "Pattern": "prove_pattern.h",
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

        # Check if HOF functions are used (map/filter/reduce)
        self._scan_for_hof(self._module)

    def _scan_for_hof(self, module: Module) -> None:
        """Pre-scan AST for map/filter/reduce calls to include prove_hof.h."""
        _hof_names = {"map", "filter", "reduce", "each"}

        def _scan_expr(expr: Expr) -> bool:
            if isinstance(expr, CallExpr):
                if isinstance(expr.func, IdentifierExpr) and expr.func.name in _hof_names:
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

    # ── Type forward declarations ──────────────────────────────

    def _emit_type_forwards(self) -> None:
        for td in self._all_type_defs():
            cname = mangle_type_name(td.name)
            # Lookup types use enum, not struct
            if isinstance(td.body, LookupTypeDef):
                self._line(f"typedef enum {cname} {cname};")
            else:
                self._line(f"typedef struct {cname} {cname};")
        # Forward declarations for imported local types
        for name, ty in self._imported_local_types():
            cname = mangle_type_name(name)
            self._line(f"typedef struct {cname} {cname};")
        self._line("")
        # Full struct definitions for imported local types
        self._emit_imported_type_defs()

    def _imported_local_types(self) -> list[tuple[str, Type]]:
        """Collect types imported from local modules (not defined in this module)."""
        local_type_names = {td.name for td in self._all_type_defs()}
        result: list[tuple[str, Type]] = []
        seen: set[str] = set()
        for name, ty in self._symbols.all_types().items():
            if name in local_type_names:
                continue
            if name in seen:
                continue
            if isinstance(ty, (RecordType, AlgebraicType)):
                # Only include types that aren't builtins
                if name not in (
                    "Integer",
                    "Decimal",
                    "Float",
                    "Boolean",
                    "String",
                    "Character",
                    "Byte",
                    "Unit",
                    "Error",
                    "Result",
                    "Option",
                    "List",
                    "Table",
                ):
                    result.append((name, ty))
                    seen.add(name)
        return result

    def _emit_imported_type_defs(self) -> None:
        """Emit full struct definitions for imported local types."""
        for name, ty in self._imported_local_types():
            cname = mangle_type_name(name)
            if isinstance(ty, RecordType):
                self._line(f"struct {cname} {{")
                self._indent += 1
                for fname, ftype in ty.fields.items():
                    ct = map_type(ftype)
                    self._line(f"{ct.decl} {fname};")
                self._indent -= 1
                self._line("};")
                self._line("")
                # Constructor function for imported record types
                params: list[str] = []
                field_names: list[str] = []
                for fname, ftype in ty.fields.items():
                    ct = map_type(ftype)
                    params.append(f"{ct.decl} {fname}")
                    field_names.append(fname)
                param_str = ", ".join(params) if params else "void"
                self._line(f"static inline {cname} {name}({param_str}) {{")
                self._indent += 1
                self._line(f"{cname} _v;")
                for fname in field_names:
                    self._line(f"_v.{fname} = {fname};")
                self._line("return _v;")
                self._indent -= 1
                self._line("}")
                self._line("")
            elif isinstance(ty, AlgebraicType):
                # Tag enum
                self._line("enum {")
                self._indent += 1
                for i, v in enumerate(ty.variants):
                    tag = f"{cname}_TAG_{v.name.upper()}"
                    self._line(f"{tag} = {i},")
                self._indent -= 1
                self._line("};")
                self._line("")
                # Tagged union struct
                self._line(f"struct {cname} {{")
                self._indent += 1
                self._line("uint8_t tag;")
                self._line("union {")
                self._indent += 1
                for v in ty.variants:
                    if v.fields:
                        self._line("struct {")
                        self._indent += 1
                        for fname, ftype in v.fields.items():
                            ct = map_type(ftype)
                            self._line(f"{ct.decl} {fname};")
                        self._indent -= 1
                        self._line(f"}} {v.name};")
                    else:
                        self._line(f"uint8_t _{v.name};  /* unit variant */")
                self._indent -= 1
                self._line("};")
                self._indent -= 1
                self._line("};")
                self._line("")
                # Constructor functions for each variant
                for i, v in enumerate(ty.variants):
                    tag = f"{cname}_TAG_{v.name.upper()}"
                    params: list[str] = []
                    for fname, ftype in v.fields.items():
                        ct = map_type(ftype)
                        params.append(f"{ct.decl} {fname}")
                    param_str = ", ".join(params) if params else "void"
                    self._line(f"static inline {cname} {v.name}({param_str}) {{")
                    self._indent += 1
                    self._line(f"{cname} _v;")
                    self._line(f"_v.tag = {tag};")
                    for fname in v.fields:
                        self._line(f"_v.{v.name}.{fname} = {fname};")
                    self._line("return _v;")
                    self._indent -= 1
                    self._line("}")
                    self._line("")

    def _emit_record_to_value_converters(self) -> None:
        """Emit static functions that convert record structs to Prove_Value*.

        Pre-scans functions/main for calls where a record arg is passed
        where Value is expected, then emits one converter per record type.
        """
        # Pre-scan: find all record types that need conversion
        self._scan_record_to_value_needs()

        for rec_name in sorted(self._record_to_value):
            rec_ty = self._symbols.resolve_type(rec_name)
            if not isinstance(rec_ty, RecordType):
                continue
            cname = mangle_type_name(rec_name)
            self._line(f"static Prove_Value* _prove_record_to_value_{rec_name}({cname} _r) {{")
            self._indent += 1
            self._line("Prove_Table *_tbl = prove_table_new();")
            for fname, ftype in rec_ty.fields.items():
                val_expr = self._record_field_to_value(f"_r.{fname}", ftype)
                self._line(
                    f'_tbl = prove_table_add(prove_string_from_cstr("{fname}"), {val_expr}, _tbl);'
                )
            self._line("return prove_value_object(_tbl);")
            self._indent -= 1
            self._line("}")
            self._line("")

    def _record_field_to_value(self, access: str, ty: Type) -> str:
        """Return a C expression converting a record field to Prove_Value*."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "Integer":
                return f"prove_value_number({access})"
            if ty.name == "String":
                return f"prove_value_text({access})"
            if ty.name in ("Float", "Decimal"):
                return f"prove_value_decimal({access})"
            if ty.name == "Boolean":
                return f"prove_value_bool({access})"
            if ty.name == "Character":
                return f"prove_value_text(prove_string_from_char({access}))"
            if ty.name == "Value":
                return access
        if isinstance(ty, RecordType):
            self._record_to_value.add(ty.name)
            return f"_prove_record_to_value_{ty.name}({access})"
        return "prove_value_null()"

    def _scan_record_to_value_needs(self) -> None:
        """Scan all call sites to find record→Value conversions needed."""
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef) and not decl.binary:
                saved = dict(self._locals)
                self._locals.clear()
                sig = self._symbols.resolve_function(
                    decl.verb,
                    decl.name,
                    len(decl.params),
                )
                if sig:
                    for p, pt in zip(decl.params, sig.param_types):
                        self._locals[p.name] = pt
                self._scan_stmts_for_record_value(decl.body)
                self._locals = saved
            elif isinstance(decl, MainDef):
                self._scan_stmts_for_record_value(decl.body)

    def _scan_stmts_for_record_value(self, stmts: list) -> None:
        for s in stmts:
            if isinstance(s, ExprStmt):
                self._scan_expr_for_record_value(s.expr)
            elif isinstance(s, VarDecl):
                self._scan_expr_for_record_value(s.value)
            elif isinstance(s, Assignment):
                self._scan_expr_for_record_value(s.value)

    @staticmethod
    def _is_value_conversion(sig: FunctionSignature) -> bool:
        """Return True if sig is Parse.creates/validates value(V)."""
        return (
            sig.module
            and sig.module == "parse"
            and sig.verb in ("creates", "validates")
            and sig.name == "value"
        )

    def _scan_expr_for_record_value(self, expr: Expr) -> None:
        from prove.types import is_json_serializable

        if isinstance(expr, CallExpr):
            # Find the called function's signature
            n_args = len(expr.args)
            sig = None
            if isinstance(expr.func, IdentifierExpr):
                sig = self._symbols.resolve_function(None, expr.func.name, n_args)
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.name,
                        arity=n_args,
                    )
            elif isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
                sig = self._symbols.resolve_function(
                    None,
                    expr.func.field,
                    n_args,
                )
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.field,
                        arity=n_args,
                    )
            if sig and self._is_value_conversion(sig) and expr.args:
                arg_ty = self._infer_expr_type(expr.args[0])
                if isinstance(arg_ty, RecordType) and is_json_serializable(arg_ty):
                    self._record_to_value.add(arg_ty.name)
            # Recurse into args
            if isinstance(expr, CallExpr):
                for a in expr.args:
                    self._scan_expr_for_record_value(a)
        elif isinstance(expr, PipeExpr):
            self._scan_expr_for_record_value(expr.left)
            self._scan_expr_for_record_value(expr.right)
        elif isinstance(expr, BinaryExpr):
            self._scan_expr_for_record_value(expr.left)
            self._scan_expr_for_record_value(expr.right)
        elif isinstance(expr, MatchExpr):
            self._scan_expr_for_record_value(expr.subject)
            for arm in expr.arms:
                self._scan_expr_for_record_value(arm.body)

    def _wrap_record_to_value_args(
        self,
        expr: CallExpr,
        args: list[str],
    ) -> list[str]:
        """Wrap record arguments with _prove_record_to_value_X() where needed.

        Only applies to the verb-gated ``creates value(V)`` function from Parse.
        """
        from prove.types import is_json_serializable

        sig = None
        n_args = len(expr.args)
        if isinstance(expr.func, IdentifierExpr):
            sig = self._symbols.resolve_function(None, expr.func.name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    expr.func.name,
                    arity=n_args,
                )
        elif isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            sig = self._symbols.resolve_function(
                None,
                expr.func.field,
                n_args,
            )
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    expr.func.field,
                    arity=n_args,
                )
        if sig is None or not self._is_value_conversion(sig):
            return args

        if expr.args:
            arg_ty = self._infer_expr_type(expr.args[0])
            if isinstance(arg_ty, RecordType) and is_json_serializable(arg_ty):
                result = list(args)
                result[0] = f"_prove_record_to_value_{arg_ty.name}({args[0]})"
                return result
        return args

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
        if any_emitted:
            self._line("")

    def _eval_comptime(self, const: ConstantDef, expr: ComptimeExpr) -> object | None:
        """Evaluate a comptime expression and return the result."""
        from pathlib import Path

        from prove.interpreter import ComptimeInterpreter

        source_dir = Path(self._module.span.file).parent if self._module.span.file else Path(".")
        interpreter = ComptimeInterpreter(module_source_dir=source_dir)
        try:
            result = interpreter.evaluate(expr)
            return result.value
        except Exception as e:
            diag = Diagnostic(
                severity=Severity.ERROR,
                code="E417",
                message=f"comptime evaluation failed: {e}",
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
        for decl in self._module.declarations:
            if not isinstance(decl, FunctionDef) or decl.binary:
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
            params: list[str] = []
            for p, pt in zip(decl.params, sig.param_types):
                ct = map_type(pt)
                params.append(f"{ct.decl} {p.name}")
            param_str = ", ".join(params) if params else "void"
            self._line(f"{ret_decl} {mangled}({param_str});")
            any_emitted = True
        if any_emitted:
            self._line("")

    # ── Type definitions ───────────────────────────────────────

    def _emit_type_def(self, td: TypeDef) -> None:
        cname = mangle_type_name(td.name)
        body = td.body

        if isinstance(body, RecordTypeDef):
            self._line(f"struct {cname} {{")
            self._indent += 1
            for f in body.fields:
                te_name = f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
                ft = self._symbols.resolve_type(te_name)
                ct = map_type(ft) if ft else CType("int64_t", False, None)
                self._line(f"{ct.decl} {f.name};")
            self._indent -= 1
            self._line("};")
            self._line("")
            # Constructor function for record types
            params: list[str] = []
            field_names: list[str] = []
            for f in body.fields:
                te_name = f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
                ft = self._symbols.resolve_type(te_name)
                ct = map_type(ft) if ft else CType("int64_t", False, None)
                params.append(f"{ct.decl} {f.name}")
                field_names.append(f.name)
            param_str = ", ".join(params) if params else "void"
            self._line(f"static inline {cname} {td.name}({param_str}) {{")
            self._indent += 1
            self._line(f"{cname} _v;")
            for fname in field_names:
                self._line(f"_v.{fname} = {fname};")
            self._line("return _v;")
            self._indent -= 1
            self._line("}")
            self._line("")

        elif isinstance(body, AlgebraicTypeDef):
            # Tag enum
            self._line("enum {")
            self._indent += 1
            for i, v in enumerate(body.variants):
                tag = f"{cname}_TAG_{v.name.upper()}"
                self._line(f"{tag} = {i},")
            self._indent -= 1
            self._line("};")
            self._line("")

            # Tagged union struct
            self._line(f"struct {cname} {{")
            self._indent += 1
            self._line("uint8_t tag;")
            self._line("union {")
            self._indent += 1
            for v in body.variants:
                if v.fields:
                    self._line("struct {")
                    self._indent += 1
                    for f in v.fields:
                        ft = self._symbols.resolve_type(
                            f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
                        )
                        ct = map_type(ft) if ft else CType("int64_t", False, None)
                        self._line(f"{ct.decl} {f.name};")
                    self._indent -= 1
                    self._line(f"}} {v.name};")
                else:
                    self._line(f"uint8_t _{v.name};  /* unit variant */")
            self._indent -= 1
            self._line("};")
            self._indent -= 1
            self._line("};")
            self._line("")

            # Constructor functions for each variant
            for i, v in enumerate(body.variants):
                tag = f"{cname}_TAG_{v.name.upper()}"
                params: list[str] = []
                for f in v.fields:
                    ft = self._symbols.resolve_type(
                        f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
                    )
                    ct = map_type(ft) if ft else CType("int64_t", False, None)
                    params.append(f"{ct.decl} {f.name}")
                param_str = ", ".join(params) if params else "void"
                self._line(f"static inline {cname} {v.name}({param_str}) {{")
                self._indent += 1
                self._line(f"{cname} _v;")
                self._line(f"_v.tag = {tag};")
                for f in v.fields:
                    self._line(f"_v.{v.name}.{f.name} = {f.name};")
                self._line("return _v;")
                self._indent -= 1
                self._line("}")
                self._line("")

        elif isinstance(body, BinaryDef):
            # Opaque pointer typedef for C-backed types
            self._line(f"typedef struct {cname}_impl* {cname};")
            self._line("")

        elif isinstance(body, LookupTypeDef):
            # Lookup type: generate C enum from entries
            # Build unique variant names (skip duplicates with same variant name)
            seen_variants: set[str] = set()
            variant_names: list[str] = []
            for entry in body.entries:
                if entry.variant not in seen_variants:
                    seen_variants.add(entry.variant)
                    variant_names.append(entry.variant)
            # Generate enum
            self._line(f"enum {cname} {{")
            self._indent += 1
            for i, vname in enumerate(variant_names):
                tag = f"{cname}_{vname.upper()}"
                self._line(f"{tag} = {i},")
            self._indent -= 1
            self._line("};")
            self._line("")
            # Constructor functions for each variant (zero-arg constructors)
            for vname in variant_names:
                tag = f"{cname}_{vname.upper()}"
                self._line(f"static inline {cname} {vname}(void) {{")
                self._indent += 1
                self._line(f"{cname} _v;")
                self._line(f"_v = {tag};")
                self._line("return _v;")
                self._indent -= 1
                self._line("}")
                self._line("")

    # ── Function emission ──────────────────────────────────────

    def _emit_function(self, fd: FunctionDef) -> None:
        # Binary functions are C-backed — no Prove body to emit
        if fd.binary:
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
        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_explain_branches(self, fd: FunctionDef, ret_type: Type) -> None:
        """Emit if/else-if chains from explain entries with `when` conditions.

        Entries with conditions map to body expressions by order.
        An entry without a condition becomes the else branch.
        """
        assert fd.explain is not None

        # Separate entries with and without conditions
        cond_entries: list[tuple[ExplainEntry, int]] = []
        default_idx: int | None = None
        for i, entry in enumerate(fd.explain.entries):
            if entry.condition is not None:
                cond_entries.append((entry, i))
            else:
                default_idx = i

        is_unit = isinstance(ret_type, UnitType)

        # Each obligation maps to the body expression at the same index.
        # Body is a list of stmts — we use obligation index to pick the
        # corresponding body expression.
        body = fd.body

        first = True
        for entry, idx in cond_entries:
            assert entry.condition is not None
            cond = self._emit_expr(entry.condition)
            keyword = "if" if first else "else if"
            self._line(f"{keyword} (({cond})) {{")
            self._indent += 1
            if idx < len(body):
                stmt = body[idx]
                if is_unit:
                    self._emit_stmt(stmt)
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        self._line(f"return {self._emit_expr(expr)};")
                    else:
                        self._emit_stmt(stmt)
            self._indent -= 1
            self._line("}")
            first = False

        # Default (else) branch — obligation without condition
        if default_idx is not None and default_idx < len(body):
            self._line("else {")
            self._indent += 1
            stmt = body[default_idx]
            if is_unit:
                self._emit_stmt(stmt)
            else:
                expr = self._stmt_expr(stmt)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
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

    # ── Requires-based option narrowing ─────────────────────────

    def _is_option_narrowed(
        self,
        func_name: str,
        args: list[Expr],
        module_name: str,
    ) -> bool:
        """Check if a call matches a requires validates precondition."""
        if not self._current_requires:
            return False
        # All call args must be identifiers
        call_arg_names: list[str] = []
        for a in args:
            if isinstance(a, IdentifierExpr):
                call_arg_names.append(a.name)
            else:
                return False
        call_key = frozenset(call_arg_names)
        for req_expr in self._current_requires:
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                # requires valid email(param) — resolve the validates function
                sig_v = self._symbols.resolve_function(
                    "validates", req_expr.name, len(req_expr.args)
                )
                if sig_v is None:
                    sig_v = self._symbols.resolve_function_any(
                        req_expr.name, arity=len(req_expr.args)
                    )
                if sig_v is None or sig_v.verb != "validates":
                    continue
                req_mod = sig_v.module or module_name
                if req_mod != module_name:
                    continue
                req_arg_names: list[str] = []
                all_idents = True
                for a in req_expr.args:
                    if isinstance(a, IdentifierExpr):
                        req_arg_names.append(a.name)
                    else:
                        all_idents = False
                        break
                if all_idents and frozenset(req_arg_names) == call_key:
                    return True
                continue
            if not isinstance(req_expr, CallExpr):
                continue
            func = req_expr.func
            # Qualified: Table.has(...)
            if isinstance(func, FieldExpr) and isinstance(func.obj, TypeIdentifierExpr):
                if func.obj.name != module_name:
                    continue
                req_name = func.field
            # Unqualified: has(...)
            elif isinstance(func, IdentifierExpr):
                req_name = func.name
            else:
                continue
            # Check the requires call resolves to a validates function
            n = len(req_expr.args)
            sig = self._symbols.resolve_function("validates", req_name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(req_name, arity=n)
            if sig is None or sig.verb != "validates":
                continue
            # For unqualified calls, verify the module matches
            if isinstance(func, IdentifierExpr):
                req_mod = sig.module
                if req_mod != module_name:
                    continue
            # All requires args must be identifiers matching our call args
            req_arg_names2: list[str] = []
            all_idents2 = True
            for a in req_expr.args:
                if isinstance(a, IdentifierExpr):
                    req_arg_names2.append(a.name)
                else:
                    all_idents2 = False
                    break
            if not all_idents2:
                continue
            if frozenset(req_arg_names2) == call_key:
                return True
        return False

    def _maybe_unwrap_option(
        self,
        call_str: str,
        sig: FunctionSignature,
        call_args: list[Expr],
        module_name: str,
    ) -> str:
        """If the call returns Option<V> and is narrowed by requires, unwrap."""
        from prove.symbols import FunctionSignature

        if not isinstance(sig, FunctionSignature):
            return call_str
        ret = sig.return_type
        if not (isinstance(ret, GenericInstance) and ret.base_name == "Option" and ret.args):
            return call_str
        if not self._is_option_narrowed(sig.name, call_args, module_name):
            return call_str
        # Resolve type variables against actual arg types
        actual_types = [self._infer_expr_type(a) for a in call_args]
        bindings = resolve_type_vars(sig.param_types, actual_types)
        inner = substitute_type_vars(ret.args[0], bindings)
        inner_ct = map_type(inner)
        return f"({inner_ct.decl}){call_str}.value"

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

    def _resolve_call_sig(self, expr: Expr) -> FunctionSignature | None:
        """Resolve the FunctionSignature for a call expression, if any."""
        from prove.symbols import FunctionSignature

        if isinstance(expr, CallExpr):
            n_args = len(expr.args)
            if isinstance(expr.func, IdentifierExpr):
                sig = self._symbols.resolve_function(None, expr.func.name, n_args)
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.name,
                        arity=n_args,
                    )
                return sig if isinstance(sig, FunctionSignature) else None
            if isinstance(expr.func, FieldExpr) and isinstance(
                expr.func.obj,
                TypeIdentifierExpr,
            ):
                sig = self._symbols.resolve_function(
                    None,
                    expr.func.field,
                    n_args,
                )
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.field,
                        arity=n_args,
                    )
                return sig if isinstance(sig, FunctionSignature) else None
        return None

    def _maybe_unwrap_option_value(
        self,
        expr_str: str,
        expr_type: Type,
        target_type: Type,
    ) -> str:
        """If expr_type is Option<T> and target_type is T, unwrap .value with tag check."""
        if (
            isinstance(expr_type, GenericInstance)
            and expr_type.base_name == "Option"
            and expr_type.args
        ):
            inner = expr_type.args[0]
            inner_ct = map_type(inner)
            target_ct = map_type(target_type)
            # Check if target type matches the inner Option type
            if target_ct.decl == inner_ct.decl:
                # Only unwrap if Some (tag == 1), otherwise use a default/zero value
                # For numeric types, use 0 as default; for pointers, use NULL
                if inner_ct.is_pointer or inner_ct.decl == "Prove_String*":
                    default_val = "NULL"
                else:
                    default_val = "0"
                return f"({expr_str}.tag == 1 ? ({inner_ct.decl}){expr_str}.value : {default_val})"
        return expr_str

    def _coerce_call_args(
        self,
        args: list[str],
        arg_exprs: list[Expr],
        sig: FunctionSignature,
    ) -> list[str]:
        """Coerce call arguments to match parameter types.

        Handles:
        - Option<T> arg → T param: unwrap with .value
        - Result<T, E> arg → T param: unwrap with prove_result_unwrap_*
        - Prove_Value* arg → int64_t/String* param: prove_value_as_*
        """
        if sig is None or not hasattr(sig, "param_types"):
            return args
        result = list(args)
        for i, (arg_str, arg_expr) in enumerate(zip(args, arg_exprs)):
            if i >= len(sig.param_types):
                break
            arg_ty = self._infer_expr_type(arg_expr)
            param_ty = sig.param_types[i]
            arg_ct = map_type(arg_ty)
            param_ct = map_type(param_ty)
            if arg_ct.decl == param_ct.decl:
                continue
            # Option<T> → T: unwrap .value with tag check
            if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Option" and arg_ty.args:
                inner_ct = map_type(arg_ty.args[0])
                if inner_ct.decl == param_ct.decl:
                    # Only unwrap if Some (tag == 1), otherwise use default value
                    if inner_ct.is_pointer or inner_ct.decl == "Prove_String*":
                        default_val = "NULL"
                    else:
                        default_val = "0"
                    result[i] = (
                        f"({arg_str}.tag == 1 ? ({param_ct.decl}){arg_str}.value : {default_val})"
                    )
                    continue
            # Result<T, E> → T: unwrap
            if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Result" and arg_ty.args:
                inner_ty = arg_ty.args[0]
                inner_ct = map_type(inner_ty)
                if inner_ct.decl == param_ct.decl:
                    if inner_ct.is_pointer:
                        result[i] = f"({param_ct.decl})prove_result_unwrap_ptr({arg_str})"
                    elif inner_ct.decl == "double":
                        result[i] = f"prove_result_unwrap_double({arg_str})"
                    else:
                        result[i] = f"prove_result_unwrap_int({arg_str})"
                    continue
            # Prove_Value* → concrete type extraction
            if arg_ct.decl == "Prove_Value*" and not param_ct.is_pointer:
                if param_ct.decl in (
                    "int64_t",
                    "int32_t",
                    "int16_t",
                    "int8_t",
                    "uint64_t",
                    "uint32_t",
                    "uint16_t",
                    "uint8_t",
                ):
                    result[i] = f"prove_value_as_number({arg_str})"
                elif param_ct.decl in ("double", "float"):
                    result[i] = f"prove_value_as_decimal({arg_str})"
                elif param_ct.decl == "bool":
                    result[i] = f"prove_value_as_bool({arg_str})"
                continue
            if arg_ct.decl == "Prove_Value*" and param_ct.decl == "Prove_String*":
                result[i] = f"prove_value_as_text({arg_str})"
                continue
        return result

    # ── Body emission ──────────────────────────────────────────

    def _emit_body(self, body: list, ret_type: Type, *, is_failable: bool = False) -> None:
        """Emit a function body. Last expression is the return value."""
        for i, stmt in enumerate(body):
            is_last = i == len(body) - 1
            # TailLoop handles its own returns internally
            if isinstance(stmt, TailLoop):
                self._emit_stmt(stmt)
                continue
            if is_last and not isinstance(stmt, VarDecl):
                # Last expression is the return value
                if isinstance(ret_type, UnitType) and not is_failable:
                    self._emit_stmt(stmt)
                    self._emit_releases(None)
                elif is_failable:
                    # For failable functions, wrap last expression in result_ok
                    if isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result":
                        # Already returns Result — just emit and return ok
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
                        self._line("return prove_result_ok();")
                    elif isinstance(ret_type, UnitType):
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
                        self._line("return prove_result_ok();")
                    else:
                        # Non-Result return: capture and wrap
                        expr = self._stmt_expr(stmt)
                        if expr is not None:
                            ret_tmp = self._tmp()
                            ret_ct = map_type(ret_type)
                            self._line(f"{ret_ct.decl} {ret_tmp} = {self._emit_expr(expr)};")
                            self._emit_releases(ret_tmp)
                            if isinstance(ret_type, RecordType):
                                heap_tmp = self._tmp()
                                self._line(
                                    f"{ret_ct.decl}* {heap_tmp} = malloc(sizeof({ret_ct.decl}));"
                                )
                                self._line(f"*{heap_tmp} = {ret_tmp};")
                                self._line(f"return prove_result_ok_ptr({heap_tmp});")
                            elif ret_ct.is_pointer:
                                self._line(f"return prove_result_ok_ptr({ret_tmp});")
                            elif ret_ct.decl == "double":
                                self._line(f"return prove_result_ok_double({ret_tmp});")
                            elif isinstance(ret_type, GenericInstance) and not ret_ct.is_pointer:
                                # Struct-like generic (Option<T>, etc.) — heap-allocate
                                heap_tmp = self._tmp()
                                self._line(
                                    f"{ret_ct.decl}* {heap_tmp} = malloc(sizeof({ret_ct.decl}));"
                                )
                                self._line(f"*{heap_tmp} = {ret_tmp};")
                                self._line(f"return prove_result_ok_ptr({heap_tmp});")
                            else:
                                self._line(f"return prove_result_ok_int({ret_tmp});")
                        else:
                            self._emit_stmt(stmt)
                            self._emit_releases(None)
                            self._line("return prove_result_ok();")
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        ret_tmp = self._tmp()
                        ret_ct = map_type(ret_type)
                        # For validates functions returning bool: if returning an Option,
                        # check if it's Some (tag == 1)
                        emit_val = self._emit_expr(expr)
                        if isinstance(ret_type, PrimitiveType) and ret_type.name == "Boolean":
                            expr_type = self._infer_expr_type(expr)
                            if (
                                isinstance(expr_type, GenericInstance)
                                and expr_type.base_name == "Option"
                            ):
                                if isinstance(expr, IdentifierExpr):
                                    emit_val = f"{expr.name}.tag == 1"
                        self._line(f"{ret_ct.decl} {ret_tmp} = {emit_val};")
                        self._emit_releases(ret_tmp)
                        self._line(f"return {ret_tmp};")
                    else:
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
            else:
                self._emit_stmt(stmt)

    def _emit_releases(self, skip_var: str | None) -> None:
        """Emit prove_release for all pointer locals except skip_var."""
        for name, ty in self._locals.items():
            if name == skip_var:
                continue
            ct = map_type(ty)
            if ct.is_pointer:
                self._line(f"prove_release({name});")

    def _stmt_expr(self, stmt: Stmt) -> Expr | None:
        """Extract the expression from a statement, if it is an ExprStmt."""
        if isinstance(stmt, ExprStmt):
            return stmt.expr
        if isinstance(stmt, MatchExpr):
            return stmt
        return None

    # ── Statement emission ─────────────────────────────────────

    def _emit_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, VarDecl):
            self._emit_var_decl(stmt)
        elif isinstance(stmt, Assignment):
            self._emit_assignment(stmt)
        elif isinstance(stmt, FieldAssignment):
            self._emit_field_assignment(stmt)
        elif isinstance(stmt, ExprStmt):
            self._emit_expr_stmt(stmt)
        elif isinstance(stmt, TailLoop):
            self._emit_tail_loop(stmt)
        elif isinstance(stmt, TailContinue):
            self._emit_tail_continue(stmt)
        elif isinstance(stmt, MatchExpr):
            self._emit_match_stmt(stmt)
        elif isinstance(stmt, CommentStmt):
            pass  # comments don't emit C code

    def _emit_var_decl(self, vd: VarDecl) -> None:
        # Determine target type: from annotation if present, else from value
        target_ty = self._infer_expr_type(vd.value)
        if vd.type_expr:
            # Resolve type from annotation
            # SimpleType has 'name', GenericType has 'name' and 'args', ModifiedType has 'base_type'
            type_name = getattr(vd.type_expr, "name", None)
            if type_name is None:
                # Could be ModifiedType with base_type
                base = getattr(vd.type_expr, "base_type", None)
                if base:
                    type_name = getattr(base, "name", None)
            if type_name:
                # Handle GenericType annotations (e.g. Table<Value>, Option<Integer>)
                type_args = getattr(vd.type_expr, "args", None)
                if type_args and type_name in ("Table", "Option", "Result"):
                    arg_types: list[Type] = []
                    for ta in type_args:
                        ta_name = getattr(ta, "name", None)
                        if ta_name:
                            resolved_arg = self._symbols.resolve_type(ta_name)
                            arg_types.append(resolved_arg if resolved_arg else INTEGER)
                    target_ty = GenericInstance(type_name, arg_types)
                else:
                    resolved = self._symbols.resolve_type(type_name)
                    if resolved:
                        target_ty = resolved

        # When annotation and value are both Option but with different inner types,
        # emit conversion code (e.g. Option<String> → Option<Integer> via parse)
        value_ty = self._infer_expr_type(vd.value)
        if (
            isinstance(target_ty, GenericInstance)
            and isinstance(value_ty, GenericInstance)
            and target_ty.base_name == value_ty.base_name == "Option"
            and target_ty.args
            and value_ty.args
        ):
            target_inner = map_type(target_ty.args[0])
            value_inner = map_type(value_ty.args[0])
            target_inner_type = target_ty.args[0]
            value_inner_type = value_ty.args[0]
            needs_refinement_check = (
                isinstance(target_inner_type, RefinementType)
                and target_inner_type.constraint
                and isinstance(value_inner_type, PrimitiveType)
                and value_inner_type.name == "String"
            )
            if target_inner.decl != value_inner.decl or needs_refinement_check:
                # Emit conversion: store raw, then convert
                raw_ct = map_type(value_ty)
                tgt_ct = map_type(target_ty)
                raw_tmp = self._tmp()
                self._line(f"{raw_ct.decl} {raw_tmp} = {self._emit_expr(vd.value)};")
                self._line(f"{tgt_ct.decl} {vd.name};")
                self._line(f"if ({raw_tmp}.tag == 1) {{")
                self._indent += 1
                if value_inner.decl == "Prove_String*" and target_inner.decl == "int64_t":
                    self._needed_headers.add("prove_convert.h")
                    cv_tmp = self._tmp()
                    self._line(
                        f"Prove_Result {cv_tmp} = prove_convert_integer_str("
                        f"(Prove_String*){raw_tmp}.value);"
                    )
                    self._line(
                        f"if (!prove_result_is_err({cv_tmp})) "
                        f"{vd.name} = {tgt_ct.decl}_some(prove_result_unwrap_int({cv_tmp}));"
                    )
                    self._line(f"else {vd.name} = {tgt_ct.decl}_none();")
                else:
                    # Generic fallback: cast the value
                    # Check if inner type has refinement constraint
                    needs_refinement = (
                        isinstance(target_inner_type, RefinementType)
                        and target_inner_type.constraint
                    )
                    if needs_refinement:
                        # Validate before wrapping - on failure, return None
                        self._emit_refinement_validation_for_option(
                            f"({target_inner.decl}){raw_tmp}.value",
                            target_inner_type,  # type: ignore[arg-type]
                            tgt_ct.decl,
                            vd.name,
                        )
                    else:
                        self._line(
                            f"{vd.name} = {tgt_ct.decl}_some(({target_inner.decl}){raw_tmp}.value);"
                        )
                self._indent -= 1
                self._line("} else {")
                self._indent += 1
                self._line(f"{vd.name} = {tgt_ct.decl}_none();")
                self._indent -= 1
                self._line("}")
                self._locals[vd.name] = target_ty
                return

        # Check if value is a failable call returning Result and target is the success type
        needs_unwrap = False
        if isinstance(value_ty, GenericInstance) and value_ty.base_name == "Result":
            if isinstance(target_ty, GenericInstance) and target_ty.base_name == "Result":
                # Target is also Result, no unwrapping needed
                pass
            else:
                # Target is the success type, need to unwrap
                needs_unwrap = True
        # Also detect failable non-Result calls (without !)
        # The C function returns Prove_Result even though the Prove type is not Result
        if not needs_unwrap and not isinstance(vd.value, FailPropExpr):
            call_sig = self._resolve_call_sig(vd.value)
            if (
                call_sig is not None
                and call_sig.can_fail
                and not (
                    isinstance(call_sig.return_type, GenericInstance)
                    and call_sig.return_type.base_name == "Result"
                )
            ):
                needs_unwrap = True

        ct = map_type(target_ty)
        val = self._emit_expr(vd.value)

        if needs_unwrap:
            # For failable function returning Result, unwrap before assignment
            tmp = self._tmp()
            self._line(f"Prove_Result {tmp} = {val};")
            # Check for error - panic if non-failable function, return error if failable
            is_failable = (
                getattr(self._current_func, "can_fail", False) if self._current_func else False
            )
            if self._in_main:
                err_str = self._tmp()
                self._line(f"if (prove_result_is_err({tmp})) {{")
                self._indent += 1
                self._line(f"Prove_String *{err_str} = (Prove_String*){tmp}.error;")
                self._line(
                    f"if ({err_str}) fprintf(stderr,"
                    f' "error: %.*s\\n",'
                    f" (int){err_str}->length,"
                    f" {err_str}->data);"
                )
                self._line("prove_runtime_cleanup();")
                self._line("return 1;")
                self._indent -= 1
                self._line("}")
            elif is_failable:
                self._line(f"if (prove_result_is_err({tmp})) return {tmp};")
            else:
                self._line(f'if (prove_result_is_err({tmp})) prove_panic("IO error");')
            # Unwrap the success value
            if isinstance(target_ty, RecordType):
                self._line(f"{ct.decl} {vd.name} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            elif ct.is_pointer:
                self._line(f"{ct.decl} {vd.name} = ({ct.decl})prove_result_unwrap_ptr({tmp});")
            elif ct.decl == "double":
                self._line(f"{ct.decl} {vd.name} = prove_result_unwrap_double({tmp});")
            elif isinstance(target_ty, GenericInstance) and not ct.is_pointer:
                # Struct-like GenericInstance (Option<T>, etc.)
                self._line(f"{ct.decl} {vd.name} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            else:
                # For integer types
                self._line(f"{ct.decl} {vd.name} = prove_result_unwrap_int({tmp});")
        else:
            # Wrap bare value in Option if annotation is Option<T> but value is T
            if (
                isinstance(target_ty, GenericInstance)
                and target_ty.base_name == "Option"
                and not (isinstance(value_ty, GenericInstance) and value_ty.base_name == "Option")
            ):
                # Check if inner type has refinement constraint
                if (
                    target_ty.args
                    and isinstance(target_ty.args[0], RefinementType)
                    and target_ty.args[0].constraint
                ):
                    # Store value in temp first, then validate
                    # Get the inner type for the temp
                    inner_ct = map_type(target_ty.args[0])
                    tmp_val = self._tmp()
                    self._line(f"{inner_ct.decl} {tmp_val} = {val};")
                    self._emit_refinement_validation_for_option(
                        tmp_val, target_ty.args[0], ct.decl, vd.name
                    )
                else:
                    self._line(f"{ct.decl} {vd.name} = {ct.decl}_some({val});")
            else:
                self._line(f"{ct.decl} {vd.name} = {val};")

        # Validate refinement type constraints
        # Skip validation for GenericInstance (Option<T>) because validation is already
        # done in the conversion code. Only validate direct RefinementType assignments.
        if not isinstance(target_ty, GenericInstance):
            check_ty = target_ty
            validation_var = vd.name
            if isinstance(check_ty, RefinementType) and check_ty.constraint:
                self._emit_refinement_validation(validation_var, check_ty)

        # Update locals with target type
        self._locals[vd.name] = target_ty
        # Retain pointer types
        if ct.is_pointer:
            self._line(f"prove_retain({vd.name});")

    def _emit_refinement_validation(self, var_name: str, target_ty: RefinementType) -> None:
        """Emit runtime validation for refinement type constraints."""
        constraint = target_ty.constraint
        if constraint is None:
            return

        if isinstance(constraint, RegexLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.pattern.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            self._line('prove_panic("constraint failed: value does not match pattern");')
            self._indent -= 1
            self._line("}")
        elif isinstance(constraint, RawStringLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.value.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            self._line('prove_panic("constraint failed: value does not match pattern");')
            self._indent -= 1
            self._line("}")

    def _emit_refinement_validation_for_option(
        self, var_name: str, target_ty: Type, option_ct: str | CType, result_var: str
    ) -> None:
        """Emit validation that returns None on failure instead of panicking."""
        if not isinstance(target_ty, RefinementType):
            return
        constraint = target_ty.constraint
        if constraint is None:
            return

        # Declare the result variable first
        self._line(f"{option_ct} {result_var};")

        # Now we know target_ty is RefinementType
        rt = target_ty
        constraint = rt.constraint

        if isinstance(constraint, RegexLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.pattern.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            # Return None for Option type - silent failure
            self._line(f"{result_var} = {option_ct}_none();")
            self._indent -= 1
            self._line("} else {")
            self._indent += 1
            self._line(f"{result_var} = {option_ct}_some({var_name});")
            self._indent -= 1
            self._line("}")
        elif isinstance(constraint, RawStringLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.value.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            # Return None for Option type - silent failure
            self._line(f"{result_var} = {option_ct}_none();")
            self._indent -= 1
            self._line("} else {")
            self._indent += 1
            self._line(f"{result_var} = {option_ct}_some({var_name});")
            self._indent -= 1
            self._line("}")

    def _emit_assignment(self, assign: Assignment) -> None:
        val = self._emit_expr(assign.value)
        self._line(f"{assign.target} = {val};")

    def _emit_field_assignment(self, fa: FieldAssignment) -> None:
        target = self._emit_expr(fa.target)
        val = self._emit_expr(fa.value)
        # Infer target field type and unwrap Option if needed
        target_type = self._infer_expr_type(fa.target)
        if isinstance(target_type, RecordType):
            field_type = target_type.fields.get(fa.field)
            if field_type:
                val_type = self._infer_expr_type(fa.value)
                val = self._maybe_unwrap_option_value(val, val_type, field_type)
        self._line(f"{target}.{fa.field} = {val};")

    def _emit_expr_stmt(self, es: ExprStmt) -> None:
        val = self._emit_expr(es.expr)
        # Suppress bare tmp variable statements from FailPropExpr
        # (the error check is already emitted as a side effect)
        if isinstance(es.expr, FailPropExpr) and val.startswith("_tmp"):
            return
        # Transforms call as statement: capture return value back into
        # the first argument (mutation-by-return for value types).
        if isinstance(es.expr, CallExpr) and isinstance(es.expr.func, IdentifierExpr):
            sig = self._symbols.resolve_function_any(
                es.expr.func.name,
                arity=len(es.expr.args),
            )
            if (
                sig is not None
                and sig.verb == "transforms"
                and es.expr.args
                and isinstance(es.expr.args[0], IdentifierExpr)
            ):
                # Check if any Option args have requires clauses - need to guard the call
                needs_guard = False
                for i, arg in enumerate(es.expr.args[1:], start=1):
                    if i < len(sig.param_types):
                        param_ty = sig.param_types[i]
                        if isinstance(param_ty, GenericInstance) and param_ty.base_name == "Option":
                            # Check if there's a requires clause for this param
                            if sig.requires:
                                for req in sig.requires:
                                    if isinstance(req, CallExpr):
                                        for req_arg in req.args:
                                            if (
                                                isinstance(req_arg, IdentifierExpr)
                                                and isinstance(arg, IdentifierExpr)
                                                and req_arg.name == arg.name
                                            ):
                                                needs_guard = True
                                                break
                                    if isinstance(req, ValidExpr) and req.args is not None:
                                        for req_arg in req.args:
                                            if (
                                                isinstance(req_arg, IdentifierExpr)
                                                and isinstance(arg, IdentifierExpr)
                                                and req_arg.name == arg.name
                                            ):
                                                needs_guard = True
                                                break
                if needs_guard:
                    # Emit if-check for Option args
                    arg_names = []
                    for arg in es.expr.args:
                        if isinstance(arg, IdentifierExpr):
                            arg_names.append(arg.name)
                    first_arg = es.expr.args[0].name
                    self._line("// Guarded transforms call")
                    for i, arg_name in enumerate(arg_names[1:], start=1):
                        if i < len(sig.param_types):
                            param_ty = sig.param_types[i]
                            if (
                                isinstance(param_ty, GenericInstance)
                                and param_ty.base_name == "Option"
                            ):
                                self._line(f"if ({arg_name}.tag == 1) {{")
                                self._indent += 1
                    self._line(f"{first_arg} = {val};")
                    for i, arg_name in enumerate(arg_names[1:], start=1):
                        if i < len(sig.param_types):
                            param_ty = sig.param_types[i]
                            if (
                                isinstance(param_ty, GenericInstance)
                                and param_ty.base_name == "Option"
                            ):
                                self._indent -= 1
                                self._line("}")
                    return
                first_arg = es.expr.args[0].name
                self._line(f"{first_arg} = {val};")
                return
        self._line(f"{val};")

    def _emit_match_stmt(self, m: MatchExpr) -> None:
        """Emit a match expression as a statement (switch)."""
        if m.subject is None:
            # Implicit match — emit as if-else chain
            for i, arm in enumerate(m.arms):
                for s in arm.body:
                    self._emit_stmt(s)
            return

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
        subj = self._emit_expr(m.subject)
        subj_type = self._resolve_prim_type(self._infer_expr_type(m.subject))

        if isinstance(subj_type, AlgebraicType):
            tmp = self._tmp()
            ct = map_type(subj_type)
            self._line(f"{ct.decl} {tmp} = {subj};")
            self._line(f"switch ({tmp}.tag) {{")
            cname = mangle_type_name(subj_type.name)
            for arm in m.arms:
                if isinstance(arm.pattern, VariantPattern):
                    tag = f"{cname}_TAG_{arm.pattern.name.upper()}"
                    self._line(f"case {tag}: {{")
                    self._indent += 1
                    # Bind fields
                    variant_info = next(
                        (v for v in subj_type.variants if v.name == arm.pattern.name), None
                    )
                    if variant_info:
                        for i, sub_pat in enumerate(arm.pattern.fields):
                            if isinstance(sub_pat, BindingPattern):
                                field_names = list(variant_info.fields.keys())
                                if i < len(field_names):
                                    fname = field_names[i]
                                    ft = variant_info.fields[fname]
                                    fct = map_type(ft)
                                    self._locals[sub_pat.name] = ft
                                    self._line(
                                        f"{fct.decl} {sub_pat.name} = "
                                        f"{tmp}.{arm.pattern.name}.{fname};"
                                    )
                    self._emit_match_arm_body(arm.body)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
                elif isinstance(arm.pattern, WildcardPattern):
                    self._line("default: {")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
            self._line("}")
        else:
            # Non-algebraic match — emit as if-else
            if self._in_tail_loop:
                self._emit_tail_match_as_if_else(m, subj)
            else:
                has_variant = any(isinstance(a.pattern, VariantPattern) for a in m.arms)
                if (
                    has_variant
                    and isinstance(subj_type, GenericInstance)
                    and subj_type.base_name == "Option"
                ):
                    self._emit_option_match_stmt(m, subj, subj_type)
                elif has_variant and isinstance(subj_type, RecordType):
                    # Record type check: first matching VariantPattern whose
                    # name matches the record type is the "true" branch,
                    # wildcard is else.
                    first = True
                    for arm in m.arms:
                        if (
                            isinstance(arm.pattern, VariantPattern)
                            and arm.pattern.name == subj_type.name
                        ):
                            # Always matches — emit as unconditional block
                            if not first:
                                self._line("} else {")
                            self._line("{")
                            self._indent += 1
                            self._emit_match_arm_body(arm.body)
                            self._indent -= 1
                            self._line("}")
                        elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                            pass  # Dead code — record always matches its own type
                        first = False
                else:
                    for arm in m.arms:
                        for s in arm.body:
                            self._emit_stmt(s)
        # Restore locals (match arm bindings are scoped to arms)
        self._locals = saved_locals

    def _emit_option_match_stmt(
        self,
        m: MatchExpr,
        subj: str,
        subj_type: GenericInstance,
    ) -> None:
        """Emit match on Option<T> as if/else statement."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, VariantPattern):
                if arm.pattern.name == "Some":
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({subj}.tag == 1) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                        inner_ct = map_type(inner_ty)
                        bind_name = arm.pattern.fields[0].name
                        if bind_name == subj:
                            # Avoid C self-init UB when binding
                            # shadows subject
                            alias = self._tmp()
                            self._line(f"{inner_ct.decl} {alias} = ({inner_ct.decl}){subj}.value;")
                            self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                        else:
                            self._line(
                                f"{inner_ct.decl} {bind_name} = ({inner_ct.decl}){subj}.value;"
                            )
                        self._locals[bind_name] = inner_ty
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                elif arm.pattern.name == "None":
                    if first:
                        self._line("{")
                    else:
                        self._line("} else {")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                    self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            first = False
        # Close if last arm wasn't wildcard/None
        if m.arms and not isinstance(
            m.arms[-1].pattern,
            (WildcardPattern, BindingPattern),
        ):
            last_pat = m.arms[-1].pattern
            if not (isinstance(last_pat, VariantPattern) and last_pat.name == "None"):
                self._line("}")

    def _emit_match_arm_body(self, body: list) -> None:  # type: ignore[type-arg]
        """Emit match arm body, handling TailContinue and returns in tail loop."""
        for i, s in enumerate(body):
            is_last = i == len(body) - 1
            if isinstance(s, TailContinue):
                self._emit_tail_continue(s)
            elif is_last and self._in_tail_loop and not isinstance(s, TailContinue):
                # Base case in tail loop — emit as return
                expr = self._stmt_expr(s)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(s)
            else:
                self._emit_stmt(s)

    def _emit_tail_match_as_if_else(self, m: MatchExpr, subj: str) -> None:
        """Emit a non-algebraic match as if/else inside a tail loop."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    subj_type = self._infer_expr_type(m.subject) if m.subject else UNIT
                    bct = map_type(subj_type)
                    self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, LiteralPattern):
                cond = self._emit_literal_cond(subj, arm.pattern)
                keyword = "if" if first else "} else if"
                self._line(f"{keyword} ({cond}) {{")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
            first = False
        # Close trailing if without else
        if m.arms and not isinstance(m.arms[-1].pattern, (WildcardPattern, BindingPattern)):
            self._line("}")

    # ── Tail call optimization emission ─────────────────────────

    def _emit_tail_loop(self, tl: TailLoop) -> None:
        """Emit a TCO-rewritten loop: while (1) { body }."""
        saved_in_tail = self._in_tail_loop
        self._in_tail_loop = True
        self._line("while (1) {")
        self._indent += 1
        for i, stmt in enumerate(tl.body):
            is_last = i == len(tl.body) - 1
            if is_last and not isinstance(stmt, (TailContinue, TailLoop, MatchExpr)):
                # Last statement is the return value (base case)
                expr = self._stmt_expr(stmt)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(stmt)
            else:
                self._emit_stmt(stmt)
        self._indent -= 1
        self._line("}")
        self._in_tail_loop = saved_in_tail

    def _emit_tail_continue(self, tc: TailContinue) -> None:
        """Emit temporaries for all new values, then assign + continue."""
        # First, evaluate all new values into temporaries
        # (avoids evaluation-order bugs when params depend on each other)
        tmps: list[tuple[str, str]] = []
        for param_name, new_val_expr in tc.assignments:
            tmp = self._tmp()
            ty = self._locals.get(param_name)
            ct = map_type(ty) if ty else CType("int64_t", False, None)
            val = self._emit_expr(new_val_expr)
            self._line(f"{ct.decl} {tmp} = {val};")
            tmps.append((param_name, tmp))
        # Then assign all at once
        for param_name, tmp in tmps:
            self._line(f"{param_name} = {tmp};")
        self._line("continue;")

    # ── Expression emission ────────────────────────────────────

    def _emit_expr(self, expr: Expr) -> str:
        if isinstance(expr, IntegerLit):
            return f"{expr.value}L"

        if isinstance(expr, DecimalLit):
            return expr.value

        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"

        if isinstance(expr, CharLit):
            return f"'{expr.value}'"

        if isinstance(expr, PathLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, TripleStringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, RawStringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringInterp):
            return self._emit_string_interp(expr)

        if isinstance(expr, ListLiteral):
            return self._emit_list_literal(expr)

        if isinstance(expr, IdentifierExpr):
            # Check if this identifier is an outputs function with no args (zero-arg call)
            sig = self._symbols.resolve_function("outputs", expr.name, 0)
            if sig is None:
                sig = self._symbols.resolve_function_any(expr.name, arity=0)
            if sig and sig.verb == "outputs" and sig.module:
                # This is a zero-arg call to an outputs function
                from prove.stdlib_loader import binary_c_name

                c_name = binary_c_name(sig.module, sig.verb, sig.name, None)
                if c_name:
                    return f"{c_name}()"
            return expr.name

        if isinstance(expr, TypeIdentifierExpr):
            return expr.name

        if isinstance(expr, BinaryExpr):
            return self._emit_binary(expr)

        if isinstance(expr, UnaryExpr):
            return self._emit_unary(expr)

        if isinstance(expr, CallExpr):
            return self._emit_call(expr)

        if isinstance(expr, FieldExpr):
            return self._emit_field(expr)

        if isinstance(expr, PipeExpr):
            return self._emit_pipe(expr)

        if isinstance(expr, FailPropExpr):
            return self._emit_fail_prop(expr)

        if isinstance(expr, MatchExpr):
            return self._emit_match_expr(expr)

        if isinstance(expr, LambdaExpr):
            return self._emit_lambda(expr)

        if isinstance(expr, IndexExpr):
            return self._emit_index(expr)

        if isinstance(expr, LookupAccessExpr):
            return self._emit_lookup_access(expr)

        if isinstance(expr, ValidExpr):
            # Prefer validates verb since valid X(...) means validates
            n = len(expr.args) if expr.args is not None else 0
            sig = self._symbols.resolve_function("validates", expr.name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(expr.name, arity=n)
            if expr.args is not None:
                # valid error(x) → call the validates function
                args_c = ", ".join(self._emit_expr(a) for a in expr.args)
                # Check stdlib C name first
                if sig and sig.module:
                    from prove.stdlib_loader import binary_c_name

                    fpt = None
                    if expr.args:
                        actual_fpt = self._infer_expr_type(expr.args[0])
                        fpt = _get_type_key(actual_fpt)
                    if fpt is None:
                        pts = sig.param_types
                        fpt = _get_type_key(pts[0]) if pts else None
                    c_name = binary_c_name(sig.module, "validates", sig.name, fpt)
                    if c_name:
                        return f"{c_name}({args_c})"
                pt = list(sig.param_types) if sig else None
                fn = mangle_name("validates", expr.name, pt)
                return f"{fn}({args_c})"
            # valid error → function reference (used as HOF predicate)
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name

                c_name = binary_c_name(sig.module, "validates", sig.name, None)
                if c_name:
                    return c_name
            pt = list(sig.param_types) if sig else None
            return mangle_name("validates", expr.name, pt)

        if isinstance(expr, ComptimeExpr):
            result = self._eval_comptime(type("const", (), {"span": expr.span})(), expr)
            if result is not None:
                return self._comptime_result_to_c(result)
            return "/* comptime failed */ 0"

        return "/* unsupported expr */ 0"

    # ── Binary expressions ─────────────────────────────────────

    def _emit_binary(self, expr: BinaryExpr) -> str:
        left = self._emit_expr(expr.left)
        right = self._emit_expr(expr.right)

        # Unwrap Option operands when the other side is the inner type
        lt = self._infer_expr_type(expr.left)
        rt = self._infer_expr_type(expr.right)
        left = self._maybe_unwrap_option_value(left, lt, rt)
        right = self._maybe_unwrap_option_value(right, rt, lt)
        # Re-infer after unwrap for downstream checks
        if isinstance(lt, GenericInstance) and lt.base_name == "Option" and lt.args:
            lt_eff = lt.args[0]
        else:
            lt_eff = lt

        # String concatenation
        if expr.op == "+":
            if isinstance(lt_eff, PrimitiveType) and lt_eff.name == "String":
                return f"prove_string_concat({left}, {right})"

        # String equality
        if expr.op == "==" or expr.op == "!=":
            if isinstance(lt_eff, PrimitiveType) and lt_eff.name == "String":
                eq = f"prove_string_eq({left}, {right})"
                return eq if expr.op == "==" else f"(!{eq})"
            # Algebraic type tag comparison: severity == Error → .tag == TAG
            if isinstance(lt_eff, AlgebraicType) and isinstance(expr.right, TypeIdentifierExpr):
                cname = mangle_type_name(lt_eff.name)
                tag = f"{cname}_TAG_{expr.right.name.upper()}"
                cmp = "==" if expr.op == "==" else "!="
                return f"({left}.tag {cmp} {tag})"

        # Map Prove operators to C
        op_map = {
            "&&": "&&",
            "||": "||",
            "==": "==",
            "!=": "!=",
            "<": "<",
            ">": ">",
            "<=": "<=",
            ">=": ">=",
            "+": "+",
            "-": "-",
            "*": "*",
            "/": "/",
            "%": "%",
        }
        c_op = op_map.get(expr.op, expr.op)
        return f"({left} {c_op} {right})"

    # ── Unary expressions ──────────────────────────────────────

    def _emit_unary(self, expr: UnaryExpr) -> str:
        operand = self._emit_expr(expr.operand)
        if expr.op == "!":
            return f"(!{operand})"
        if expr.op == "-":
            return f"(-{operand})"
        return operand

    # ── Call expressions ───────────────────────────────────────

    def _emit_call(self, expr: CallExpr) -> str:
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Higher-order functions handle their own arg emission
            # (must check before eagerly emitting args to avoid
            # hoisting lambdas that will be inlined)
            if name == "map" and len(expr.args) == 2:
                return self._emit_hof_map(expr)
            if name == "each" and len(expr.args) == 2:
                return self._emit_hof_each(expr)
            if name == "filter" and len(expr.args) == 2:
                return self._emit_hof_filter(expr)
            if name == "reduce" and len(expr.args) == 3:
                return self._emit_hof_reduce(expr)

        args = [self._emit_expr(a) for a in expr.args]

        # Wrap record args with record-to-Value converters when needed
        args = self._wrap_record_to_value_args(expr, args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Type-aware dispatch for to_string
            if name == "to_string" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                # Unwrap Option<T> → use inner type for dispatch
                if (
                    isinstance(arg_type, GenericInstance)
                    and arg_type.base_name == "Option"
                    and arg_type.args
                ):
                    inner_ty = arg_type.args[0]
                    inner_ct = map_type(inner_ty)
                    c_name = self._to_string_func(inner_ty)
                    return f"{c_name}(({inner_ct.decl}){args[0]}.value)"
                c_name = self._to_string_func(arg_type)
                return f"{c_name}({', '.join(args)})"

            # Type-aware dispatch for len
            if name == "len" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                if isinstance(arg_type, PrimitiveType) and arg_type.name == "String":
                    return f"prove_string_len({', '.join(args)})"
                return f"prove_list_len({', '.join(args)})"

            # Builtin mapping
            if name in _BUILTIN_MAP:
                c_name = _BUILTIN_MAP[name]
                return f"{c_name}({', '.join(args)})"

            # Foreign (C FFI) functions — emit direct C call, no mangling
            if name in self._foreign_names:
                return f"{name}({', '.join(args)})"

            # Binary bridge: stdlib binary functions → C runtime
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            # Type-based disambiguation for overloaded stdlib functions
            if expr.args:
                from prove.types import TypeVariable, types_compatible

                actual_types = [self._infer_expr_type(a) for a in expr.args]
                if sig is None or (
                    sig.param_types
                    and not all(
                        isinstance(p, TypeVariable) or types_compatible(p, a)
                        for p, a in zip(sig.param_types, actual_types)
                    )
                ):
                    any_sig = self._symbols.resolve_function_any(
                        name,
                        actual_types,
                    )
                    if any_sig is not None:
                        sig = any_sig
            elif sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name

                args = self._coerce_call_args(args, expr.args, sig)
                # Use actual arg types for binary dispatch key (resolves TypeVars)
                fpt = None
                if expr.args:
                    actual_fpt = self._infer_expr_type(expr.args[0])
                    fpt = _get_type_key(actual_fpt)
                if fpt is None:
                    pts = sig.param_types
                    fpt = _get_type_key(pts[0]) if pts else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        sig.module,
                    )
                    return call_str

            # User function — resolve and mangle (re-resolve if needed)
            if sig is None:
                sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )

            if sig and sig.verb is not None:
                args = self._coerce_call_args(args, expr.args, sig)
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                call = f"{mangled}({', '.join(args)})"

                # Only memoize functions returning Integer or Boolean
                ret_type = sig.return_type if sig else None
                is_simple = (
                    ret_type
                    and isinstance(ret_type, PrimitiveType)
                    and ret_type.name in ("Integer", "Boolean")
                )
                if (
                    is_simple
                    and self._memo_info
                    and self._memo_info.is_candidate(sig.verb, sig.name)
                ):
                    table_name = f"_memo_{sig.verb}_{sig.name}"
                    table_size = 32
                    cand = self._memo_info.get_candidate(sig.verb, sig.name)
                    if cand:
                        key = self._get_memo_key(cand, args)
                        idx = f"(({key}) % {table_size})"
                        hit = f"{table_name}[{idx}].valid && {table_name}[{idx}].key == {key}"
                        miss = f"({table_name}[{idx}].key = {key}, {table_name}[{idx}].value = {call}, {table_name}[{idx}].valid = 1, {table_name}[{idx}].value)"
                        result = f"({hit}) ? {table_name}[{idx}].value : ({miss})"
                        return result

                return call

            # Variant constructor or unknown — use name directly
            return f"{name}({', '.join(args)})"

        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            # Pad record constructors with missing fields using defaults
            resolved = self._symbols.resolve_type(name)
            if isinstance(resolved, RecordType):
                # Coerce args to match record field types

                field_types = list(resolved.fields.values())
                fake_sig = type("Sig", (), {"param_types": field_types})()
                args = self._coerce_call_args(args, expr.args, fake_sig)
                if len(args) < len(resolved.fields):
                    for fname, ftype in list(resolved.fields.items())[len(args) :]:
                        args.append(self._default_for_type(ftype))
            elif len(args) < len(getattr(resolved, "fields", {})):
                for fname, ftype in list(resolved.fields.items())[len(args) :]:
                    args.append(self._default_for_type(ftype))
            # Check if it's a variant constructor
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig:
                return f"{name}({', '.join(args)})"
            return f"{name}({', '.join(args)})"

        # Namespaced call: Module.function(args)
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            module_name = expr.func.obj.name
            name = expr.func.field
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name

                pts = sig.param_types
                fpt = _get_type_key(pts[0]) if pts else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        module_name,
                    )
                    return call_str
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                call_str = f"{mangled}({', '.join(args)})"
                call_str = self._maybe_unwrap_option(
                    call_str,
                    sig,
                    expr.args,
                    module_name,
                )
                return call_str
            return f"{name}({', '.join(args)})"

        # Complex callable expression
        func = self._emit_expr(expr.func)
        return f"{func}({', '.join(args)})"

    def _to_string_func(self, ty: Type) -> str:
        """Pick the right prove_string_from_* function."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "Integer":
                return "prove_string_from_int"
            if ty.name in ("Decimal", "Float"):
                return "prove_string_from_double"
            if ty.name == "Boolean":
                return "prove_string_from_bool"
            if ty.name == "Character":
                return "prove_string_from_char"
            if ty.name == "String":
                return ""  # identity — shouldn't happen
        return "prove_string_from_int"  # fallback

    # ── Higher-order function emission ─────────────────────────

    def _emit_loop_body_retains(self, body: Expr, loop_param: str) -> None:
        """Emit prove_retain for captured pointer vars passed to calls in a loop.

        The callee releases its parameters, but loop-invariant captured
        variables are reused on every iteration, so we must retain them
        before each call to keep the refcount balanced.
        """
        if not isinstance(body, CallExpr):
            return
        for arg in body.args:
            if isinstance(arg, IdentifierExpr) and arg.name != loop_param:
                ty = self._locals.get(arg.name)
                if ty and map_type(ty).is_pointer:
                    self._line(f"prove_retain({arg.name});")

    def _emit_hof_map(self, expr: CallExpr) -> str:
        """Emit prove_list_map(list, fn, result_elem_size)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        # Infer element type from the list
        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        # Emit lambda with correct types
        fn_name = self._emit_hof_lambda(expr.args[1], elem_type, "map")
        result_ct = map_type(elem_type)  # map result elem same type for now
        return f"prove_list_map({list_arg}, {fn_name}, sizeof({result_ct.decl}))"

    def _emit_hof_each(self, expr: CallExpr) -> str:
        """Emit each as inline loop (avoids closure issues)."""
        self._needed_headers.add("prove_list.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            idx = self._tmp()
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            self._line(
                f"{elem_ct.decl} {param} = *({elem_ct.decl}*)prove_list_get({list_arg}, {idx});"
            )
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            # Retain captured pointer vars before the call — the callee
            # releases its params, but we reuse captured vars each iteration.
            self._emit_loop_body_retains(lam.body, param)
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            self._line(f"{body_code};")
            self._indent -= 1
            self._line("}")
            return "(void)0"
        # Non-lambda: fall back to prove_list_each
        self._needed_headers.add("prove_hof.h")
        fn_name = self._emit_hof_lambda(lam, elem_type, "each")
        return f"prove_list_each({list_arg}, {fn_name})"

    def _emit_hof_filter(self, expr: CallExpr) -> str:
        """Emit prove_list_filter(list, pred)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        fn_name = self._emit_hof_lambda(expr.args[1], elem_type, "filter")
        return f"prove_list_filter({list_arg}, {fn_name})"

    def _emit_hof_reduce(self, expr: CallExpr) -> str:
        """Emit prove_list_reduce(list, &accum, fn)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        accum_type = self._infer_expr_type(expr.args[1])
        accum_ct = map_type(accum_type)

        # Emit initial accumulator into a temp
        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[1])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        fn_name = self._emit_hof_lambda(
            expr.args[2],
            elem_type,
            "reduce",
            accum_type=accum_type,
        )
        self._line(f"prove_list_reduce({list_arg}, &{accum_tmp}, {fn_name});")
        return accum_tmp

    def _emit_hof_lambda(
        self,
        expr: Expr,
        elem_type: Type,
        kind: str,
        *,
        accum_type: Type | None = None,
    ) -> str:
        """Emit a lambda for HOF use with correct C signature."""
        if isinstance(expr, ValidExpr) and expr.args is None and kind == "filter":
            # valid error → wrap validates function as filter predicate
            sig = self._symbols.resolve_function_any(expr.name)
            pt = list(sig.param_types) if sig else None
            fn = mangle_name("validates", expr.name, pt)
            wrapper = f"_lambda_{self._tmp_counter}"
            self._tmp_counter += 1
            elem_ct = map_type(elem_type)
            lam = (
                f"static bool {wrapper}(const void *_arg) {{\n"
                f"    {elem_ct.decl} _x = *({elem_ct.decl}*)_arg;\n"
                f"    return {fn}(_x);\n"
                f"}}\n"
            )
            self._lambdas.append(lam)
            return wrapper
        if not isinstance(expr, LambdaExpr):
            # Not a lambda — assume it's an identifier referencing a function
            return self._emit_expr(expr)

        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1
        elem_ct = map_type(elem_type)

        if kind == "map":
            # void *fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            # Save and set locals for lambda body
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void *{name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    static {elem_ct.decl} _result;\n"
                f"    _result = {body_code};\n"
                f"    return &_result;\n"
                f"}}\n"
            )
        elif kind == "filter":
            # bool fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static bool {name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    return {body_code};\n"
                f"}}\n"
            )
        elif kind == "reduce":
            # void fn(void *_accum, const void *_elem)
            accum_param = expr.params[0] if len(expr.params) > 0 else "_acc"
            elem_param = expr.params[1] if len(expr.params) > 1 else "_el"
            accum_ct = map_type(accum_type) if accum_type else elem_ct
            saved_locals = dict(self._locals)
            self._locals[accum_param] = accum_type if accum_type else elem_type
            self._locals[elem_param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void {name}(void *_accum, const void *_elem) {{\n"
                f"    {accum_ct.decl} *{accum_param} = ({accum_ct.decl}*)_accum;\n"
                f"    {elem_ct.decl} {elem_param} = *({elem_ct.decl}*)_elem;\n"
                f"    *{accum_param} = {body_code};\n"
                f"}}\n"
            )
        elif kind == "each":
            # void fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void {name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    {body_code};\n"
                f"}}\n"
            )
        else:
            return self._emit_expr(expr)

        self._lambdas.append(lam)
        return name

    # ── Field access ───────────────────────────────────────────

    def _emit_field(self, expr: FieldExpr) -> str:
        obj = self._emit_expr(expr.obj)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, (RecordType, AlgebraicType)):
            return f"{obj}.{expr.field}"
        # Table field access: prove_table_get
        if isinstance(obj_type, GenericInstance) and obj_type.base_name == "Table":
            val_type = obj_type.args[0] if obj_type.args else INTEGER
            val_ct = map_type(val_type)
            get_expr = f'prove_table_get(prove_string_from_cstr("{expr.field}"), {obj})'
            if val_ct.is_pointer:
                return f"({val_ct.decl}){get_expr}.value"
            if val_ct.decl == "int64_t":
                return f"prove_value_to_number({get_expr}.value)"
            if val_ct.decl == "double":
                return f"prove_value_to_decimal({get_expr}.value)"
            if val_ct.decl == "bool":
                return f"prove_value_to_bool({get_expr}.value)"
            return f"({val_ct.decl}){get_expr}.value"
        # Pointer types use ->
        ct = map_type(obj_type)
        if ct.is_pointer:
            return f"{obj}->{expr.field}"
        return f"{obj}.{expr.field}"

    # ── Pipe expressions ───────────────────────────────────────

    def _emit_pipe(self, expr: PipeExpr) -> str:
        left = self._emit_expr(expr.left)

        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            if name in _BUILTIN_MAP:
                return f"{_BUILTIN_MAP[name]}({left})"
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=1,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name

                pts = sig.param_types
                fpt = _get_type_key(pts[0]) if pts else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    return f"{c_name}({left})"
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({left})"
            return f"{name}({left})"

        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            extra_args = [self._emit_expr(a) for a in expr.right.args]
            all_args = [left] + extra_args
            if name in _BUILTIN_MAP:
                return f"{_BUILTIN_MAP[name]}({', '.join(all_args)})"
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=total,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name

                pts = sig.param_types
                fpt = _get_type_key(pts[0]) if pts else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    return f"{c_name}({', '.join(all_args)})"
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({', '.join(all_args)})"
            return f"{name}({', '.join(all_args)})"

        right = self._emit_expr(expr.right)
        return f"{right}({left})"

    # ── Fail propagation ───────────────────────────────────────

    def _emit_fail_prop(self, expr: FailPropExpr) -> str:
        tmp = self._tmp()
        inner = self._emit_expr(expr.expr)
        self._line(f"Prove_Result {tmp} = {inner};")
        if self._in_main:
            self._line(f"if (prove_result_is_err({tmp})) {{")
            self._indent += 1
            err_str = self._tmp()
            self._line(f"Prove_String *{err_str} = (Prove_String*){tmp}.error;")
            self._line(
                f"if ({err_str}) fprintf(stderr,"
                f' "error: %.*s\\n",'
                f" (int){err_str}->length,"
                f" {err_str}->data);"
            )
            self._line("prove_runtime_cleanup();")
            self._line("return 1;")
            self._indent -= 1
            self._line("}")
        else:
            self._line(f"if (prove_result_is_err({tmp})) return {tmp};")
        # Unwrap the success value
        inner_type = self._infer_expr_type(expr.expr)
        if isinstance(inner_type, GenericInstance) and inner_type.base_name == "Result":
            if inner_type.args:
                success_type = inner_type.args[0]
                return self._unwrap_result_value(tmp, success_type)
        # Failable function with non-Result return — the C ABI still wraps
        # in Prove_Result, so we need to unwrap.
        if not isinstance(inner_type, (ErrorType, GenericInstance)):
            return self._unwrap_result_value(tmp, inner_type)
        return f"{tmp}"

    def _unwrap_result_value(self, tmp: str, success_type: Type) -> str:
        """Emit the correct prove_result_unwrap_* call for a success type."""
        if isinstance(success_type, UnitType):
            return tmp  # No value to unwrap
        if isinstance(success_type, RecordType):
            ct = map_type(success_type)
            return f"*(({ct.decl}*)prove_result_unwrap_ptr({tmp}))"
        sname = getattr(success_type, "name", "")
        if sname == "Integer":
            return f"prove_result_unwrap_int({tmp})"
        ct = map_type(success_type)
        if ct.is_pointer:
            return f"({ct.decl})prove_result_unwrap_ptr({tmp})"
        if ct.decl == "double":
            return f"prove_result_unwrap_double({tmp})"
        # Struct-like GenericInstance (Option<T>, etc.)
        if isinstance(success_type, GenericInstance) and not ct.is_pointer:
            return f"*(({ct.decl}*)prove_result_unwrap_ptr({tmp}))"
        return f"prove_result_unwrap_int({tmp})"

    # ── Match expressions ──────────────────────────────────────

    def _emit_match_expr(self, m: MatchExpr) -> str:
        if m.subject is None:
            # Implicit subject: for `matches` verb, use first parameter
            if (
                self._current_func is not None
                and self._current_func.verb == "matches"
                and self._current_func.params
            ):
                first_param = self._current_func.params[0].name
                implicit_subj = MatchExpr(
                    subject=IdentifierExpr(first_param, m.span),
                    arms=m.arms,
                    span=m.span,
                )
                return self._emit_match_expr(implicit_subj)
            # No subject and not matches verb — just emit arm bodies
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return "/* match */"

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
        subj = self._emit_expr(m.subject)
        subj_type = self._resolve_prim_type(self._infer_expr_type(m.subject))

        if not isinstance(subj_type, AlgebraicType):
            # Non-algebraic match: emit as if/else-if chain
            result_type = self._infer_match_result_type(m)
            ct = map_type(result_type)
            is_unit = isinstance(result_type, UnitType)
            tmp = "" if is_unit else self._tmp()
            if not is_unit:
                self._line(f"{ct.decl} {tmp};")

            first = True
            for arm in m.arms:
                if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                    # Default/else branch
                    if first:
                        self._line("{")
                    else:
                        self._line("} else {")
                    self._indent += 1
                    if isinstance(arm.pattern, BindingPattern):
                        bct = map_type(subj_type)
                        self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                        self._locals[arm.pattern.name] = subj_type
                    for i, s in enumerate(arm.body):
                        if not is_unit and i == len(arm.body) - 1:
                            e = self._stmt_expr(s)
                            if e is not None:
                                self._line(f"{tmp} = {self._emit_expr(e)};")
                            else:
                                self._emit_stmt(s)
                        else:
                            self._emit_stmt(s)
                    self._indent -= 1
                    self._line("}")
                elif isinstance(arm.pattern, LiteralPattern):
                    cond = self._emit_literal_cond(subj, arm.pattern)
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({cond}) {{")
                    self._indent += 1
                    for i, s in enumerate(arm.body):
                        if not is_unit and i == len(arm.body) - 1:
                            e = self._stmt_expr(s)
                            if e is not None:
                                self._line(f"{tmp} = {self._emit_expr(e)};")
                            else:
                                self._emit_stmt(s)
                        else:
                            self._emit_stmt(s)
                    self._indent -= 1
                elif isinstance(arm.pattern, VariantPattern):
                    vp = arm.pattern
                    if isinstance(subj_type, GenericInstance) and subj_type.base_name == "Option":
                        if vp.name == "Some":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj}.tag == 1) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                                inner_ct = map_type(inner_ty)
                                bind_name = vp.fields[0].name
                                if bind_name == subj:
                                    alias = self._tmp()
                                    self._line(
                                        f"{inner_ct.decl} {alias} = ({inner_ct.decl}){subj}.value;"
                                    )
                                    self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                                else:
                                    self._line(
                                        f"{inner_ct.decl} {bind_name} = "
                                        f"({inner_ct.decl}){subj}.value;"
                                    )
                                self._locals[bind_name] = inner_ty
                            for i, s in enumerate(arm.body):
                                if not is_unit and i == len(arm.body) - 1:
                                    e = self._stmt_expr(s)
                                    if e is not None:
                                        self._line(f"{tmp} = {self._emit_expr(e)};")
                                    else:
                                        self._emit_stmt(s)
                                else:
                                    self._emit_stmt(s)
                            self._indent -= 1
                        elif vp.name == "None":
                            # None variant — treated as else
                            if first:
                                self._line("{")
                            else:
                                self._line("} else {")
                            self._indent += 1
                            for i, s in enumerate(arm.body):
                                if not is_unit and i == len(arm.body) - 1:
                                    e = self._stmt_expr(s)
                                    if e is not None:
                                        self._line(f"{tmp} = {self._emit_expr(e)};")
                                    else:
                                        self._emit_stmt(s)
                                else:
                                    self._emit_stmt(s)
                            self._indent -= 1
                            self._line("}")
                    elif map_type(subj_type).is_pointer:
                        if vp.name == "Some":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj} != NULL) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                bind_name = vp.fields[0].name
                                # Skip re-declaration when binding name
                                # matches the subject — avoids C
                                # self-init UB (T x = x;)
                                if bind_name != subj:
                                    sct = map_type(subj_type)
                                    self._line(f"{sct.decl} {bind_name} = {subj};")
                                self._locals[bind_name] = subj_type
                            for i, s in enumerate(arm.body):
                                if not is_unit and i == len(arm.body) - 1:
                                    e = self._stmt_expr(s)
                                    if e is not None:
                                        self._line(f"{tmp} = {self._emit_expr(e)};")
                                    else:
                                        self._emit_stmt(s)
                                else:
                                    self._emit_stmt(s)
                            self._indent -= 1
                        else:
                            # None or other — else branch
                            if first:
                                self._line("{")
                            else:
                                self._line("} else {")
                            self._indent += 1
                            for i, s in enumerate(arm.body):
                                if not is_unit and i == len(arm.body) - 1:
                                    e = self._stmt_expr(s)
                                    if e is not None:
                                        self._line(f"{tmp} = {self._emit_expr(e)};")
                                    else:
                                        self._emit_stmt(s)
                                else:
                                    self._emit_stmt(s)
                            self._indent -= 1
                            self._line("}")
                    elif isinstance(subj_type, RecordType) and vp.name == subj_type.name:
                        # Record type always matches its own name — unconditional.
                        # Remaining arms are dead code, so break after emitting.
                        for i, s in enumerate(arm.body):
                            if not is_unit and i == len(arm.body) - 1:
                                e = self._stmt_expr(s)
                                if e is not None:
                                    self._line(f"{tmp} = {self._emit_expr(e)};")
                                else:
                                    self._emit_stmt(s)
                            else:
                                self._emit_stmt(s)
                        break
                first = False

            # Close trailing if without else
            if not isinstance(
                m.arms[-1].pattern,
                (WildcardPattern, BindingPattern),
            ):
                # Don't double-close if last was a None variant (already closed)
                last_pat = m.arms[-1].pattern
                needs_close = True
                if isinstance(last_pat, VariantPattern) and last_pat.name == "None":
                    needs_close = False
                if needs_close:
                    self._line("}")

            self._locals = saved_locals
            return "/* match */" if is_unit else tmp

        # Tagged union switch
        result_type = self._infer_match_result_type(m)
        ct = map_type(result_type)
        result_tmp = self._tmp()
        subj_tmp = self._tmp()
        sct = map_type(subj_type)
        cname = mangle_type_name(subj_type.name)

        if not isinstance(result_type, UnitType):
            self._line(f"{ct.decl} {result_tmp};")
        self._line(f"{sct.decl} {subj_tmp} = {subj};")
        self._line(f"switch ({subj_tmp}.tag) {{")

        for arm in m.arms:
            if isinstance(arm.pattern, VariantPattern):
                tag = f"{cname}_TAG_{arm.pattern.name.upper()}"
                self._line(f"case {tag}: {{")
                self._indent += 1
                variant_info = next(
                    (v for v in subj_type.variants if v.name == arm.pattern.name), None
                )
                if variant_info:
                    for i, sub_pat in enumerate(arm.pattern.fields):
                        if isinstance(sub_pat, BindingPattern):
                            field_names = list(variant_info.fields.keys())
                            if i < len(field_names):
                                fname = field_names[i]
                                ft = variant_info.fields[fname]
                                fct = map_type(ft)
                                self._locals[sub_pat.name] = ft
                                self._line(
                                    f"{fct.decl} {sub_pat.name} = "
                                    f"{subj_tmp}.{arm.pattern.name}.{fname};"
                                )
                for j, s in enumerate(arm.body):
                    if j == len(arm.body) - 1 and not isinstance(result_type, UnitType):
                        e = self._stmt_expr(s)
                        if e is not None:
                            self._line(f"{result_tmp} = {self._emit_expr(e)};")
                        else:
                            self._emit_stmt(s)
                    else:
                        self._emit_stmt(s)
                self._line("break;")
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                self._line("default: {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    self._locals[arm.pattern.name] = subj_type
                    self._line(f"{sct.decl} {arm.pattern.name} = {subj_tmp};")
                for j, s in enumerate(arm.body):
                    if j == len(arm.body) - 1 and not isinstance(result_type, UnitType):
                        e = self._stmt_expr(s)
                        if e is not None:
                            self._line(f"{result_tmp} = {self._emit_expr(e)};")
                        else:
                            self._emit_stmt(s)
                    else:
                        self._emit_stmt(s)
                self._line("break;")
                self._indent -= 1
                self._line("}")
        self._line("}")
        # Restore locals (match arm bindings are scoped to arms)
        self._locals = saved_locals

        return result_tmp if not isinstance(result_type, UnitType) else "/* match */"

    def _infer_match_result_type(self, m: MatchExpr) -> Type:
        """Infer the result type of a match expression."""
        for arm in m.arms:
            if arm.body:
                last = arm.body[-1]
                if isinstance(last, ExprStmt):
                    return self._infer_expr_type(last.expr)
        return UNIT

    # ── Lambda expressions ─────────────────────────────────────

    def _emit_lambda(self, expr: LambdaExpr) -> str:
        # Hoist as a static function
        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1

        # We don't know param types precisely, so use generic approach
        params = ", ".join(f"int64_t {p}" for p in expr.params)
        if not params:
            params = "void"

        body_code = self._emit_expr(expr.body)

        lam = f"static int64_t {name}({params}) {{\n    return {body_code};\n}}\n"
        self._lambdas.append(lam)
        return name

    # ── String interpolation ───────────────────────────────────

    def _emit_string_interp(self, expr: StringInterp) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, StringLit):
                escaped = self._escape_c_string(part.value)
                parts.append(f'prove_string_from_cstr("{escaped}")')
            else:
                part_type = self._infer_expr_type(part)
                val = self._emit_expr(part)
                if isinstance(part_type, PrimitiveType) and part_type.name == "String":
                    parts.append(val)
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Integer":
                    parts.append(f"prove_string_from_int({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name in (
                    "Decimal",
                    "Float",
                ):
                    parts.append(f"prove_string_from_double({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Boolean":
                    parts.append(f"prove_string_from_bool({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Character":
                    parts.append(f"prove_string_from_char({val})")
                elif (
                    isinstance(part_type, GenericInstance)
                    and part_type.base_name == "Option"
                    and part_type.args
                ):
                    inner = part_type.args[0]
                    inner_ct = map_type(inner)
                    unwrapped = f"({inner_ct.decl}){val}.value"
                    c_name = self._to_string_func(inner)
                    parts.append(f"{c_name}({unwrapped})")
                else:
                    parts.append(f"prove_string_from_int({val})")

        if not parts:
            return 'prove_string_from_cstr("")'
        result = parts[0]
        for p in parts[1:]:
            result = f"prove_string_concat({result}, {p})"
        return result

    # ── List literal ───────────────────────────────────────────

    def _emit_list_literal(self, expr: ListLiteral) -> str:
        if not expr.elements:
            return "prove_list_new(sizeof(int64_t), 4)"
        # Determine element type
        elem_type = self._infer_expr_type(expr.elements[0])
        ct = map_type(elem_type)

        tmp = self._tmp()
        self._line(f"Prove_List *{tmp} = prove_list_new(sizeof({ct.decl}), {len(expr.elements)});")
        for elem in expr.elements:
            val = self._emit_expr(elem)
            etmp = self._tmp()
            self._line(f"{ct.decl} {etmp} = {val};")
            self._line(f"prove_list_push(&{tmp}, &{etmp});")
        return tmp

    # ── Index expression ───────────────────────────────────────

    def _emit_index(self, expr: IndexExpr) -> str:
        obj = self._emit_expr(expr.obj)
        idx = self._emit_expr(expr.index)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, ListType):
            elem_ct = map_type(obj_type.element)
            return f"(*({elem_ct.decl}*)prove_list_get({obj}, {idx}))"
        return f"{obj}[{idx}]"

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
            # Failable function with concrete return type (not Result<T>)
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

        return ERROR_TY

    def _infer_call_type(self, expr: CallExpr) -> Type:
        n = len(expr.args)
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n,
                )
            if sig:
                ret = sig.return_type
                # Resolve type variables using actual arg types
                actual_types = [self._infer_expr_type(a) for a in expr.args] if expr.args else []
                if actual_types and sig.param_types:
                    bindings = resolve_type_vars(
                        sig.param_types,
                        actual_types,
                    )
                    ret = substitute_type_vars(ret, bindings)
                if (
                    sig.module
                    and isinstance(ret, GenericInstance)
                    and ret.base_name == "Option"
                    and ret.args
                    and self._is_option_narrowed(
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
                    and ret.base_name == "Option"
                    and ret.args
                    and self._is_option_narrowed(
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
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=1,
                )
            if sig:
                return sig.return_type
        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=total,
                )
            if sig:
                return sig.return_type
        return ERROR_TY

    # ── Lookup expressions ─────────────────────────────────────

    def _emit_lookup_access(self, expr: LookupAccessExpr) -> str:
        """Emit a compile-time lookup: TypeName:"main" -> Main(), TypeName:Main -> string."""
        lookup = self._lookup_tables.get(expr.type_name)
        if lookup is None:
            return "/* no lookup table */ 0"
        operand = expr.operand
        if isinstance(operand, (StringLit, IntegerLit, BooleanLit)):
            # Forward: literal -> variant constructor
            value = operand.value
            if isinstance(operand, BooleanLit):
                value = "true" if operand.value else "false"
            for entry in lookup.entries:
                if entry.value == str(value):
                    return f"{entry.variant}()"
            return "/* lookup miss */ 0"
        if isinstance(operand, TypeIdentifierExpr):
            # Reverse: variant -> value
            for entry in lookup.entries:
                if entry.variant == operand.name:
                    if entry.value_kind == "string":
                        escaped = self._escape_c_string(entry.value)
                        return f'prove_string_from_cstr("{escaped}")'
                    if entry.value_kind == "integer":
                        return f"{entry.value}L"
                    if entry.value_kind == "boolean":
                        return entry.value
                    return f'prove_string_from_cstr("{entry.value}")'
            return "/* lookup miss */ 0"
        return "/* unsupported lookup */ 0"

    def _infer_lookup_type(self, expr: LookupAccessExpr) -> Type:
        """Infer the type of a lookup access expression."""
        lookup = self._lookup_tables.get(expr.type_name)
        if lookup is None:
            return ERROR_TY
        operand = expr.operand
        if isinstance(operand, (StringLit, IntegerLit, BooleanLit)):
            # Forward: literal -> algebraic type
            resolved = self._symbols.resolve_type(expr.type_name)
            return resolved if resolved else ERROR_TY
        if isinstance(operand, TypeIdentifierExpr):
            # Reverse: variant -> value type
            name = lookup.value_type.name if hasattr(lookup.value_type, "name") else ""
            resolved = self._symbols.resolve_type(name)
            return resolved if resolved else ERROR_TY
        return ERROR_TY

    def _emit_literal_cond(self, subj: str, pat: LiteralPattern) -> str:
        """Generate a C condition comparing subj to a literal pattern."""
        val = pat.value
        if pat.kind == "boolean" or val in ("true", "false"):
            return subj if val == "true" else f"!({subj})"
        if pat.kind == "string":
            escaped = self._escape_c_string(val)
            return f'prove_string_eq({subj}, prove_string_from_cstr("{escaped}"))'
        return f"{subj} == {val}L"

    def _default_for_type(self, ty: Type) -> str:
        """Return a C default value expression for a type."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "String":
                return 'prove_string_from_cstr("")'
            if ty.name == "Boolean":
                return "false"
        return "0"

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _escape_c_string(s: str) -> str:
        """Escape a string for C source."""
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
