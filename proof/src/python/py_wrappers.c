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
#include "prove_string.h"
#include <Python.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Generated into build/gen/ by the Prove compiler when foreign libpython3
 * is detected. If this include fails, the project is missing a comptime
 * read() of a .py file that imports the required Python packages. */
#include "prove_bundle_data.h"

void py_initialize(void) {
#ifdef PYTHON_HOME
  /* Tell the embedded interpreter where its standard library lives.
   * Without this, Python searches relative to the proof binary and
   * fails to find os, sys, etc. PYTHON_HOME is set via c_flags in prove.toml.
   */
  static wchar_t _home[] = L"" PYTHON_HOME;
  Py_SetPythonHome(_home);
#endif
  Py_Initialize();
  /* Write the bundled prove package to a zip next to the binary and prepend
   * to sys.path so `import prove` works regardless of the working directory.
   * Uses a fixed name beside the binary to avoid /tmp accumulation. */
  extern const char *__prove_binary_path;  /* set by main before py_initialize */
  const char *bin_path = __prove_binary_path;
  char bundle_path[4096];
  if (bin_path) {
    /* Place bundle zip next to the binary: <dir>/.prove_bundle.zip */
    const char *last_slash = strrchr(bin_path, '/');
    size_t dir_len = last_slash ? (size_t)(last_slash - bin_path) : 1;
    snprintf(bundle_path, sizeof(bundle_path), "%.*s/.prove_bundle.zip",
             (int)dir_len, last_slash ? bin_path : ".");
  } else {
    snprintf(bundle_path, sizeof(bundle_path), ".prove_bundle.zip");
  }
  int fd = open(bundle_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd >= 0) {
    write(fd, prove_bundle_zip, prove_bundle_zip_len);
    close(fd);
    PyObject *sys_mod = PyImport_ImportModule("sys");
    PyObject *path = PyObject_GetAttrString(sys_mod, "path");
    PyObject *zip_str = PyUnicode_FromString(bundle_path);
    PyList_Insert(path, 0, zip_str);
    Py_DECREF(zip_str);
    Py_DECREF(path);
    Py_DECREF(sys_mod);
  }
}

void py_finalize(void) { Py_Finalize(); }

int64_t py_run_string(Prove_String *code) {
  int64_t rc = (int64_t)PyRun_SimpleString(code->data);
  if (rc != 0 && PyErr_Occurred()) {
    /* Check for SystemExit before calling PyErr_Print, because
     * PyErr_Print handles SystemExit by calling exit() directly,
     * which crashes the Prove runtime during cleanup (bus error). */
    PyObject *exc_type, *exc_value, *exc_tb;
    PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
    if (exc_type && PyErr_GivenExceptionMatches(exc_type, PyExc_SystemExit)) {
      /* Extract the exit code and return it without calling exit() */
      int64_t exit_code = 1;
      if (exc_value) {
        PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);
        PyObject *code_attr = PyObject_GetAttrString(exc_value, "code");
        if (code_attr && PyLong_Check(code_attr)) {
          exit_code = (int64_t)PyLong_AsLongLong(code_attr);
        }
        Py_XDECREF(code_attr);
      }
      Py_XDECREF(exc_type);
      Py_XDECREF(exc_value);
      Py_XDECREF(exc_tb);
      return exit_code;
    }
    /* Not SystemExit — restore and print the error normally */
    PyErr_Restore(exc_type, exc_value, exc_tb);
    PyErr_Print();
  }
  return rc;
}

void py_set_string(Prove_String *name, Prove_String *value) {
  if (!value) {
    /* NULL value — set Python variable to None instead of crashing */
    PyObject *main_module = PyImport_AddModule("__main__");
    PyObject *main_dict = PyModule_GetDict(main_module);
    Py_INCREF(Py_None);
    PyDict_SetItemString(main_dict, name->data, Py_None);
    return;
  }
  PyObject *main_module = PyImport_AddModule("__main__");
  PyObject *main_dict = PyModule_GetDict(main_module);
  PyObject *val = PyUnicode_FromStringAndSize(value->data, value->length);
  PyDict_SetItemString(main_dict, name->data, val);
  Py_DECREF(val);
}

void py_set_integer(Prove_String *name, int64_t value) {
  PyObject *main_module = PyImport_AddModule("__main__");
  PyObject *main_dict = PyModule_GetDict(main_module);
  PyObject *val = PyLong_FromLongLong(value);
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
