"""Type and struct emission mixin for CEmitter."""

from __future__ import annotations

from typing import Any

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryDef,
    BinaryExpr,
    CallExpr,
    Expr,
    ExprStmt,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    LookupTypeDef,
    MainDef,
    MatchExpr,
    PipeExpr,
    RecordTypeDef,
    TypeDef,
    TypeIdentifierExpr,
    VarDecl,
)
from prove.c_types import mangle_type_name, map_type
from prove.symbols import FunctionSignature
from prove.types import (
    INTEGER,
    AlgebraicType,
    PrimitiveType,
    RecordType,
    RecursiveFieldInfo,
    StructType,
    Type,
    TypeVariable,
    find_recursive_fields,
)


class TypeEmitterMixin:
    _locals: dict[str, Type]

    def _emit_type_forwards(self) -> None:
        for td in self._all_type_defs():
            cname = mangle_type_name(td.name)
            # Lookup types use enum, not struct
            if isinstance(td.body, LookupTypeDef):
                self._line(f"typedef enum {cname} {cname};")
            else:
                self._line(f"typedef struct {cname} {cname};")
        # Forward declarations for imported local types.
        # Lookup types need full enum definitions here because C requires
        # the complete type for by-value fields.  Algebraic types also need
        # their struct emitted early so that a consuming module's struct
        # (which embeds them by value) compiles in a unity build where the
        # defining module appears later.
        lookup_names: set[str] = set()
        for name, ty in self._imported_local_types():
            cname = mangle_type_name(name)
            if self._is_stdlib_lookup_type(name) or name in self._lookup_tables:
                lookup_names.add(name)
                self._line(f"typedef enum {cname} {cname};")
                self._line(f"enum {cname} {{")
                self._indent += 1
                for i, v in enumerate(ty.variants):
                    self._line(f"{cname}_{v.name.upper()} = {i},")
                self._indent -= 1
                self._line("};")
                self._line("")
            elif isinstance(ty, AlgebraicType):
                # Emit typedef + full struct early for ordering; the same
                # struct will be emitted again by _emit_imported_type_defs
                # but the unity merger deduplicates by struct name.
                self._line(f"typedef struct {cname} {cname};")
                self._emit_algebraic_struct(cname, ty.variants)
                self._line("")
            else:
                self._line(f"typedef struct {cname} {cname};")
        self._line("")
        # Full struct definitions + constructors for imported local types
        self._emit_imported_type_defs(lookup_names)

    def _imported_local_types(self) -> list[tuple[str, Type]]:
        """Collect types imported from local modules (not defined in this module).

        Returns them in topological order (field dependencies before the types
        that use them), so that C struct definitions compile correctly.
        """
        _BUILTIN_NAMES = frozenset(
            (
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
                "Position",  # defined in prove_terminal.h runtime header
            )
        )
        local_type_names = {td.name for td in self._all_type_defs()}

        ordered: list[tuple[str, Type]] = []
        seen: set[str] = set()

        def _visit(ty: Type) -> None:
            if isinstance(ty, PrimitiveType) and ty.name not in _BUILTIN_NAMES:
                # Resolve PrimitiveType to actual type (e.g. Severity → AlgebraicType)
                resolved = self._symbols.resolve_type(ty.name)
                if resolved is None:
                    # Transitive dependency not in local symbol table —
                    # try loading from stdlib (e.g. DiagnosticMessage imports
                    # Severity from Log, but the consuming module only
                    # imports DiagnosticMessage, not Severity).
                    from prove.stdlib_loader import load_stdlib_types

                    for mod_name in ("Log", "UI", "Terminal", "Graphic", "Source"):
                        types = load_stdlib_types(mod_name)
                        if ty.name in types:
                            resolved = types[ty.name]
                            break
                if resolved is not None and isinstance(resolved, (RecordType, AlgebraicType)):
                    ty = resolved
            # StructType is anonymous (no .name) — only traverse its fields
            # to collect named dependencies, don't add it to the ordered list.
            if isinstance(ty, StructType):
                for ftype in ty.required_fields.values():
                    _visit(ftype)
                return
            if not isinstance(ty, (RecordType, AlgebraicType)):
                return
            name = ty.name
            if name in seen or name in local_type_names or name in _BUILTIN_NAMES:
                return
            seen.add(name)
            # Emit field-type dependencies first (traverse embedded types directly)
            if isinstance(ty, RecordType):
                for ftype in ty.fields.values():
                    _visit(ftype)
            ordered.append((name, ty))

        for ty in self._symbols.all_types().values():
            _visit(ty)

        return ordered

    # noqa: E501
    def _direct_imported_local_type_names(self) -> set[str]:
        """Names of types directly imported (not just transitively needed as field deps)."""
        _BUILTIN_NAMES = frozenset(
            (
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
            )
        )
        local_type_names = {td.name for td in self._all_type_defs()}
        result: set[str] = set()
        for name, ty in self._symbols.all_types().items():
            if name not in local_type_names and name not in _BUILTIN_NAMES:
                if isinstance(ty, (RecordType, AlgebraicType)):
                    result.add(name)
        return result

    def _emit_imported_type_defs(self, lookup_names: set[str] | None = None) -> None:
        """Emit full struct definitions for imported local types.

        Constructors are only emitted for directly imported types — transitive
        field dependencies only need the struct definition (no constructor), to
        avoid name collisions with locally-defined constructors.
        """
        skip = lookup_names or set()
        direct_names = self._direct_imported_local_type_names()
        for name, ty in self._imported_local_types():
            if name in skip:
                # Lookup types were fully emitted as enums in _emit_type_forwards
                if name in direct_names:
                    cname = mangle_type_name(name)
                    for v in ty.variants:
                        tag = f"{cname}_{v.name.upper()}"
                        self._line(f"static inline {cname} {v.name}(void) {{")
                        self._indent += 1
                        self._line(f"{cname} _v;")
                        self._line(f"_v = {tag};")
                        self._line("return _v;")
                        self._indent -= 1
                        self._line("}")
                        self._line("")
                continue
            cname = mangle_type_name(name)
            if isinstance(ty, RecordType):
                self._emit_record_struct(cname, ty.fields)
                if name in direct_names:
                    self._emit_record_constructor(cname, name, ty.fields)
            elif isinstance(ty, AlgebraicType):
                self._emit_algebraic_struct(cname, ty.variants)
                if name in direct_names and not self._is_inherited_base_type(name):
                    self._emit_variant_constructors(cname, ty.variants)

    _stdlib_lookup_cache: dict[str, bool] | None = None

    @classmethod
    def _is_stdlib_lookup_type(cls, name: str) -> bool:
        """Check if a type name is a lookup type in any stdlib module."""
        if cls._stdlib_lookup_cache is None:
            cls._stdlib_lookup_cache = {}
            from prove.parse import parse as parse_source
            from prove.stdlib_loader import load_stdlib_prv_source

            for mod_name in ("UI", "Terminal", "Graphic"):
                src = load_stdlib_prv_source(mod_name)
                if not src:
                    continue
                try:
                    mod = parse_source(src, f"<stdlib:{mod_name}>")
                except Exception:
                    continue
                for decl in mod.declarations:
                    if hasattr(decl, "types"):
                        for td in decl.types:
                            cls._stdlib_lookup_cache[td.name] = isinstance(td.body, LookupTypeDef)
        return cls._stdlib_lookup_cache.get(name, False)

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
        if isinstance(ty, TypeVariable) and ty.name == "Value":
            return access
        if isinstance(ty, RecordType):
            self._record_to_value.add(ty.name)
            return f"_prove_record_to_value_{ty.name}({access})"
        return "prove_value_null()"

    def _scan_record_to_value_needs(self) -> None:
        """Scan all call sites to find record->Value conversions needed."""
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
            and sig.module in ("parse", "types")
            and sig.verb in ("creates", "validates")
            and sig.name == "value"  # type: ignore[return-value]
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

    def _emit_record_struct(self, cname: str, fields: dict[str, Type]) -> None:
        """Emit a C struct definition for a record type."""
        self._line(f"struct {cname} {{")
        self._indent += 1
        for fname, ftype in fields.items():
            ct = map_type(ftype)
            if ct.header:
                self._needed_headers.add(ct.header)
            self._line(f"{ct.decl} {fname};")
        self._indent -= 1
        self._line("};")
        self._line("")

    def _emit_record_constructor(self, cname: str, name: str, fields: dict[str, Type]) -> None:
        """Emit a static inline constructor for a record type."""
        params: list[str] = []
        field_names: list[str] = []
        for fname, ftype in fields.items():
            ct = map_type(ftype)
            if ct.header:
                self._needed_headers.add(ct.header)
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

    def _emit_algebraic_struct(
        self,
        cname: str,
        variants: list[Any],
        rec_fields: list[RecursiveFieldInfo] | None = None,
    ) -> None:
        """Emit a tagged union struct for an algebraic type.

        Variants can be VariantInfo (resolved) or AST variant nodes.
        Each must have .name and .fields attributes.
        """
        # Build lookup of direct recursive fields for pointer emission
        rec_direct: set[tuple[str, str]] = set()
        if rec_fields:
            rec_direct = {(rf.variant_name, rf.field_name) for rf in rec_fields if rf.direct}

        # Tag enum
        self._line("enum {")
        self._indent += 1
        for i, v in enumerate(variants):
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
        for v in variants:
            v_fields = self._variant_fields_dict(v)
            if v_fields:
                self._line("struct {")
                self._indent += 1
                for fname, ftype in v_fields.items():
                    if (v.name, fname) in rec_direct:
                        # Recursive field: emit as pointer
                        ct = map_type(ftype)
                        self._line(f"{ct.decl} *{fname};")
                    else:
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

    def _emit_variant_constructors(
        self,
        cname: str,
        variants: list[Any],
        rec_fields: list[RecursiveFieldInfo] | None = None,
    ) -> None:
        """Emit constructors for each variant of an algebraic type."""
        rec_direct: set[tuple[str, str]] = set()
        if rec_fields:
            rec_direct = {(rf.variant_name, rf.field_name) for rf in rec_fields if rf.direct}

        for i, v in enumerate(variants):
            tag = f"{cname}_TAG_{v.name.upper()}"
            v_fields = self._variant_fields_dict(v)
            params: list[str] = []
            for fname, ftype in v_fields.items():
                ct = map_type(ftype)
                if (v.name, fname) in rec_direct:
                    params.append(f"{ct.decl} *{fname}")
                else:
                    params.append(f"{ct.decl} {fname}")
            param_str = ", ".join(params) if params else "void"
            self._line(f"static inline {cname} {cname}_{v.name}({param_str}) {{")
            self._indent += 1
            self._line(f"{cname} _v;")
            self._line(f"_v.tag = {tag};")
            for fname in v_fields:
                self._line(f"_v.{v.name}.{fname} = {fname};")
            self._line("return _v;")
            self._indent -= 1
            self._line("}")
            self._line("")

    def _is_inherited_base_type(self, type_name: str) -> bool:
        """Check if a type is used as a base type by another algebraic type."""
        for td in self._all_type_defs():
            if td.name == type_name:
                continue
            resolved = self._symbols.resolve_type(td.name)
            if isinstance(resolved, AlgebraicType):
                # Check if any variant shares a name with a variant in the base type
                base_type = self._symbols.resolve_type(type_name)
                if isinstance(base_type, AlgebraicType):
                    base_names = {v.name for v in base_type.variants}
                    child_names = {v.name for v in resolved.variants}
                    if base_names.issubset(child_names) and base_names:
                        return True
        return False

    def _variant_fields_dict(self, v: Any) -> dict[str, Type]:
        """Get fields dict from a variant (resolved VariantInfo or AST node)."""
        if isinstance(v.fields, dict):
            # Resolved VariantInfo
            return v.fields
        # AST variant: list of field objects with .name and .type_expr
        result: dict[str, Type] = {}
        for f in v.fields:
            te_name = f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
            ft = self._symbols.resolve_type(te_name)
            result[f.name] = ft if ft else INTEGER
        return result

    def _resolve_ast_fields(self, fields: list[Any]) -> dict[str, Type]:
        """Resolve AST field list to {name: Type} dict."""
        result: dict[str, Type] = {}
        for f in fields:
            te_name = f.type_expr.name if hasattr(f.type_expr, "name") else "Integer"
            ft = self._symbols.resolve_type(te_name)
            result[f.name] = ft if ft else INTEGER
        return result

    def _all_algebraic_type_names(self) -> set[str]:
        """Return the names of all user-defined algebraic types in this module."""
        names: set[str] = set()
        for td in self._all_type_defs():
            if isinstance(td.body, AlgebraicTypeDef):
                resolved = self._symbols.resolve_type(td.name)
                if isinstance(resolved, AlgebraicType):
                    names.add(td.name)
        return names

    def _emit_type_def(self, td: TypeDef) -> None:
        cname = mangle_type_name(td.name)
        body = td.body

        if isinstance(body, RecordTypeDef):
            fields = self._resolve_ast_fields(body.fields)
            self._emit_record_struct(cname, fields)
            self._emit_record_constructor(cname, td.name, fields)

        elif isinstance(body, AlgebraicTypeDef):
            # Use resolved type from checker (includes inherited variants)
            resolved_type = self._symbols.resolve_type(td.name)
            if isinstance(resolved_type, AlgebraicType) and resolved_type.variants:
                # Include mutual recursion group for cross-type detection
                all_alg = self._all_algebraic_type_names()
                rec_fields = find_recursive_fields(resolved_type, all_alg - {td.name})
                if rec_fields:
                    self._recursive_fields_cache[td.name] = {
                        (rf.variant_name, rf.field_name) for rf in rec_fields if rf.direct
                    }
                self._emit_algebraic_struct(cname, resolved_type.variants, rec_fields or None)
                # Skip constructors if this type is a base for another type
                # (child type will emit constructors with its own return type)
                if not self._is_inherited_base_type(td.name):
                    self._emit_variant_constructors(
                        cname, resolved_type.variants, rec_fields or None
                    )
            else:
                self._emit_algebraic_struct(cname, body.variants)
                if not self._is_inherited_base_type(td.name):
                    self._emit_variant_constructors(cname, body.variants)

        elif isinstance(body, BinaryDef):
            # Opaque pointer typedef for C-backed types
            self._line(f"typedef struct {cname}_impl* {cname};")
            self._line("")

        elif isinstance(body, LookupTypeDef):
            # Store-backed lookup: no static emission — data is runtime-only
            if body.is_store_backed:
                self._line(f"/* Store-backed lookup type: {td.name} */")
                self._line("")
                return
            # Dispatch lookup: no enum — function references dispatched inline
            if body.is_dispatch:
                return
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

            # Binary lookup: emit column arrays and reverse lookup table
            if body.is_binary:
                self._emit_binary_lookup_tables(cname, variant_names, body)

    _BINARY_SEARCH_THRESHOLD = 16

    def _emit_binary_lookup_tables(
        self, cname: str, variant_names: list[str], body: LookupTypeDef
    ) -> None:
        """Emit static C arrays and reverse lookup table for binary lookups."""
        # Build a mapping from variant name to entry (first occurrence)
        variant_to_entry: dict[str, Any] = {}
        for entry in body.entries:
            if entry.variant not in variant_to_entry:
                variant_to_entry[entry.variant] = entry

        _C_TYPE_MAP = {
            "String": "const char*",
            "Integer": "int64_t",
            "Decimal": "double",
            "Float": "float",
            "Boolean": "bool",
        }

        # Emit forward arrays (variant index → column value)
        for col_idx, vt in enumerate(body.value_types):
            col_type_name = vt.name if hasattr(vt, "name") else "Unknown"
            c_type = _C_TYPE_MAP.get(col_type_name, "const char*")
            # Use named column if available, otherwise fall back to type name
            named = (
                body.column_names[col_idx]
                if body.column_names
                and col_idx < len(body.column_names)
                and body.column_names[col_idx] is not None
                else None
            )
            if named:
                array_name = f"{cname}_col_{named}"
            else:
                array_name = f"{cname}_col_{col_type_name}"
                # If there are duplicate type names, suffix with index
                type_names = [
                    vt2.name if hasattr(vt2, "name") else "Unknown" for vt2 in body.value_types
                ]
                if type_names.count(col_type_name) > 1:
                    array_name = f"{cname}_col_{col_type_name}_{col_idx}"

            self._line(f"static {c_type} {array_name}[] = {{")
            self._indent += 1
            for vname in variant_names:
                entry = variant_to_entry.get(vname)  # type: ignore[assignment]
                if entry and col_idx < len(entry.values):
                    raw = entry.values[col_idx]
                    kind = (
                        entry.value_kinds[col_idx] if col_idx < len(entry.value_kinds) else "string"
                    )  # noqa: E501
                    if kind == "string":
                        escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
                        self._line(f'"{escaped}",')
                    elif kind == "integer":
                        self._line(f"{raw},")
                    elif kind == "decimal":
                        self._line(f"{raw},")
                    elif kind == "boolean":
                        self._line(f"{raw},")
                    else:
                        self._line(f'"{raw}",')
                else:
                    self._line("0,")
            self._indent -= 1
            self._line("};")
            self._line("")

        use_sorted = len(variant_names) > self._BINARY_SEARCH_THRESHOLD

        # Emit reverse lookup table (string key → variant index)
        # Uses the first String column for reverse lookup keys
        str_col_idx = None
        for idx, vt in enumerate(body.value_types):
            if hasattr(vt, "name") and vt.name == "String":
                str_col_idx = idx
                break

        if str_col_idx is not None:
            # Build entries list
            reverse_entries: list[tuple[str, int]] = []
            for i, vname in enumerate(variant_names):
                entry = variant_to_entry.get(vname)  # type: ignore[assignment]
                if entry and str_col_idx < len(entry.values):
                    reverse_entries.append((entry.values[str_col_idx], i))
            if use_sorted:
                reverse_entries.sort(key=lambda e: e[0])
            self._line(f"static const Prove_LookupEntry {cname}_reverse_entries[] = {{")
            if use_sorted:
                self._line("/* sorted for binary search */")
            self._indent += 1
            for key, idx in reverse_entries:
                escaped = key.replace("\\", "\\\\").replace('"', '\\"')
                self._line(f'{{"{escaped}", {idx}}},')
            self._indent -= 1
            self._line("};")
            self._line(f"static const Prove_LookupTable {cname}_reverse = {{")
            self._indent += 1
            self._line(f"{cname}_reverse_entries, {len(variant_names)}")
            self._indent -= 1
            self._line("};")
            self._line("")

        # Emit reverse lookup table (integer key → variant index)
        # Uses the first Integer column for reverse lookup keys
        int_col_idx = None
        for idx, vt in enumerate(body.value_types):
            if hasattr(vt, "name") and vt.name == "Integer":
                int_col_idx = idx
                break

        if int_col_idx is not None:
            # Build entries list
            int_reverse_entries: list[tuple[str, int]] = []
            for i, vname in enumerate(variant_names):
                entry = variant_to_entry.get(vname)  # type: ignore[assignment]
                if entry and int_col_idx < len(entry.values):
                    int_reverse_entries.append((entry.values[int_col_idx], i))
            if use_sorted:
                int_reverse_entries.sort(key=lambda e: int(e[0]))
            self._line(f"static const Prove_IntLookupEntry {cname}_int_reverse_entries[] = {{")
            if use_sorted:
                self._line("/* sorted for binary search */")
            self._indent += 1
            for key, idx in int_reverse_entries:
                self._line(f"{{{key}, {idx}}},")
            self._indent -= 1
            self._line("};")
            self._line(f"static const Prove_IntLookupTable {cname}_int_reverse = {{")
            self._indent += 1
            self._line(f"{cname}_int_reverse_entries, {len(variant_names)}")
            self._indent -= 1
            self._line("};")
            self._line("")
