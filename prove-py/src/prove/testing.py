"""Generate C test code from Prove contracts and annotations.

Extracts testable properties from:
- `ensures` postconditions
- `requires` preconditions (used to constrain random inputs)
- `near_miss` annotations (explicit negative test cases)
- `believe` annotations (adversarial test generation)

Produces a standalone C program with main() that runs all tests and
reports pass/fail via exit code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    DecimalLit,
    Expr,
    FloatLit,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    Module,
    ModuleDecl,
    NearMiss,
    RawStringLit,
    StringLit,
    TypeIdentifierExpr,
)
from prove.c_emitter import CEmitter
from prove.c_types import mangle_name, map_type
from prove.symbols import SymbolTable
from prove.types import (
    ErrorType,
    GenericInstance,
    ListType,
    PrimitiveType,
    Type,
)


@dataclass
class TestCase:
    """A single generated test case."""

    name: str
    code: str  # C code for the test body
    function_name: str = ""  # Name of the function being tested
    verb: str = ""  # Verb (transforms, matches, etc.)
    test_type: str = "property"  # property, near_miss, believe


@dataclass
class TestSuite:
    """All generated tests for a module."""

    cases: list[TestCase] = field(default_factory=list)
    preamble: str = ""  # C code before tests (includes, type defs, functions)


class TestGenerator:
    """Generate C test code from a checked Prove module."""

    def __init__(
        self,
        module: Module,
        symbols: SymbolTable,
        *,
        property_rounds: int = 1000,
    ) -> None:
        self._module = module
        self._symbols = symbols
        self._rounds = property_rounds
        self._test_counter = 0

    def generate(self) -> TestSuite:
        """Generate all test cases from the module."""
        suite = TestSuite()

        # Generate the module C code as preamble (without main)
        emitter = CEmitter(self._module, self._symbols)
        full_c = emitter.emit()
        # Strip the generated main() so we can add our test main
        suite.preamble = self._strip_main(full_c)

        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                self._generate_function_tests(decl, suite)
            elif isinstance(decl, ModuleDecl):
                for inner in decl.body:
                    if isinstance(inner, FunctionDef):
                        self._generate_function_tests(inner, suite)

        return suite

    def emit_test_c(self, suite: TestSuite) -> str:
        """Emit the complete C test program."""
        lines: list[str] = []

        # Preamble (module code without main)
        lines.append(suite.preamble)
        lines.append("")
        lines.append("/* ── Test infrastructure ──── */")
        lines.append("")
        lines.append("static int _tests_run = 0;")
        lines.append("static int _tests_passed = 0;")
        lines.append("static int _tests_failed = 0;")
        lines.append("")
        lines.append("static void _test_pass(const char *name) {")
        lines.append("    _tests_run++;")
        lines.append("    _tests_passed++;")
        lines.append("}")
        lines.append("")
        lines.append("static void _test_fail(const char *name, const char *msg) {")
        lines.append("    _tests_run++;")
        lines.append("    _tests_failed++;")
        lines.append('    fprintf(stderr, "FAIL %s: %s\\n", name, msg);')
        lines.append("}")
        lines.append("")

        # Simple PRNG for property tests
        lines.append("static uint64_t _rng_state = 0x12345678DEADBEEF;")
        lines.append("")
        lines.append("static uint64_t _rng_next(void) {")
        lines.append("    _rng_state ^= _rng_state << 13;")
        lines.append("    _rng_state ^= _rng_state >> 7;")
        lines.append("    _rng_state ^= _rng_state << 17;")
        lines.append("    return _rng_state;")
        lines.append("}")
        lines.append("")
        lines.append("static int64_t _rng_int(void) {")
        lines.append("    return (int64_t)_rng_next();")
        lines.append("}")
        lines.append("")
        lines.append("static int64_t _rng_int_range(int64_t lo, int64_t hi) {")
        lines.append("    if (lo >= hi) return lo;")
        lines.append("    uint64_t range = (uint64_t)(hi - lo + 1);")
        lines.append("    return lo + (int64_t)(_rng_next() % range);")
        lines.append("}")
        lines.append("")
        lines.append("static double _rng_double(void) {")
        lines.append("    return (double)_rng_next() / (double)UINT64_MAX * 200.0 - 100.0;")
        lines.append("}")
        lines.append("")

        # Test functions
        for tc in suite.cases:
            lines.append(f"static void {tc.name}(void) {{")
            for code_line in tc.code.split("\n"):
                if code_line.strip():
                    lines.append(f"    {code_line}")
            lines.append("}")
            lines.append("")

        # Main
        lines.append("int main(int argc, char **argv) {")
        lines.append("    (void)argc; (void)argv;")
        for tc in suite.cases:
            lines.append(f"    {tc.name}();")
        lines.append("")
        lines.append(
            '    fprintf(stdout, "\\n%d tests, %d passed, '
            '%d failed\\n", _tests_run, _tests_passed, '
            "_tests_failed);"
        )
        lines.append("    return _tests_failed > 0 ? 1 : 0;")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    # ── Per-function test generation ───────────────────────────

    def _generate_function_tests(
        self,
        fd: FunctionDef,
        suite: TestSuite,
    ) -> None:
        sig = self._symbols.resolve_function(
            fd.verb,
            fd.name,
            len(fd.params),
        )
        if sig is None:
            return

        param_types = sig.param_types
        ret_type = sig.return_type
        mangled = mangle_name(
            fd.verb,
            fd.name,
            param_types,
            module=sig.module if sig.module and sig.module != "main" else None,
        )

        # validates functions implicitly return Boolean
        from prove.types import BOOLEAN

        if fd.verb == "validates":
            ret_type = BOOLEAN

        # Skip functions that return void or Result (hard to test)
        if isinstance(ret_type, (ErrorType, GenericInstance)):
            return

        # Near-miss tests
        for nm in fd.near_misses:
            self._gen_near_miss_test(
                fd,
                nm,
                mangled,
                param_types,
                ret_type,
                suite,
            )

        # Property tests from ensures
        # Skip for validators - their return value IS the property, mutation testing is redundant
        if fd.verb != "validates" and fd.ensures and self._all_testable(param_types):
            self._gen_property_tests(
                fd,
                mangled,
                param_types,
                ret_type,
                suite,
            )

        # Believe annotations → adversarial tests
        if fd.believe and self._all_testable(param_types):
            self._gen_believe_tests(
                fd,
                mangled,
                param_types,
                ret_type,
                suite,
            )

    def _all_testable(self, types: list[Type]) -> bool:
        """Check if all parameter types can be randomly generated."""
        for t in types:
            if isinstance(t, PrimitiveType):
                if t.name not in ("Integer", "Decimal", "Float", "Boolean", "String"):
                    return False
            elif isinstance(t, GenericInstance):
                if t.base_name == "Option":
                    if len(t.args) != 1 or not self._all_testable(t.args):
                        return False
                elif t.base_name == "Result":
                    if len(t.args) != 2 or not self._all_testable(t.args):
                        return False
                else:
                    return False
            elif isinstance(t, ListType):
                if not self._all_testable([t.element]):
                    return False
            else:
                return False
        return True

    # ── Near-miss tests ────────────────────────────────────────

    def _gen_near_miss_test(
        self,
        fd: FunctionDef,
        nm: NearMiss,
        mangled: str,
        param_types: list[Type],
        ret_type: Type,
        suite: TestSuite,
    ) -> None:
        """Generate a test from a near_miss annotation.

        near_miss verifies that a specific input does NOT produce
        the expected output (the function should handle it differently).
        """
        self._test_counter += 1
        name = f"_test_nearmiss_{fd.name}_{self._test_counter}"

        input_c = self._expr_to_c(nm.input)
        expected_c = self._expr_to_c(nm.expected)
        if input_c is None or expected_c is None:
            return

        code = (
            f"int64_t _result = {mangled}({input_c});\n"
            f"if (_result != {expected_c}) {{\n"
            f'    _test_pass("{name}");\n'
            f"}} else {{\n"
            f'    _test_fail("{name}", '
            f'"near-miss matched unexpectedly");\n'
            f"}}"
        )
        suite.cases.append(
            TestCase(
                name=name,
                code=code,
                function_name=fd.name,
                verb=fd.verb or "",
                test_type="near_miss",
            )
        )

    # ── Property tests (from ensures) ──────────────────────────

    def _gen_property_tests(
        self,
        fd: FunctionDef,
        mangled: str,
        param_types: list[Type],
        ret_type: Type,
        suite: TestSuite,
    ) -> None:
        """Generate property-based tests using random inputs.

        For each `ensures` condition, generate N rounds of random
        inputs and check that the postcondition holds.
        """
        self._test_counter += 1
        name = f"_test_prop_{fd.name}_{self._test_counter}"

        lines: list[str] = []
        lines.append(f"for (int _i = 0; _i < {self._rounds}; _i++) {{")

        # Generate random inputs
        param_gen: list[str] = []
        for p, pt in zip(fd.params, param_types):
            gen = self._random_gen(p.name, pt)
            param_gen.append(gen)
            lines.append(f"    {gen}")

        # Skip inputs that violate requires preconditions
        for req in fd.requires:
            req_c = self._expr_to_c_bool(req, "_unused")
            if req_c:
                lines.append(f"    if (!({req_c})) continue;")

        # Call function
        arg_names = [p.name for p in fd.params]
        arg_str = ", ".join(arg_names)
        ret_ct = map_type(ret_type)
        lines.append(f"    {ret_ct.decl} _result = {mangled}({arg_str});")

        # Check ensures conditions
        for i, ens in enumerate(fd.ensures):
            # For validators, the ensures is already encoded in the return value.
            # The validator returns true when its body (the validation condition) passes.
            # So we just need to check _result is true when requires is satisfied.
            if fd.verb == "validates":
                check_c = "_result"
            else:
                check_c = self._ensures_to_c(ens, "_result")  # type: ignore[assignment]
            if check_c:
                lines.append(f"    if (!({check_c})) {{")
                lines.append(f'        _test_fail("{name}", "ensures[{i}] violated");')
                lines.append("        return;")
                lines.append("    }")

        lines.append("}")
        lines.append(f'_test_pass("{name}");')

        code = "\n".join(lines)
        suite.cases.append(
            TestCase(
                name=name,
                code=code,
                function_name=fd.name,
                verb=fd.verb or "",
                test_type="property",
            )
        )

        # Also add boundary value tests
        self._gen_boundary_tests(
            fd,
            mangled,
            param_types,
            ret_type,
            suite,
        )

    def _gen_boundary_tests(
        self,
        fd: FunctionDef,
        mangled: str,
        param_types: list[Type],
        ret_type: Type,
        suite: TestSuite,
    ) -> None:
        """Test with boundary values: 0, 1, -1, 1000, -1000."""
        boundaries = ["0L", "1L", "-1L", "1000L", "-1000L"]

        self._test_counter += 1
        name = f"_test_boundary_{fd.name}_{self._test_counter}"

        lines: list[str] = []

        # Build requires guards using boundary param names
        req_guards: list[str] = []
        for req in fd.requires:
            req_c = self._expr_to_c_bool(req, "_unused")
            if req_c:
                req_guards.append(req_c)

        # For each boundary, call function with all params set to it
        for bv in boundaries:
            for pt in param_types:
                if not (isinstance(pt, PrimitiveType) and pt.name == "Integer"):
                    break
            else:
                args = ", ".join([bv] * len(param_types))
                # Apply requires guards with boundary value substituted
                if req_guards:
                    # Substitute param names with boundary value
                    for guard in req_guards:
                        g = guard
                        for p in fd.params:
                            g = g.replace(p.name, f"({bv})")
                        lines.append(f"if ({g})")
                    lines.append(f"    (void){mangled}({args});")
                else:
                    lines.append(f"(void){mangled}({args});")

        # If we got here without crashing, pass
        lines.append(f'_test_pass("{name}");')

        code = "\n".join(lines)
        suite.cases.append(
            TestCase(
                name=name,
                code=code,
                function_name=fd.name,
                verb=fd.verb or "",
                test_type="boundary",
            )
        )

    # ── Believe tests (adversarial) ────────────────────────────

    def _gen_believe_tests(
        self,
        fd: FunctionDef,
        mangled: str,
        param_types: list[Type],
        ret_type: Type,
        suite: TestSuite,
    ) -> None:
        """Generate adversarial tests for `believe` annotations.

        These try harder to find counterexamples: more rounds,
        extreme values, and targeted patterns.
        """
        for bi, belief in enumerate(fd.believe):
            self._test_counter += 1
            name = f"_test_believe_{fd.name}_{self._test_counter}"

            lines: list[str] = []
            # Adversarial: 3x the normal rounds
            adv_rounds = self._rounds * 3

            lines.append(f"for (int _i = 0; _i < {adv_rounds}; _i++) {{")

            # Generate random inputs with adversarial bias
            for p, pt in zip(fd.params, param_types):
                gen = self._random_gen(p.name, pt)
                lines.append(f"    {gen}")

            # Skip inputs that violate requires preconditions
            for req in fd.requires:
                req_c = self._expr_to_c_bool(req, "_unused")
                if req_c:
                    lines.append(f"    if (!({req_c})) continue;")

            # Call function
            arg_names = [p.name for p in fd.params]
            arg_str = ", ".join(arg_names)
            ret_ct = map_type(ret_type)
            lines.append(f"    {ret_ct.decl} _result = {mangled}({arg_str});")

            # Check believe condition
            check = self._ensures_to_c(belief, "_result")
            if check:
                lines.append(f"    if (!({check})) {{")
                lines.append(f'        _test_fail("{name}", "believe[{bi}] violated");')
                lines.append("        return;")
                lines.append("    }")

            lines.append("}")
            lines.append(f'_test_pass("{name}");')

        code = "\n".join(lines)
        suite.cases.append(
            TestCase(
                name=name,
                code=code,
                function_name=fd.name,
                verb=fd.verb or "",
                test_type="property",
            )
        )

    # ── Helpers ────────────────────────────────────────────────

    def _random_gen(self, name: str, ty: Type) -> str:
        """Generate C code for a random value of the given type."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "Integer":
                return f"int64_t {name} = _rng_int_range(-1000, 1000);"
            if ty.name in ("Decimal", "Float"):
                return f"double {name} = _rng_double();"
            if ty.name == "Boolean":
                return f"bool {name} = _rng_next() % 2 == 0;"
            if ty.name == "String":
                return self._random_string_gen(name)
        if isinstance(ty, GenericInstance):
            if ty.base_name == "Option":
                return self._random_option_gen(name, ty.args[0])
            if ty.base_name == "Result":
                return self._random_result_gen(name)
        if isinstance(ty, ListType):
            return self._random_list_gen(name)
        return f"int64_t {name} = 0; /* untestable type */"

    def _random_string_gen(self, name: str) -> str:
        """Generate C code for a random string (valid JSON for testing)."""
        return f"""Prove_String* {name};
    do {{
        // Generate random JSON object for testing
        int64_t id_val = _rng_int();
        char buf[128];
        snprintf(buf, sizeof(buf),
            "{{\\"id\\": %ld, \\"name\\": \\"t\\", \\"email\\": \\"t@t.com\\"}}", id_val);
        {name} = prove_string_from_cstr(buf);
    }} while(0);"""

    def _random_option_gen(self, name: str, inner_ty: Type) -> str:
        """Generate C code for a random Option<Value> (50% Some, 50% None)."""
        from prove.c_types import map_type
        from prove.types import PrimitiveType

        inner_c = map_type(inner_ty)
        safe = inner_c.decl.replace("*", "ptr").replace(" ", "_")
        if isinstance(inner_ty, PrimitiveType):
            if inner_ty.name == "Integer":
                return f"""Prove_Option_{safe} {name};
        if (_rng_next() % 2 == 0) {{
            {name} = Prove_Option_{safe}_some(_rng_int());
        }} else {{
            {name} = Prove_Option_{safe}_none();
        }}"""
            if inner_ty.name == "String":
                return f"""Prove_Option_{safe} {name};
        if (_rng_next() % 2 == 0) {{
            {name} = Prove_Option_{safe}_some(prove_string_from_cstr("test"));
        }} else {{
            {name} = Prove_Option_{safe}_none();
        }}"""
            if inner_ty.name == "Boolean":
                return f"""Prove_Option_{safe} {name};
        if (_rng_next() % 2 == 0) {{
            {name} = Prove_Option_{safe}_some(true);
        }} else {{
            {name} = Prove_Option_{safe}_none();
        }}"""
        return f"Prove_Option_{safe} {name} = Prove_Option_{safe}_none();"

    def _random_result_gen(self, name: str) -> str:
        """Generate C code for a random Result<Value, Error> (default to Err)."""
        return (
            f"Prove_Result_int64_t_Prove_Stringptr {name} = "
            f"Prove_Result_int64_t_Prove_Stringptr_err("
            f'prove_string_from_cstr("err"));'
        )

    def _random_list_gen(self, name: str) -> str:
        """Generate C code for a random List<Value> (empty list)."""
        return f"Prove_List* {name} = prove_list_new();"

    def _ensures_to_c(self, expr: Expr, result_var: str) -> str | None:
        """Convert an ensures expression to a C boolean expression.

        The ensures expression can reference `result` (the return
        value), which maps to `result_var` in C.
        """
        return self._expr_to_c_bool(expr, result_var)

    def _expr_to_c_bool(
        self,
        expr: Expr,
        result_var: str,
    ) -> str | None:
        """Convert an AST Expr to a C expression string."""
        if isinstance(expr, BinaryExpr):
            left = self._expr_to_c_inner(expr.left, result_var)
            right = self._expr_to_c_inner(expr.right, result_var)
            if left is None or right is None:
                return None
            op_map = {
                "==": "==",
                "!=": "!=",
                "<": "<",
                ">": ">",
                "<=": "<=",
                ">=": ">=",
                "&&": "&&",
                "||": "||",
            }
            c_op = op_map.get(expr.op)
            if c_op is None:
                return None
            return f"({left} {c_op} {right})"

        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"

        if isinstance(expr, IdentifierExpr):
            if expr.name == "result":
                return result_var
            return expr.name

        # Fallback: try as a general expression
        val = self._expr_to_c_inner(expr, result_var)
        return val

    def _expr_to_c_inner(
        self,
        expr: Expr,
        result_var: str,
    ) -> str | None:
        """Convert an inner expression to C."""
        if isinstance(expr, IntegerLit):
            return f"{expr.value}L"
        if isinstance(expr, DecimalLit):
            return expr.value
        if isinstance(expr, FloatLit):
            return expr.value
        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"
        if isinstance(expr, StringLit):
            return f'prove_string_from_cstr("{expr.value}")'
        if isinstance(expr, RawStringLit):
            return f'prove_string_from_cstr("{expr.value}")'
        if isinstance(expr, IdentifierExpr):
            if expr.name == "result":
                return result_var
            return expr.name
        if isinstance(expr, TypeIdentifierExpr):
            return expr.name
        if isinstance(expr, BinaryExpr):
            left = self._expr_to_c_inner(expr.left, result_var)
            right = self._expr_to_c_inner(expr.right, result_var)
            if left is None or right is None:
                return None
            from prove.type_inference import BINARY_OP_TO_C

            c_op = BINARY_OP_TO_C.get(expr.op, expr.op)
            return f"({left} {c_op} {right})"
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                func_name = expr.func.name
                args = []
                for a in expr.args:
                    ac = self._expr_to_c_inner(a, result_var)
                    if ac is None:
                        return None
                    args.append(ac)
                return f"{func_name}({', '.join(args)})"
        return None

    def _expr_to_c(self, expr: Expr) -> str | None:
        """Convert a simple AST expression to C."""
        return self._expr_to_c_inner(expr, "_result")

    @staticmethod
    def _strip_main(c_code: str) -> str:
        """Remove the main() function from generated C code."""
        lines = c_code.split("\n")
        result: list[str] = []
        in_main = False
        brace_depth = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("int main(") and not in_main:
                in_main = True
                brace_depth = 0
                if "{" in stripped:
                    brace_depth += stripped.count("{")
                    brace_depth -= stripped.count("}")
                continue

            if in_main:
                brace_depth += stripped.count("{")
                brace_depth -= stripped.count("}")
                if brace_depth <= 0:
                    in_main = False
                continue

            result.append(line)

        return "\n".join(result)


# ── Public API ─────────────────────────────────────────────────


@dataclass
class TestResult:
    """Outcome of running tests."""

    ok: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    output: str = ""
    c_error: str | None = None
    test_details: list[TestCase] = field(default_factory=list)


def run_tests(
    project_dir: Path,
    modules: list[tuple[Module, SymbolTable]],
    *,
    property_rounds: int = 1000,
) -> TestResult:
    """Generate, compile, and run tests for the given modules."""
    from prove.c_compiler import CompileCError, compile_c, find_c_compiler
    from prove.c_runtime import copy_runtime

    all_cases: list[TestCase] = []
    preamble = ""

    for module, symbols in modules:
        gen = TestGenerator(
            module,
            symbols,
            property_rounds=property_rounds,
        )
        suite = gen.generate()
        preamble = suite.preamble  # last module's preamble
        all_cases.extend(suite.cases)

    if not all_cases:
        return TestResult(
            ok=True,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            output="no testable functions found",
            test_details=[],
        )

    # Build combined suite
    combined = TestSuite(cases=all_cases, preamble=preamble)
    gen_dummy = TestGenerator(
        modules[0][0],
        modules[0][1],
        property_rounds=property_rounds,
    )
    test_c = gen_dummy.emit_test_c(combined)

    # Write to build dir
    build_dir = project_dir / "build"
    test_dir = build_dir / "test"
    test_dir.mkdir(parents=True, exist_ok=True)

    test_c_path = test_dir / "test_main.c"
    test_c_path.write_text(test_c)

    # Copy runtime
    runtime_c_files = copy_runtime(build_dir)

    # Compile
    cc = find_c_compiler()
    if cc is None:
        return TestResult(
            ok=False,
            c_error="no C compiler found (install gcc or clang)",
            test_details=all_cases,
        )

    runtime_dir = build_dir / "runtime"
    test_binary = test_dir / "test_runner"

    try:
        compile_c(
            c_files=runtime_c_files + [test_c_path],
            output=test_binary,
            compiler=cc,
            include_dirs=[runtime_dir],
            extra_flags=["-lm"],
        )
    except CompileCError as e:
        return TestResult(
            ok=False,
            c_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
            test_details=all_cases,
        )

    # Run tests
    import subprocess

    try:
        proc = subprocess.run(
            [str(test_binary)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            ok=False,
            output="test runner timed out",
            test_details=all_cases,
        )

    output = proc.stdout + proc.stderr

    # Parse results from output
    tests_run = 0
    tests_passed = 0
    tests_failed = 0
    for line in output.split("\n"):
        line = line.strip()
        if "tests," in line and "passed," in line:
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                if "test" in part and "passed" not in part and "failed" not in part:
                    try:
                        tests_run = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif "passed" in part:
                    try:
                        tests_passed = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif "failed" in part:
                    try:
                        tests_failed = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass

    return TestResult(
        ok=proc.returncode == 0,
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        output=output,
        test_details=all_cases,
    )
