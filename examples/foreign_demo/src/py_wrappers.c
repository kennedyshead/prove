/*
 * Thin C wrappers for libpython3.
 *
 * Python's C API uses PascalCase (Py_Initialize, PyRun_SimpleString, etc.).
 * Prove foreign blocks require snake_case names, so these wrappers bridge
 * the gap without changing the Prove source.
 *
 * Build requirements:
 *   - Python development headers (python3-config --includes)
 *   - Link with the matching Python library (python3-config --ldflags)
 *   - Add the Python include path to [build] c_flags in prove.toml
 */
#include <Python.h>
#include "prove_string.h"
#include <stdint.h>

void py_initialize(void) {
    Py_Initialize();
}

void py_finalize(void) {
    Py_Finalize();
}

int64_t py_run_string(Prove_String *code) {
    return (int64_t)PyRun_SimpleString(code->data);
}
