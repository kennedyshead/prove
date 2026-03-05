"""AST mutation engine for mutation testing.

Generates small code modifications (mutants) from Prove source code:
- Operator swaps (+ → -, * → /, etc.)
- Constant value changes (0→1, true→false)
- Condition negation
- Branch removal in match expressions
- Return value changes
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    Expr,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    Module,
    Stmt,
    UnaryExpr,
)
from prove.source import Span
from prove.symbols import SymbolTable


@dataclass
class Mutant:
    """A single mutation variant of the source code."""

    id: str
    description: str
    module: Module
    mutated_location: Span


@dataclass
class MutationResult:
    """Result of generating mutations for a module."""

    mutants: list[Mutant] = field(default_factory=list)


class Mutator:
    """Generate mutation variants from a Prove module."""

    OPERATOR_MUTATIONS = {
        "+": ["-", "*", "/"],
        "-": ["+", "*", "/"],
        "*": ["+", "-", "/"],
        "/": ["+", "-", "*"],
        "%": ["+", "-", "*", "/"],
        "==": ["!=", "<", ">", "<=", ">="],
        "!=": ["==", "<", ">", "<=", ">="],
        "<": ["<=", "==", "!="],
        ">": [">=", "==", "!="],
        "<=": ["<", "==", "!="],
        ">=": [">", "==", "!="],
        "&&": ["||"],
        "||": ["&&"],
    }

    def __init__(self, module: Module, seed: int | None = None) -> None:
        self._module = module
        self._rng = random.Random(seed)
        self._mutant_counter = 0

    def generate_mutants(
        self,
        *,
        max_mutants: int = 50,
        operator_mutations: bool = True,
        constant_mutations: bool = True,
        condition_mutations: bool = True,
    ) -> MutationResult:
        """Generate all possible mutants for the module."""
        result = MutationResult()

        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                mutants = self._mutate_function(
                    decl,
                    operator_mutations=operator_mutations,
                    constant_mutations=constant_mutations,
                    condition_mutations=condition_mutations,
                )
                result.mutants.extend(mutants)

                if len(result.mutants) >= max_mutants:
                    break

        return result

    def _mutate_function(
        self,
        fd: FunctionDef,
        *,
        operator_mutations: bool,
        constant_mutations: bool,
        condition_mutations: bool,
    ) -> list[Mutant]:
        """Generate mutants for a function."""
        mutants: list[Mutant] = []
        body = fd.body

        # Skip single-line validators - their return value already encodes the property
        # Also skip inputs with no parameters - nothing meaningful to mutate
        if len(body) == 1 and fd.verb == "validates":
            return mutants
        if len(body) == 1 and fd.can_fail:
            return mutants
        if fd.verb == "inputs" and not fd.params:
            return mutants

        for i, stmt in enumerate(body):
            if operator_mutations:
                mutants.extend(self._mutate_binary_operators(stmt, fd, i))

            if constant_mutations:
                mutants.extend(self._mutate_constants(stmt, fd, i))

            if condition_mutations:
                mutants.extend(self._mutate_conditions(stmt, fd, i))

        return mutants

    def _mutate_binary_operators(
        self,
        stmt: Stmt,
        fd: FunctionDef,
        stmt_idx: int,
    ) -> list[Mutant]:
        """Generate operator swap mutations."""
        mutants: list[Mutant] = []
        exprs = self._collect_expressions(stmt)

        for expr in exprs:
            if isinstance(expr, BinaryExpr):
                if expr.op in self.OPERATOR_MUTATIONS:
                    for new_op in self.OPERATOR_MUTATIONS[expr.op]:
                        self._mutant_counter += 1
                        mutant_id = f"M{self._mutant_counter:04d}"

                        mutated_module = self._copy_with_operator_swap(
                            self._module, fd, stmt_idx, expr, new_op
                        )

                        mutants.append(
                            Mutant(
                                id=mutant_id,
                                description=f"{fd.name}: {expr.op} → {new_op}",
                                module=mutated_module,
                                mutated_location=expr.span,
                            )
                        )

        return mutants

    def _mutate_constants(
        self,
        stmt: Stmt,
        fd: FunctionDef,
        stmt_idx: int,
    ) -> list[Mutant]:
        """Generate constant value mutations."""
        mutants: list[Mutant] = []
        exprs = self._collect_expressions(stmt)

        for expr in exprs:
            if isinstance(expr, IntegerLit):
                if expr.value == "0" or expr.value == "1":
                    new_value = "0" if expr.value == "1" else "1"
                    self._mutant_counter += 1
                    mutant_id = f"M{self._mutant_counter:04d}"

                    mutated_module = self._copy_with_constant_change(
                        self._module, fd, stmt_idx, expr, new_value
                    )

                    mutants.append(
                        Mutant(
                            id=mutant_id,
                            description=f"{fd.name}: integer {expr.value} → {new_value}",
                            module=mutated_module,
                            mutated_location=expr.span,
                        )
                    )

            elif isinstance(expr, BooleanLit):
                new_value = not expr.value
                self._mutant_counter += 1
                mutant_id = f"M{self._mutant_counter:04d}"

                mutated_module = self._copy_with_boolean_flip(self._module, fd, stmt_idx, expr)

                mutants.append(
                    Mutant(
                        id=mutant_id,
                        description=f"{fd.name}: boolean {expr.value} → {new_value}",
                        module=mutated_module,
                        mutated_location=expr.span,
                    )
                )

        return mutants

    def _mutate_conditions(
        self,
        stmt: Stmt,
        fd: FunctionDef,
        stmt_idx: int,
    ) -> list[Mutant]:
        """Generate condition negation and branch mutations."""
        mutants: list[Mutant] = []
        exprs = self._collect_expressions(stmt)

        for expr in exprs:
            if isinstance(expr, BinaryExpr) and expr.op in ("==", "!=", "<", ">", "<=", ">="):
                negated_op = self._negate_comparison(expr.op)
                if negated_op:
                    self._mutant_counter += 1
                    mutant_id = f"M{self._mutant_counter:04d}"

                    mutated_module = self._copy_with_operator_swap(
                        self._module, fd, stmt_idx, expr, negated_op
                    )

                    mutants.append(
                        Mutant(
                            id=mutant_id,
                            description=f"{fd.name}: {expr.op} → {negated_op} (negated)",
                            module=mutated_module,
                            mutated_location=expr.span,
                        )
                    )

            if isinstance(expr, UnaryExpr) and expr.op == "!":
                inner = expr.operand
                if isinstance(inner, IdentifierExpr):
                    self._mutant_counter += 1
                    mutant_id = f"M{self._mutant_counter:04d}"

                    mutated_module = self._copy_with_unary_remove(self._module, fd, stmt_idx, expr)

                    mutants.append(
                        Mutant(
                            id=mutant_id,
                            description=f"{fd.name}: removed negation",
                            module=mutated_module,
                            mutated_location=expr.span,
                        )
                    )

        return mutants

    def _negate_comparison(self, op: str) -> str | None:
        """Negate a comparison operator."""
        negation_map = {
            "==": "!=",
            "!=": "==",
            "<": ">=",
            ">": "<=",
            "<=": ">",
            ">=": "<",
        }
        return negation_map.get(op)

    def _collect_expressions(self, stmt: Stmt) -> list[Expr]:
        """Recursively collect all expressions from a statement."""
        exprs: list[Expr] = []

        def walk(e: Expr) -> None:
            exprs.append(e)
            if isinstance(e, BinaryExpr):
                walk(e.left)
                walk(e.right)
            elif isinstance(e, UnaryExpr):
                walk(e.operand)
            elif isinstance(e, IdentifierExpr):
                pass

        from prove.ast_nodes import Assignment, ExprStmt, FieldAssignment, VarDecl

        if isinstance(stmt, ExprStmt):
            walk(stmt.expr)
        elif isinstance(stmt, VarDecl):
            walk(stmt.value)
        elif isinstance(stmt, Assignment):
            walk(stmt.value)
        elif isinstance(stmt, FieldAssignment):
            walk(stmt.value)

        return exprs

    def _copy_with_operator_swap(
        self,
        module: Module,
        fd: FunctionDef,
        stmt_idx: int,
        expr: BinaryExpr,
        new_op: str,
    ) -> Module:
        """Create a module copy with an operator swapped."""
        from copy import deepcopy

        mutated = deepcopy(module)

        for decl in mutated.declarations:
            if isinstance(decl, FunctionDef) and decl.name == fd.name:
                for i, stmt in enumerate(decl.body):
                    if i == stmt_idx:
                        self._swap_operator_in_stmt(stmt, expr, new_op)
                break

        return mutated

    def _swap_operator_in_stmt(self, stmt: Stmt, target: Expr, new_op: str) -> None:
        """Recursively swap operator in a statement."""
        from prove.ast_nodes import Assignment, ExprStmt, VarDecl

        if isinstance(stmt, ExprStmt):
            self._swap_operator_in_expr(stmt.expr, target, new_op)
        elif isinstance(stmt, VarDecl):
            self._swap_operator_in_expr(stmt.value, target, new_op)
        elif isinstance(stmt, Assignment):
            self._swap_operator_in_expr(stmt.value, target, new_op)

    def _swap_operator_in_expr(self, expr: Expr, target: BinaryExpr, new_op: str) -> None:
        """Recursively swap operator in an expression."""
        if isinstance(expr, BinaryExpr):
            if expr.span == target.span:
                object.__setattr__(expr, "op", new_op)
            self._swap_operator_in_expr(expr.left, target, new_op)
            self._swap_operator_in_expr(expr.right, target, new_op)

    def _copy_with_constant_change(
        self,
        module: Module,
        fd: FunctionDef,
        stmt_idx: int,
        expr: IntegerLit,
        new_value: str,
    ) -> Module:
        """Create a module copy with a constant changed."""
        from copy import deepcopy

        mutated = deepcopy(module)

        for decl in mutated.declarations:
            if isinstance(decl, FunctionDef) and decl.name == fd.name:
                for i, stmt in enumerate(decl.body):
                    if i == stmt_idx:
                        self._change_constant_in_stmt(stmt, expr, new_value)
                break

        return mutated

    def _change_constant_in_stmt(self, stmt: Stmt, target: IntegerLit, new_value: str) -> None:
        """Recursively change constant in a statement."""
        from prove.ast_nodes import Assignment, ExprStmt, VarDecl

        if isinstance(stmt, ExprStmt):
            self._change_constant_in_expr(stmt.expr, target, new_value)
        elif isinstance(stmt, VarDecl):
            self._change_constant_in_expr(stmt.value, target, new_value)
        elif isinstance(stmt, Assignment):
            self._change_constant_in_expr(stmt.value, target, new_value)

    def _change_constant_in_expr(self, expr: Expr, target: IntegerLit, new_value: str) -> None:
        """Recursively change constant in an expression."""
        if isinstance(expr, IntegerLit):
            if expr.span == target.span:
                object.__setattr__(expr, "value", new_value)

    def _copy_with_boolean_flip(
        self,
        module: Module,
        fd: FunctionDef,
        stmt_idx: int,
        expr: BooleanLit,
    ) -> Module:
        """Create a module copy with a boolean flipped."""
        from copy import deepcopy

        mutated = deepcopy(module)

        for decl in mutated.declarations:
            if isinstance(decl, FunctionDef) and decl.name == fd.name:
                for i, stmt in enumerate(decl.body):
                    if i == stmt_idx:
                        self._flip_boolean_in_stmt(stmt, expr)
                break

        return mutated

    def _flip_boolean_in_stmt(self, stmt: Stmt, target: BooleanLit) -> None:
        """Recursively flip boolean in a statement."""
        from prove.ast_nodes import Assignment, ExprStmt, VarDecl

        if isinstance(stmt, ExprStmt):
            self._flip_boolean_in_expr(stmt.expr, target)
        elif isinstance(stmt, VarDecl):
            self._flip_boolean_in_expr(stmt.value, target)
        elif isinstance(stmt, Assignment):
            self._flip_boolean_in_expr(stmt.value, target)

    def _flip_boolean_in_expr(self, expr: Expr, target: BooleanLit) -> None:
        """Recursively flip boolean in an expression."""
        if isinstance(expr, BooleanLit):
            if expr.span == target.span:
                object.__setattr__(expr, "value", not expr.value)

    def _copy_with_unary_remove(
        self,
        module: Module,
        fd: FunctionDef,
        stmt_idx: int,
        expr: UnaryExpr,
    ) -> Module:
        """Create a module copy with a unary negation removed."""
        from copy import deepcopy

        mutated = deepcopy(module)

        for decl in mutated.declarations:
            if isinstance(decl, FunctionDef) and decl.name == fd.name:
                for i, stmt in enumerate(decl.body):
                    if i == stmt_idx:
                        self._remove_negation_in_stmt(stmt, expr)
                break

        return mutated

    def _remove_negation_in_stmt(self, stmt: Stmt, target: UnaryExpr) -> None:
        """Recursively remove negation in a statement."""
        from prove.ast_nodes import Assignment, ExprStmt, VarDecl

        if isinstance(stmt, ExprStmt):
            self._remove_negation_in_expr(stmt.expr, target)
        elif isinstance(stmt, VarDecl):
            self._remove_negation_in_expr(stmt.value, target)
        elif isinstance(stmt, Assignment):
            self._remove_negation_in_expr(stmt.value, target)

    def _remove_negation_in_expr(self, expr: Expr, target: UnaryExpr) -> None:
        """Recursively remove negation in an expression."""
        if isinstance(expr, UnaryExpr):
            if expr.span == target.span:
                if isinstance(expr.operand, IdentifierExpr):
                    object.__setattr__(expr, "op", "")
            self._remove_negation_in_expr(expr.operand, target)


@dataclass
class MutationTestResult:
    """Result of running mutation tests."""

    total_mutants: int = 0
    killed_mutants: int = 0
    survived_mutants: int = 0
    error_mutants: int = 0
    mutation_score: float = 0.0
    survivors: list[dict] = field(default_factory=list)


def run_mutation_tests(
    project_dir: Path,
    modules: list[tuple[Module, "SymbolTable"]],
    *,
    max_mutants: int = 50,
    property_rounds: int = 100,
) -> MutationTestResult:
    """Run mutation testing on the project.

    For each mutant:
    1. Generate mutated C code
    2. Compile the mutant
    3. Run tests against the mutant
    4. Check if tests kill the mutant
    """
    from prove.testing import TestGenerator, run_tests

    result = MutationTestResult()
    all_mutants: list[tuple[Module, SymbolTable, Mutant]] = []

    for module, symbols in modules:
        mutator = Mutator(module)
        mutation_result = mutator.generate_mutants(max_mutants=max_mutants)
        for mutant in mutation_result.mutants:
            all_mutants.append((mutant.module, symbols, mutant))

    result.total_mutants = len(all_mutants)

    if not all_mutants:
        return result

    for mutant_module, symbols, mutant in all_mutants:
        try:
            test_gen = TestGenerator(mutant_module, symbols, property_rounds=property_rounds)
            suite = test_gen.generate()

            if not suite.cases:
                result.error_mutants += 1
                continue

            test_result = run_tests(
                project_dir, [(mutant_module, symbols)], property_rounds=property_rounds
            )

            if test_result.tests_failed > 0:
                result.killed_mutants += 1
            else:
                result.survived_mutants += 1
                result.survivors.append(
                    {
                        "id": mutant.id,
                        "description": mutant.description,
                        "location": (
                            f"{mutant.mutated_location.start_line}:"
                            f"{mutant.mutated_location.start_col}"
                        ),
                    }
                )
        except Exception:
            result.error_mutants += 1

    if result.total_mutants > 0:
        result.mutation_score = result.killed_mutants / result.total_mutants

    return result


def get_survivors_path(project_dir: Path) -> Path:
    """Get the path to the survivors file."""
    prove_dir = project_dir / ".prove"
    prove_dir.mkdir(exist_ok=True)
    return prove_dir / "mutation-survivors.json"


def save_survivors(project_dir: Path, result: MutationTestResult) -> None:
    """Save mutation survivors to a file for future warnings."""
    if not result.survivors:
        return

    path = get_survivors_path(project_dir)
    data = {
        "survivors": result.survivors,
        "total_mutants": result.total_mutants,
        "killed_mutants": result.killed_mutants,
    }
    path.write_text(json.dumps(data, indent=2))


def load_survivors(project_dir: Path) -> list[dict[str, object]]:
    """Load saved mutation survivors."""
    path = get_survivors_path(project_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        result = data.get("survivors", [])
        if isinstance(result, list):
            return result
        return []
    except (json.JSONDecodeError, IOError):
        return []
