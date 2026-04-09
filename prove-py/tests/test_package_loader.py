"""Tests for package loader and checker integration."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from prove.ast_nodes import (
    AlgebraicTypeDef,
    ConstantDef,
    ExprStmt,
    FunctionDef,
    IdentifierExpr,
    ImportDecl,
    ImportItem,
    IntegerLit,
    Module,
    ModuleDecl,
    Param,
    SimpleType,
    TypeDef,
    Variant,
)
from prove.checker import Checker
from prove.lockfile import LockedPackage, Lockfile
from prove.package import create_package
from prove.package_loader import (
    PackageModuleInfo,
    load_installed_packages,
    load_package_for_emit,
)
from prove.source import Span

_S = Span("test.prv", 1, 1, 1, 10)


def _make_package_module() -> Module:
    """Create a package module with types and functions."""
    return Module(
        declarations=[
            ModuleDecl(
                name="JsonUtils",
                narrative=None,
                domain=None,
                temporal=None,
                imports=[],
                types=[
                    TypeDef(
                        name="JsonError",
                        type_params=[],
                        modifiers=[],
                        body=AlgebraicTypeDef(
                            variants=[
                                Variant("ParseError", [], _S),
                                Variant("TypeError", [], _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                        doc_comment="JSON error types.",
                    ),
                ],
                constants=[
                    ConstantDef("MAX_DEPTH", SimpleType("Integer", _S), IntegerLit("100", _S), _S),
                ],
                invariants=[],
                foreign_blocks=[],
                body=[
                    FunctionDef(
                        verb="creates",
                        name="parse_json",
                        params=[Param("input", SimpleType("String", _S), None, _S)],
                        return_type=SimpleType("String", _S),
                        can_fail=True,
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
                        body=[ExprStmt(IdentifierExpr("input", _S), _S)],
                        doc_comment="Parse a JSON string.",
                        span=_S,
                    ),
                ],
                span=_S,
            )
        ],
        span=_S,
    )


def _create_test_package(tmpdir: Path) -> Path:
    """Create a test .prvpkg file and return its path."""
    pkg_path = tmpdir / "json-utils" / "0.3.0.prvpkg"
    create_package(
        pkg_path,
        name="json-utils",
        version="0.3.0",
        prove_version="1.0.0",
        modules={"JsonUtils": _make_package_module()},
    )
    return pkg_path


def test_load_installed_packages():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        _create_test_package(tmpdir)

        lockfile = Lockfile(
            prove_version="1.0.0",
            packages=[
                LockedPackage("json-utils", "0.3.0", "sha256:abc", "https://example.com"),
            ],
        )

        with patch("prove.package_loader.cache_dir", return_value=tmpdir):
            modules = load_installed_packages(tmpdir, lockfile)

        assert "JsonUtils" in modules
        info = modules["JsonUtils"]
        assert info.package_name == "json-utils"
        assert info.package_version == "0.3.0"
        assert "JsonError" in info.types
        assert len(info.functions) == 1
        assert info.functions[0].name == "parse_json"


def test_checker_resolves_package_imports():
    """Checker can resolve imports from installed packages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        _create_test_package(tmpdir)

        lockfile = Lockfile(
            prove_version="1.0.0",
            packages=[
                LockedPackage("json-utils", "0.3.0", "sha256:abc", "https://example.com"),
            ],
        )

        with patch("prove.package_loader.cache_dir", return_value=tmpdir):
            package_modules = load_installed_packages(tmpdir, lockfile)

        # Create a user module that imports from the package
        user_module = Module(
            declarations=[
                ModuleDecl(
                    name="App",
                    narrative=None,
                    domain=None,
                    temporal=None,
                    imports=[
                        ImportDecl(
                            module="JsonUtils",
                            items=[
                                ImportItem(verb=None, name="parse_json", span=_S),
                                ImportItem(verb=None, name="JsonError", span=_S),
                            ],
                            span=_S,
                        ),
                    ],
                    types=[],
                    constants=[],
                    invariants=[],
                    foreign_blocks=[],
                    body=[
                        FunctionDef(
                            verb="creates",
                            name="main_func",
                            params=[],
                            return_type=SimpleType("String", _S),
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
                            body=[ExprStmt(IdentifierExpr("test", _S), _S)],
                            doc_comment=None,
                            span=_S,
                        ),
                    ],
                    span=_S,
                )
            ],
            span=_S,
        )

        checker = Checker(package_modules=package_modules)
        symbols = checker.check(user_module)

        # Should not have E314 "unknown module" errors
        e314_errors = [d for d in checker.diagnostics if d.code == "E314"]
        assert len(e314_errors) == 0, f"unexpected E314 errors: {e314_errors}"

        # parse_json should be resolvable
        sig = symbols.resolve_function("creates", "parse_json", 1)
        assert sig is not None
        assert sig.name == "parse_json"

        # JsonError type should be registered
        resolved_type = symbols.resolve_type("JsonError")
        assert resolved_type is not None


def test_load_package_for_emit():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pkg_path = _create_test_package(tmpdir)

        info = PackageModuleInfo(
            package_name="json-utils",
            package_version="0.3.0",
            module_name="JsonUtils",
            pkg_path=pkg_path,
        )

        module, symbols = load_package_for_emit(info)
        assert isinstance(module, Module)
        assert len(module.declarations) == 1
