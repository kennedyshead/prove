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
 *   - Run `python proof/scripts/bundle_prove.py` before building to generate
 *     prove_bundle_data.h (compile fails with #error if it is missing)
 */
#include <Python.h>
#include "prove_string.h"
#include <stdbool.h>
#include <stdint.h>
#include <unistd.h>

/* Generated into build/gen/ by the Prove compiler when foreign libpython3
 * is detected. If this include fails, the project is missing a comptime
 * read() of a .py file that imports the required Python packages. */
#include "prove_bundle_data.h"

void py_initialize(void) {
#ifdef PYTHON_HOME
    /* Tell the embedded interpreter where its standard library lives.
     * Without this, Python searches relative to the proof binary and
     * fails to find os, sys, etc. PYTHON_HOME is set via c_flags in prove.toml. */
    static wchar_t _home[] = L"" PYTHON_HOME;
    Py_SetPythonHome(_home);
#endif
    Py_Initialize();
    /* Write the bundled prove package to a temp zip and prepend to sys.path
     * so `import prove` works regardless of the working directory. */
    char tmp[] = "/tmp/prove_bundle_XXXXXX.zip";
    int fd = mkstemps(tmp, 4);
    if (fd >= 0) {
        write(fd, prove_bundle_zip, prove_bundle_zip_len);
        close(fd);
        PyObject *sys_mod = PyImport_ImportModule("sys");
        PyObject *path = PyObject_GetAttrString(sys_mod, "path");
        PyObject *zip_str = PyUnicode_FromString(tmp);
        PyList_Insert(path, 0, zip_str);
        Py_DECREF(zip_str);
        Py_DECREF(path);
        Py_DECREF(sys_mod);
    }
}

void py_finalize(void) {
    Py_Finalize();
}

int64_t py_run_string(Prove_String *code) {
    return (int64_t)PyRun_SimpleString(code->data);
}

void py_set_string(Prove_String *name, Prove_String *value) {
    PyObject *main_module = PyImport_AddModule("__main__");
    PyObject *main_dict = PyModule_GetDict(main_module);
    PyObject *val = PyUnicode_FromStringAndSize(value->data, value->length);
    PyDict_SetItemString(main_dict, name->data, val);
    Py_DECREF(val);
}

void py_set_bool(Prove_String *name, bool value) {
    PyObject *main_module = PyImport_AddModule("__main__");
    PyObject *main_dict = PyModule_GetDict(main_module);
    PyObject *val = value ? Py_True : Py_False;
    Py_INCREF(val);
    PyDict_SetItemString(main_dict, name->data, val);
    Py_DECREF(val);
}
