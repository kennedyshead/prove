"""Tests for prove_parse_arguments C runtime function."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestArgumentsParse:
    def test_empty_args(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(4);
                Prove_Value *result = prove_parse_arguments(args);
                if (!prove_value_is_object(result)) return 1;
                Prove_Table *t = prove_value_as_object(result);

                /* Check args is empty array */
                Prove_Option a = prove_table_get(prove_string_from_cstr("args"), t);
                if (prove_option_is_none(a)) return 2;
                Prove_Value *av = (Prove_Value *)a.value;
                if (!prove_value_is_array(av)) return 3;
                if (prove_list_len(prove_value_as_array(av)) != 0) return 4;

                /* Check kwargs is empty object */
                Prove_Option k = prove_table_get(prove_string_from_cstr("kwargs"), t);
                if (prove_option_is_none(k)) return 5;
                Prove_Value *kv = (Prove_Value *)k.value;
                if (!prove_value_is_object(kv)) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_empty")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_positional_only(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(4);
                prove_list_push(args, prove_string_from_cstr("foo"));
                prove_list_push(args, prove_string_from_cstr("bar"));

                Prove_Value *result = prove_parse_arguments(args);
                Prove_Table *t = prove_value_as_object(result);

                Prove_Option a = prove_table_get(prove_string_from_cstr("args"), t);
                Prove_List *arr = prove_value_as_array((Prove_Value *)a.value);
                if (prove_list_len(arr) != 2) return 1;

                Prove_Value *v0 = (Prove_Value *)prove_list_get(arr, 0);
                if (!prove_string_eq(prove_value_as_text(v0),
                                     prove_string_from_cstr("foo"))) return 2;
                Prove_Value *v1 = (Prove_Value *)prove_list_get(arr, 1);
                if (!prove_string_eq(prove_value_as_text(v1),
                                     prove_string_from_cstr("bar"))) return 3;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_pos")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_flags_only(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(4);
                prove_list_push(args, prove_string_from_cstr("--debug"));
                prove_list_push(args, prove_string_from_cstr("--verbose"));

                Prove_Value *result = prove_parse_arguments(args);
                Prove_Table *t = prove_value_as_object(result);

                /* args should be empty */
                Prove_Option a = prove_table_get(prove_string_from_cstr("args"), t);
                Prove_List *arr = prove_value_as_array((Prove_Value *)a.value);
                if (prove_list_len(arr) != 0) return 1;

                /* kwargs should have debug=null, verbose=null */
                Prove_Option k = prove_table_get(prove_string_from_cstr("kwargs"), t);
                Prove_Table *kw = prove_value_as_object((Prove_Value *)k.value);

                Prove_Option d = prove_table_get(prove_string_from_cstr("debug"), kw);
                if (prove_option_is_none(d)) return 2;
                if (!prove_value_is_unit((Prove_Value *)d.value)) return 3;

                Prove_Option v = prove_table_get(prove_string_from_cstr("verbose"), kw);
                if (prove_option_is_none(v)) return 4;
                if (!prove_value_is_unit((Prove_Value *)v.value)) return 5;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_flags")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_key_value_pair(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(4);
                prove_list_push(args, prove_string_from_cstr("--file"));
                prove_list_push(args, prove_string_from_cstr("path.prv"));

                Prove_Value *result = prove_parse_arguments(args);
                Prove_Table *t = prove_value_as_object(result);

                Prove_Option k = prove_table_get(prove_string_from_cstr("kwargs"), t);
                Prove_Table *kw = prove_value_as_object((Prove_Value *)k.value);

                Prove_Option f = prove_table_get(prove_string_from_cstr("file"), kw);
                if (prove_option_is_none(f)) return 1;
                Prove_Value *fv = (Prove_Value *)f.value;
                if (!prove_value_is_text(fv)) return 2;
                if (!prove_string_eq(prove_value_as_text(fv),
                                     prove_string_from_cstr("path.prv"))) return 3;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_kv")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_mixed(self, tmp_path, runtime_dir):
        """foo --file path.prv --debug → args=["foo"], kwargs={file:"path.prv", debug:null}"""
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(8);
                prove_list_push(args, prove_string_from_cstr("foo"));
                prove_list_push(args, prove_string_from_cstr("--file"));
                prove_list_push(args, prove_string_from_cstr("path.prv"));
                prove_list_push(args, prove_string_from_cstr("--debug"));

                Prove_Value *result = prove_parse_arguments(args);
                Prove_Table *t = prove_value_as_object(result);

                /* Check positional */
                Prove_Option a = prove_table_get(prove_string_from_cstr("args"), t);
                Prove_List *arr = prove_value_as_array((Prove_Value *)a.value);
                if (prove_list_len(arr) != 1) return 1;
                Prove_Value *v0 = (Prove_Value *)prove_list_get(arr, 0);
                if (!prove_string_eq(prove_value_as_text(v0),
                                     prove_string_from_cstr("foo"))) return 2;

                /* Check kwargs */
                Prove_Option k = prove_table_get(prove_string_from_cstr("kwargs"), t);
                Prove_Table *kw = prove_value_as_object((Prove_Value *)k.value);

                Prove_Option f = prove_table_get(prove_string_from_cstr("file"), kw);
                if (prove_option_is_none(f)) return 3;
                if (!prove_string_eq(prove_value_as_text((Prove_Value *)f.value),
                                     prove_string_from_cstr("path.prv"))) return 4;

                Prove_Option d = prove_table_get(prove_string_from_cstr("debug"), kw);
                if (prove_option_is_none(d)) return 5;
                if (!prove_value_is_unit((Prove_Value *)d.value)) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_mixed")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_flag_at_end(self, tmp_path, runtime_dir):
        """--key at end of args should be a bare flag."""
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *args = prove_list_new(4);
                prove_list_push(args, prove_string_from_cstr("--output"));
                prove_list_push(args, prove_string_from_cstr("file.txt"));
                prove_list_push(args, prove_string_from_cstr("--verbose"));

                Prove_Value *result = prove_parse_arguments(args);
                Prove_Table *t = prove_value_as_object(result);

                Prove_Option k = prove_table_get(prove_string_from_cstr("kwargs"), t);
                Prove_Table *kw = prove_value_as_object((Prove_Value *)k.value);

                /* --output file.txt → key/value */
                Prove_Option o = prove_table_get(prove_string_from_cstr("output"), kw);
                if (prove_option_is_none(o)) return 1;
                if (!prove_string_eq(prove_value_as_text((Prove_Value *)o.value),
                                     prove_string_from_cstr("file.txt"))) return 2;

                /* --verbose at end → bare flag */
                Prove_Option v = prove_table_get(prove_string_from_cstr("verbose"), kw);
                if (prove_option_is_none(v)) return 3;
                if (!prove_value_is_unit((Prove_Value *)v.value)) return 4;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="args_end_flag")
        assert result.returncode == 0
        assert "OK" in result.stdout
