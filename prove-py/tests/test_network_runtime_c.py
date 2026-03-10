"""Tests for the Network stdlib C runtime."""

import pytest
from tests.runtime_helpers import compile_and_run

needs_cc = pytest.mark.skipif(
    not pytest.importorskip("shutil").which("cc"),
    reason="C compiler not available",
)


@needs_cc
class TestNetworkAddressCreate:
    def test_creates_valid_address(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("127.0.0.1:8080");
            Prove_Result *r = prove_network_address_creates(s);
            if (r->tag != 0) { printf("FAIL: got error\n"); return 1; }
            Prove_Address *a = (Prove_Address *)r->value;
            Prove_String *host = prove_network_host_reads(a);
            int64_t port = prove_network_port_reads(a);
            printf("host=%.*s port=%lld\n", (int)host->length, host->data, (long long)port);
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "host=127.0.0.1 port=8080" in out

    def test_invalid_address_no_colon(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("localhost");
            Prove_Result *r = prove_network_address_creates(s);
            printf("tag=%d\n", r->tag);
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "tag=1" in out  # Err tag

    def test_invalid_port_out_of_range(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("host:99999");
            Prove_Result *r = prove_network_address_creates(s);
            printf("tag=%d\n", r->tag);
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "tag=1" in out


@needs_cc
class TestNetworkAddressFormat:
    def test_reads_address(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("example.com:443");
            Prove_Result *r = prove_network_address_creates(s);
            Prove_Address *a = (Prove_Address *)r->value;
            Prove_String *fmt = prove_network_address_reads(a);
            printf("%.*s\n", (int)fmt->length, fmt->data);
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "example.com:443" in out


@needs_cc
class TestNetworkAddressValidates:
    def test_valid_address(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("localhost:80");
            printf("%d\n", prove_network_address_validates(s));
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "1" in out

    def test_invalid_address(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_String *s = prove_string_from_cstr("no-port");
            printf("%d\n", prove_network_address_validates(s));
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "0" in out


@needs_cc
class TestNetworkSocketValidates:
    def test_closed_socket(self):
        code = r"""
        #include "prove_network.h"
        #include <stdio.h>
        int main(void) {
            prove_runtime_init();
            Prove_Socket s = { .fd = -1, .protocol = 0 };
            printf("%d\n", prove_network_socket_validates(&s));
            return 0;
        }
        """
        out = compile_and_run(code, extra_libs=["prove_network"])
        assert "0" in out
