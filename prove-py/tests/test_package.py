"""Tests for .prvpkg package format."""

import json
import tempfile
from pathlib import Path

from prove.ast_nodes import (
    AlgebraicTypeDef,
    ConstantDef,
    ExprStmt,
    FieldDef,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    LookupEntry,
    LookupTypeDef,
    Module,
    ModuleDecl,
    Param,
    RecordTypeDef,
    SimpleType,
    TypeDef,
    Variant,
)
from prove.package import (
    create_package,
    extract_signatures,
    extract_types,
    get_asset,
    list_modules,
    load_package_module,
    read_package,
)
from prove.source import Span

_S = Span("test.prv", 1, 1, 1, 10)


def _test_module() -> Module:
    return Module(
        declarations=[
            ModuleDecl(
                name="Utils",
                narrative=None,
                domain=None,
                temporal=None,
                imports=[],
                types=[
                    TypeDef(
                        name="Color",
                        type_params=[],
                        modifiers=[],
                        body=AlgebraicTypeDef(
                            variants=[
                                Variant("Red", [], _S),
                                Variant("Blue", [], _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                        doc_comment="A color.",
                    ),
                    TypeDef(
                        name="Point",
                        type_params=[],
                        modifiers=[],
                        body=RecordTypeDef(
                            fields=[
                                FieldDef("x", SimpleType("Integer", _S), None, _S),
                                FieldDef("y", SimpleType("Integer", _S), None, _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                    ),
                ],
                constants=[
                    ConstantDef(
                        "PI", SimpleType("Float", _S), IntegerLit("3", _S), _S, "Pi approx."
                    )
                ],
                invariants=[],
                foreign_blocks=[],
                body=[
                    FunctionDef(
                        verb="creates",
                        name="add",
                        params=[
                            Param("a", SimpleType("Integer", _S), None, _S),
                            Param("b", SimpleType("Integer", _S), None, _S),
                        ],
                        return_type=SimpleType("Integer", _S),
                        can_fail=False,
                        ensures=[],
                        requires=[],
                        explain=None,
                        terminates=None,
                        trusted=None,
                        binary=False,
                        why_not=[],
                        chosen=None,
                        near_misses=[],
                        know=[],
                        assume=[],
                        believe=[],
                        with_constraints=[],
                        intent=None,
                        satisfies=[],
                        event_type=None,
                        state_init=None,
                        state_type=None,
                        body=[
                            ExprStmt(IdentifierExpr("a", _S), _S),
                        ],
                        doc_comment="Add two numbers.",
                        span=_S,
                    ),
                ],
                span=_S,
            )
        ],
        span=_S,
    )


def test_create_read_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        create_package(
            pkg_path,
            name="test-utils",
            version="1.0.0",
            prove_version="1.1.0",
            modules={"Utils": _test_module()},
            dependencies=[("json-utils", "0.3.0")],
        )

        info = read_package(pkg_path)
        assert info.name == "test-utils"
        assert info.version == "1.0.0"
        assert info.prove_version == "1.1.0"
        assert len(info.dependencies) == 1
        assert info.dependencies[0] == ("json-utils", "0.3.0")

        # Exports: 2 types + 1 constant + 1 function
        type_exports = [e for e in info.exports if e.kind == "type"]
        func_exports = [e for e in info.exports if e.kind == "function"]
        const_exports = [e for e in info.exports if e.kind == "constant"]
        assert len(type_exports) == 2
        assert len(func_exports) == 1
        assert len(const_exports) == 1

        # Check function export
        add_fn = func_exports[0]
        assert add_fn.name == "add"
        assert add_fn.verb == "creates"
        assert add_fn.return_type == "Integer"
        assert add_fn.can_fail is False
        params = json.loads(add_fn.params)
        assert len(params) == 2
        assert params[0]["name"] == "a"


def test_full_ast_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        original = _test_module()
        create_package(
            pkg_path,
            name="test",
            version="0.1.0",
            prove_version="1.0.0",
            modules={"Utils": original},
        )

        restored = load_package_module(pkg_path, "Utils")
        assert isinstance(restored, Module)
        decl = restored.declarations[0]
        assert isinstance(decl, ModuleDecl)
        assert decl.name == "Utils"
        assert len(decl.types) == 2
        assert decl.types[0].name == "Color"
        assert len(decl.body) == 1


def test_extract_signatures():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        create_package(
            pkg_path,
            name="test",
            version="0.1.0",
            prove_version="1.0.0",
            modules={"Utils": _test_module()},
        )

        sigs = extract_signatures(pkg_path, "Utils")
        assert len(sigs) == 1
        assert sigs[0].name == "add"
        assert sigs[0].verb == "creates"


def test_extract_types():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        create_package(
            pkg_path,
            name="test",
            version="0.1.0",
            prove_version="1.0.0",
            modules={"Utils": _test_module()},
        )

        types = extract_types(pkg_path, "Utils")
        assert len(types) == 2
        names = {t.name for t in types}
        assert "Color" in names
        assert "Point" in names


def test_assets():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        test_data = b"csv,data,here\n1,2,3"
        create_package(
            pkg_path,
            name="test",
            version="0.1.0",
            prove_version="1.0.0",
            modules={"Utils": _test_module()},
            assets={"data/prices.csv": test_data},
        )

        retrieved = get_asset(pkg_path, "data/prices.csv")
        assert retrieved == test_data

        missing = get_asset(pkg_path, "nonexistent")
        assert missing is None


def test_list_modules():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "test.prvpkg"
        create_package(
            pkg_path,
            name="test",
            version="0.1.0",
            prove_version="1.0.0",
            modules={"Utils": _test_module(), "Helpers": _test_module()},
        )

        mods = list_modules(pkg_path)
        assert sorted(mods) == ["Helpers", "Utils"]


def test_lookup_type_in_package():
    """Package with lookup type preserves all entries."""
    module = Module(
        declarations=[
            ModuleDecl(
                name="Tokens",
                narrative=None,
                domain=None,
                temporal=None,
                imports=[],
                types=[
                    TypeDef(
                        name="TokenKind",
                        type_params=[],
                        modifiers=[],
                        body=LookupTypeDef(
                            value_type=SimpleType("String", _S),
                            entries=[
                                LookupEntry("Plus", "+", "string", _S),
                                LookupEntry("Minus", "-", "string", _S),
                                LookupEntry("Star", "*", "string", _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                    )
                ],
                constants=[],
                invariants=[],
                foreign_blocks=[],
                body=[],
                span=_S,
            )
        ],
        span=_S,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = Path(tmpdir) / "tokens.prvpkg"
        create_package(
            pkg_path,
            name="tokens",
            version="1.0.0",
            prove_version="1.0.0",
            modules={"Tokens": module},
        )

        restored = load_package_module(pkg_path, "Tokens")
        decl = restored.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert td.name == "TokenKind"
        assert isinstance(td.body, LookupTypeDef)
        assert len(td.body.entries) == 3
        assert td.body.entries[0].variant == "Plus"
        assert td.body.entries[1].value == "-"
