"""Tests for the Network stdlib C runtime."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestNetworkSocketValidates:
    def test_closed_socket(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_network.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Socket s = { .fd = -1 };
                printf("%d\\n", prove_network_socket_validates(&s));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sock_validates")
        assert result.returncode == 0
        assert "0" in result.stdout
