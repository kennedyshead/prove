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
#include <sys/stat.h>
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
  /* Only unpack the bundle if the build actually included Python packages. */
  if (prove_bundle_zip_len > 0) {
    /* Write the bundled zip next to the binary and extract it so both .py
     * and native extensions (.so/.dylib) are importable.  Uses the real
     * executable path so it works regardless of cwd. */
    char exe_path[4096];
    char bundle_base[4096];
    char zip_path[4096];
    char extract_dir[4096];

#ifdef __APPLE__
    {
      uint32_t sz = sizeof(exe_path);
      extern int _NSGetExecutablePath(char *, uint32_t *);
      if (_NSGetExecutablePath(exe_path, &sz) != 0) {
        exe_path[0] = '\0';
      } else {
        /* Resolve symlinks so the bundle lands next to the real binary. */
        char *rp = realpath(exe_path, NULL);
        if (rp) { strncpy(exe_path, rp, sizeof(exe_path) - 1); free(rp); }
      }
    }
#elif defined(__linux__)
    {
      ssize_t n = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
      if (n > 0) exe_path[n] = '\0'; else exe_path[0] = '\0';
    }
#else
    exe_path[0] = '\0';
#endif

    if (exe_path[0]) {
      const char *last_slash = strrchr(exe_path, '/');
      size_t dir_len = last_slash ? (size_t)(last_slash - exe_path) : 1;
      snprintf(bundle_base, sizeof(bundle_base), "%.*s/.prove",
               (int)dir_len, last_slash ? exe_path : ".");
    } else {
      snprintf(bundle_base, sizeof(bundle_base), ".prove");
    }
    mkdir(bundle_base, 0755);
    snprintf(zip_path, sizeof(zip_path), "%s/bundle.zip", bundle_base);
    snprintf(extract_dir, sizeof(extract_dir), "%s/bundle", bundle_base);

    /* Check if zip already exists with correct size — skip rewrite. */
    bool needs_extract = true;
    struct stat st;
    if (stat(zip_path, &st) == 0 &&
        (size_t)st.st_size == prove_bundle_zip_len) {
      /* Zip is current; only re-extract if bundle dir is missing. */
      struct stat dir_st;
      if (stat(extract_dir, &dir_st) == 0 && S_ISDIR(dir_st.st_mode)) {
        needs_extract = false;
      }
    }
    if (needs_extract) {
      /* Write zip to disk. */
      char tmp_path[4096];
      snprintf(tmp_path, sizeof(tmp_path), "%s.%d", zip_path, getpid());
      int fd = open(tmp_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
      if (fd >= 0) {
        write(fd, prove_bundle_zip, prove_bundle_zip_len);
        close(fd);
        rename(tmp_path, zip_path);
      }
      /* Extract zip to .prove/bundle/ via Python's zipfile module. */
      char extract_code[4096];
      snprintf(extract_code, sizeof(extract_code),
               "import zipfile, shutil, os\n"
               "d = '%s'\n"
               "if os.path.isdir(d): shutil.rmtree(d)\n"
               "os.makedirs(d, exist_ok=True)\n"
               "zipfile.ZipFile('%s').extractall(d)\n",
               extract_dir, zip_path);
      PyRun_SimpleString(extract_code);
    }
    /* Prepend .prove/bundle/ to sys.path so all packages are importable. */
    PyObject *sys_mod = PyImport_ImportModule("sys");
    PyObject *path = PyObject_GetAttrString(sys_mod, "path");
    PyObject *dir_str = PyUnicode_FromString(extract_dir);
    PyList_Insert(path, 0, dir_str);
    Py_DECREF(dir_str);
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
