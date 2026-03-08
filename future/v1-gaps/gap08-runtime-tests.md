# Runtime Tests — V1.0 Gap 08

## Overview

Four stdlib modules with C runtime implementations lack dedicated runtime test files.
These modules are exercised via e2e tests but do not have the focused unit-level C
runtime tests that other modules have. Adding them follows the established pattern
in `prove-py/tests/`.

## Current State

Existing runtime test files (12 files):

| File | Module |
|------|--------|
| `test_runtime_c.py` | Core runtime |
| `test_convert_runtime_c.py` | Convert |
| `test_error_runtime_c.py` | Error |
| `test_format_runtime_c.py` | Format |
| `test_io_runtime_c.py` | InputOutput |
| `test_list_runtime_c.py` | List |
| `test_lookup_runtime_c.py` | Lookup |
| `test_math_runtime_c.py` | Math |
| `test_parse_csv_runtime_c.py` | Parse (CSV) |
| `test_parse_runtime_c.py` | Parse |
| `test_path_runtime_c.py` | Path |
| `test_pattern_runtime_c.py` | Pattern |

Shared infrastructure:

- `compile_and_run()` function (`runtime_helpers.py:11`) — compiles C test code
  against the runtime, runs it, returns stdout/stderr/returncode
- `needs_cc` fixture (`conftest.py:18`) — skips test if no C compiler available
- `runtime_dir` fixture (`conftest.py:35`) — copies runtime source files to temp
  directory for compilation

## What's Missing

| Missing test file | Module | Runtime files |
|-------------------|--------|---------------|
| `test_time_runtime_c.py` | Time | `prove_time.c/h` |
| `test_random_runtime_c.py` | Random | `prove_random.c/h` |
| `test_hash_crypto_runtime_c.py` | Hash | `prove_hash_crypto.c/h` |
| `test_bytes_runtime_c.py` | Bytes | `prove_bytes.c/h` |

## Implementation

### File template (all 4 files follow this pattern)

```python
"""C runtime tests for prove_<module>."""

import pytest
from runtime_helpers import compile_and_run


@pytest.fixture
def <module>_code():
    """Base C code with includes for <module> tests."""
    return '''
#include "prove_runtime.h"
#include "prove_<module>.h"
#include <stdio.h>
#include <assert.h>

int main(void) {
    prove_runtime_init();
    {test_body}
    prove_runtime_cleanup();
    return 0;
}
'''


class TestProve<Module>:
    """Tests for prove_<module>.c runtime functions."""

    def test_<function>(self, needs_cc, runtime_dir, <module>_code):
        code = <module>_code.replace("{test_body}", '''
            // test body here
        ''')
        result = compile_and_run(code, runtime_dir)
        assert result.returncode == 0
```

### test_time_runtime_c.py

Test coverage for `prove_time.c/h`:
- `prove_time_now()` — returns non-zero timestamp
- `prove_time_elapsed()` — returns positive duration after sleep
- `prove_time_format()` — formats timestamp to string
- `prove_time_parse()` — parses time string
- `prove_time_to_utc()` / `prove_time_to_local()` — timezone conversion

### test_random_runtime_c.py

Test coverage for `prove_random.c/h`:
- `prove_random_integer()` — returns value within range
- `prove_random_float()` — returns value in [0, 1)
- `prove_random_seed()` — deterministic output with same seed
- `prove_random_choice()` — returns element from list
- `prove_random_shuffle()` — permutes list (statistical test or deterministic seed)

### test_hash_crypto_runtime_c.py

Test coverage for `prove_hash_crypto.c/h`:
- `prove_hash_sha256()` — known test vectors
- `prove_hash_sha512()` — known test vectors
- `prove_hash_hmac()` — known HMAC test vectors
- Empty input handling
- Large input handling

### test_bytes_runtime_c.py

Test coverage for `prove_bytes.c/h`:
- `prove_bytes_new()` — creates byte array
- `prove_bytes_length()` — returns correct length
- `prove_bytes_get()` / `prove_bytes_set()` — indexing
- `prove_bytes_slice()` — sub-array extraction
- `prove_bytes_concat()` — concatenation
- `prove_bytes_from_string()` / `prove_bytes_to_string()` — conversion

## Files to Create

| File | Description |
|------|-------------|
| `prove-py/tests/test_time_runtime_c.py` | Time module runtime tests |
| `prove-py/tests/test_random_runtime_c.py` | Random module runtime tests |
| `prove-py/tests/test_hash_crypto_runtime_c.py` | Hash module runtime tests |
| `prove-py/tests/test_bytes_runtime_c.py` | Bytes module runtime tests |

## Exit Criteria

- [ ] `test_time_runtime_c.py` — all time functions tested
- [ ] `test_random_runtime_c.py` — all random functions tested, deterministic seeding verified
- [ ] `test_hash_crypto_runtime_c.py` — SHA-256/512 against known test vectors
- [ ] `test_bytes_runtime_c.py` — all byte operations tested
- [ ] All 4 files use `needs_cc` fixture, `runtime_dir` fixture, `compile_and_run()` helper
- [ ] All tests pass with `python -m pytest tests/test_*_runtime_c.py -v`
- [ ] No new dependencies required
