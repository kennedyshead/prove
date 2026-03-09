"""Tests for the Hash/Crypto C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestSHA256:
    def test_sha256_empty_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("");
                Prove_String *hash = prove_crypto_sha256_string(data);
                printf("%.*s\\n", (int)hash->length, hash->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha256_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_sha256_hello(self, tmp_path, runtime_dir):
        # SHA-256("hello") = 2cf24dba...
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("hello");
                Prove_String *hash = prove_crypto_sha256_string(data);
                printf("%.*s\\n", (int)hash->length, hash->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha256_hello")
        assert result.returncode == 0
        assert result.stdout.strip() == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_sha256_bytes_output(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_ByteArray *data = prove_bytes_from_string(s);
                Prove_ByteArray *hash = prove_crypto_sha256_bytes(data);
                printf("%lld\\n", (long long)hash->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha256_bytes")
        assert result.returncode == 0
        assert result.stdout.strip() == "32"

    def test_sha256_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_ByteArray *data = prove_bytes_from_string(s);
                Prove_ByteArray *expected = prove_crypto_sha256_bytes(data);
                printf("%d\\n", prove_crypto_sha256_validates(data, expected) ? 1 : 0);
                /* Corrupt one byte */
                expected->data[0] ^= 0xFF;
                printf("%d\\n", prove_crypto_sha256_validates(data, expected) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha256_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # matches
        assert lines[1] == "0"  # corrupted


class TestSHA512:
    def test_sha512_empty_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("");
                Prove_String *hash = prove_crypto_sha512_string(data);
                printf("%.*s\\n", (int)hash->length, hash->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha512_empty")
        assert result.returncode == 0
        expected = ("cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
                    "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e")
        assert result.stdout.strip() == expected

    def test_sha512_hello(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("hello");
                Prove_String *hash = prove_crypto_sha512_string(data);
                printf("%.*s\\n", (int)hash->length, hash->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha512_hello")
        assert result.returncode == 0
        expected = ("9b71d224bd62f3785d96d46ad3ea3d73319bfbc2890caadae2dff72519673ca7"
                    "2323c3d99ba5c11d7c7acc6e14b8c5da0c4663475c2e5c3adef46f73bcdec043")
        assert result.stdout.strip() == expected

    def test_sha512_bytes_length(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("test");
                Prove_ByteArray *data = prove_bytes_from_string(s);
                Prove_ByteArray *hash = prove_crypto_sha512_bytes(data);
                printf("%lld\\n", (long long)hash->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="sha512_len")
        assert result.returncode == 0
        assert result.stdout.strip() == "64"


class TestBLAKE3:
    def test_blake3_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("");
                Prove_String *hash = prove_crypto_blake3_string(data);
                printf("%.*s\\n", (int)hash->length, hash->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="blake3_empty")
        assert result.returncode == 0
        # BLAKE3 hash of empty string
        expected = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
        assert result.stdout.strip() == expected

    def test_blake3_hello(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *data = prove_string_from_cstr("hello");
                Prove_String *hash = prove_crypto_blake3_string(data);
                printf("%lld\\n", (long long)hash->length);
                /* Just check it returns a 64-char hex string */
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="blake3_hello")
        assert result.returncode == 0
        assert result.stdout.strip() == "64"

    def test_blake3_bytes_length(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("test");
                Prove_ByteArray *data = prove_bytes_from_string(s);
                Prove_ByteArray *hash = prove_crypto_blake3_bytes(data);
                printf("%lld\\n", (long long)hash->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="blake3_len")
        assert result.returncode == 0
        assert result.stdout.strip() == "32"

    def test_blake3_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("test");
                Prove_ByteArray *data = prove_bytes_from_string(s);
                Prove_ByteArray *expected = prove_crypto_blake3_bytes(data);
                printf("%d\\n", prove_crypto_blake3_validates(data, expected) ? 1 : 0);
                expected->data[0] ^= 0xFF;
                printf("%d\\n", prove_crypto_blake3_validates(data, expected) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="blake3_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"
        assert lines[1] == "0"


class TestHMAC:
    def test_hmac_create(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *ds = prove_string_from_cstr("hello");
                Prove_String *ks = prove_string_from_cstr("secret");
                Prove_ByteArray *data = prove_bytes_from_string(ds);
                Prove_ByteArray *key = prove_bytes_from_string(ks);
                Prove_ByteArray *hmac = prove_crypto_hmac_create(data, key);
                printf("%lld\\n", (long long)hmac->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hmac")
        assert result.returncode == 0
        assert result.stdout.strip() == "32"

    def test_hmac_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *ds = prove_string_from_cstr("hello");
                Prove_String *ks = prove_string_from_cstr("secret");
                Prove_ByteArray *data = prove_bytes_from_string(ds);
                Prove_ByteArray *key = prove_bytes_from_string(ks);
                Prove_ByteArray *sig = prove_crypto_hmac_create(data, key);
                printf("%d\\n", prove_crypto_hmac_validates(data, key, sig) ? 1 : 0);
                sig->data[0] ^= 0xFF;
                printf("%d\\n", prove_crypto_hmac_validates(data, key, sig) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hmac_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"
        assert lines[1] == "0"

    def test_hmac_different_keys_differ(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_hash_crypto.h"
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *ds = prove_string_from_cstr("hello");
                Prove_ByteArray *data = prove_bytes_from_string(ds);
                Prove_String *k1s = prove_string_from_cstr("key1");
                Prove_String *k2s = prove_string_from_cstr("key2");
                Prove_ByteArray *key1 = prove_bytes_from_string(k1s);
                Prove_ByteArray *key2 = prove_bytes_from_string(k2s);
                Prove_ByteArray *sig1 = prove_crypto_hmac_create(data, key1);
                Prove_ByteArray *sig2 = prove_crypto_hmac_create(data, key2);
                /* Different keys should produce different HMACs */
                int same = 1;
                for (int64_t i = 0; i < 32; i++) {
                    if (sig1->data[i] != sig2->data[i]) { same = 0; break; }
                }
                printf("%d\\n", same);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hmac_diff")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"  # different
