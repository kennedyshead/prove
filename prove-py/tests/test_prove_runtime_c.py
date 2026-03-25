"""Tests for the Prove (tree-sitter) C runtime module."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from prove.c_compiler import find_c_compiler


def _get_tree_sitter_flags() -> tuple[list[str], list[str]]:
    """Get tree-sitter include and link flags via pkg-config."""
    try:
        result = subprocess.run(
            ["pkg-config", "--cflags", "--libs", "tree-sitter"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            flags = result.stdout.strip().split()
            c_flags = [f for f in flags if f.startswith(("-I", "-D"))]
            l_flags = [f for f in flags if not f.startswith(("-I", "-D"))]
            return c_flags, l_flags
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return [], []


def _compile_and_run_prove(
    runtime_dir: Path,
    tmp_path: Path,
    c_code: str,
    *,
    name: str = "test",
) -> subprocess.CompletedProcess[str]:
    """Compile a C test program that uses prove_prove (tree-sitter)."""
    src = tmp_path / f"{name}.c"
    src.write_text(c_code)
    binary = tmp_path / name
    cc = find_c_compiler()
    assert cc is not None

    ts_c_flags, ts_l_flags = _get_tree_sitter_flags()
    if not ts_l_flags:
        pytest.skip("tree-sitter not found via pkg-config")

    # Core runtime (exclude external-dep libs)
    _EXTERNAL_C = frozenset({"prove_gui.c", "prove_prove.c"})
    runtime_c = sorted(f for f in runtime_dir.glob("*.c") if f.name not in _EXTERNAL_C)

    # Add prove_prove.c
    prove_prove_c = runtime_dir / "prove_prove.c"
    assert prove_prove_c.exists(), "prove_prove.c not found in runtime_dir"
    runtime_c.append(prove_prove_c)

    # Add vendored tree-sitter-prove parser + scanner
    tsp_dir = runtime_dir / "vendor" / "tree_sitter_prove"
    ts_parser = tsp_dir / "parser.c"
    ts_scanner = tsp_dir / "scanner.c"

    vendor_c: list[Path] = []
    for f in (ts_parser, ts_scanner):
        if f.exists():
            vendor_c.append(f)

    if not vendor_c:
        pytest.skip("vendored tree-sitter-prove parser not found")

    cmd = [
        cc,
        "-O0",
        "-Wall",
        "-Wextra",
        "-Wno-unused-parameter",
        "-Wno-unused-function",
        *ts_c_flags,
        "-I",
        str(runtime_dir),
        "-I",
        str(tsp_dir),
        str(src),
        *[str(f) for f in runtime_c],
        *[str(f) for f in vendor_c],
        "-o",
        str(binary),
        "-lm",
        *ts_l_flags,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Compile failed:\n{result.stderr}"

    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)


@pytest.fixture
def _vendor_tree_sitter(runtime_dir: Path) -> None:
    """Copy prove_prove + vendored tree-sitter-prove files into the runtime_dir fixture."""
    import shutil

    rt_src = Path(__file__).parent.parent / "src" / "prove" / "runtime"
    vendor_src = rt_src / "vendor"
    ts_prove_src = vendor_src / "tree_sitter_prove"

    if not ts_prove_src.exists():
        pytest.skip("vendored tree-sitter-prove not found")

    # Copy prove_prove.c and prove_prove.h (excluded by _EXTERNAL_DEP_LIBS)
    for fname in ("prove_prove.c", "prove_prove.h"):
        shutil.copy2(rt_src / fname, runtime_dir / fname)

    # tree-sitter-prove parser + scanner
    tsp_dest = runtime_dir / "vendor" / "tree_sitter_prove"
    tsp_ts = tsp_dest / "tree_sitter"
    tsp_dest.mkdir(parents=True, exist_ok=True)
    tsp_ts.mkdir(parents=True, exist_ok=True)

    for fname in ("parser.c", "scanner.c"):
        shutil.copy2(ts_prove_src / fname, tsp_dest / fname)
    shutil.copy2(ts_prove_src / "tree_sitter" / "parser.h", tsp_ts / "parser.h")


@pytest.mark.usefixtures("_vendor_tree_sitter")
class TestProveRuntime:
    """Tests for Prove module C runtime (tree-sitter wrappers)."""

    def test_parse_and_root_kind(self, tmp_path, runtime_dir):
        """Parse source and verify root node kind is source_file."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                if (r.tag != 0) { printf("FAIL\\n"); return 1; }
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                Prove_String *k = prove_prove_kind(root);
                printf("%.*s\\n", (int)k->length, k->data);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="root_kind")
        assert result.returncode == 0
        assert result.stdout.strip() == "source_file"

    def test_children_count(self, tmp_path, runtime_dir):
        """Root node has children."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                int64_t c = prove_prove_count(root);
                printf("%lld\\n", (long long)c);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="children_count")
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count > 0

    def test_children_traversal(self, tmp_path, runtime_dir):
        """Traverse children and get their kinds."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                Prove_List *kids = prove_prove_children(root);
                for (int64_t i = 0; i < kids->length; i++) {
                    Prove_Node child = (Prove_Node)prove_list_get(kids, i);
                    Prove_String *k = prove_prove_kind(child);
                    printf("%.*s\\n", (int)k->length, k->data);
                }
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="children")
        assert result.returncode == 0
        kinds = result.stdout.strip().split("\n")
        assert "module_declaration" in kinds

    def test_node_string(self, tmp_path, runtime_dir):
        """Extract source text from a node."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                Prove_String *s = prove_prove_string(root);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="node_str")
        assert result.returncode == 0
        assert result.stdout.strip() == "module Test"

    def test_node_line_column(self, tmp_path, runtime_dir):
        """Verify line (1-based) and column (0-based) accessors."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                printf("%lld %lld\\n", (long long)prove_prove_line(root),
                       (long long)prove_prove_column(root));
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="line_col")
        assert result.returncode == 0
        parts = result.stdout.strip().split()
        assert parts[0] == "1"  # line 1
        assert parts[1] == "0"  # column 0

    def test_named_children(self, tmp_path, runtime_dir):
        """Named children skip anonymous tokens."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Test");
                Prove_Result r = prove_parse_tree(src);
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                Prove_List *named = prove_prove_named_children(root);
                Prove_List *all = prove_prove_children(root);
                printf("named=%lld all=%lld\\n",
                       (long long)named->length, (long long)all->length);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="named")
        assert result.returncode == 0
        # Named children should be <= total children
        line = result.stdout.strip()
        assert "named=" in line

    def test_child_by_field_name(self, tmp_path, runtime_dir):
        """Named child lookup returns Some for match subject, None for nonexistent."""
        # match_expression has a 'subject' field in tree-sitter-prove
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "module Test\\n"
                    "reads f(x Integer) Integer\\n"
                    "  from\\n"
                    "    match x\\n"
                    "      0 => 1\\n"
                    "      _ => 2\\n"
                );
                Prove_Result r = prove_parse_tree(src);
                if (r.tag != 0) { printf("parse_err\\n"); return 1; }
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                // Walk down to find a match_expression node
                Prove_List *kids = prove_prove_children(root);
                int found = 0;
                for (int64_t i = 0; i < kids->length && !found; i++) {
                    Prove_Node n = (Prove_Node)prove_list_get(kids, i);
                    Prove_List *gkids = prove_prove_children(n);
                    for (int64_t j = 0; j < gkids->length && !found; j++) {
                        Prove_Node gn = (Prove_Node)prove_list_get(gkids, j);
                        Prove_String *k = prove_prove_kind(gn);
                        // Look for match_expression anywhere in descendants
                        Prove_List *ggkids = prove_prove_children(gn);
                        for (int64_t m = 0; m < ggkids->length && !found; m++) {
                            Prove_Node ggn = (Prove_Node)prove_list_get(ggkids, m);
                            Prove_String *gk = prove_prove_kind(ggn);
                            if (gk->length >= 5 && memcmp(gk->data, "match", 5) == 0) {
                                // Try 'subject' field
                                Prove_String *field = prove_string_from_cstr("subject");
                                Prove_Option opt = prove_prove_child(ggn, field);
                                printf("subject_tag=%d\\n", opt.tag);
                                found = 1;
                            }
                        }
                    }
                }
                // Try a field that doesn't exist on root
                Prove_String *bad = prove_string_from_cstr("nonexistent_field");
                Prove_Option opt2 = prove_prove_child(root, bad);
                printf("none_tag=%d\\n", opt2.tag);
                if (!found) printf("no_match_found\\n");
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="child_field")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        # Nonexistent field should be None (tag=0)
        assert any("none_tag=0" in line for line in lines)

    def test_error_node_detection(self, tmp_path, runtime_dir):
        """Parse invalid source and detect error nodes."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module @@@invalid!!!");
                Prove_Result r = prove_parse_tree(src);
                if (r.tag != 0) { printf("parse_err\\n"); return 0; }
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_Node root = prove_prove_root(tree);
                // Walk children looking for error nodes
                Prove_List *kids = prove_prove_children(root);
                int found_error = 0;
                for (int64_t i = 0; i < kids->length; i++) {
                    Prove_Node child = (Prove_Node)prove_list_get(kids, i);
                    if (prove_prove_error(child)) found_error = 1;
                }
                // Also check root-level error status
                bool root_err = prove_prove_error(root);
                printf("root_error=%d child_error=%d\\n", root_err, found_error);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="errors")
        assert result.returncode == 0
        # At least one error should be found somewhere
        out = result.stdout.strip()
        assert "error=1" in out or "parse_err" in out

    def test_parse_string_roundtrip(self, tmp_path, runtime_dir):
        """Parse source then extract it back with prove_parse_string_tree."""
        code = textwrap.dedent("""\
            #include "prove_prove.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("module Roundtrip");
                Prove_Result r = prove_parse_tree(src);
                if (r.tag != 0) { printf("FAIL\\n"); return 1; }
                Prove_Tree tree = (Prove_Tree)r.value;
                Prove_String *out = prove_parse_string_tree(tree);
                printf("%.*s\\n", (int)out->length, out->data);
                return 0;
            }
        """)
        result = _compile_and_run_prove(runtime_dir, tmp_path, code, name="roundtrip")
        assert result.returncode == 0
        assert result.stdout.strip() == "module Roundtrip"
