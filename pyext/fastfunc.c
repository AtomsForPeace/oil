// Python wrapper for FANOS library in cpp/fanos_shared.h

#include <assert.h>
#include <stdarg.h>  // va_list, etc.
#include <stdio.h>  // vfprintf
#include <stdlib.h>

#include "data_lang/j8_libc.h"
#include "data_lang/utf8_impls/bjoern_dfa.h"

#include <Python.h>

// Log messages to stderr.
static void debug(const char* fmt, ...) {
#if 0
  va_list args;
  va_start(args, fmt);
  vfprintf(stderr, fmt, args);
  va_end(args);
  fprintf(stderr, "\n");
#endif
}

static PyObject *
func_J8EncodeString(PyObject *self, PyObject *args) {
  j8_buf_t in;
  int j8_fallback;

  if (!PyArg_ParseTuple(args, "s#i", &(in.data), &(in.len), &j8_fallback)) {
    return NULL;
  }

  j8_buf_t out;
  J8EncodeString(in, &out, j8_fallback);

  PyObject *ret = PyString_FromStringAndSize(out.data, out.len);
  return ret;
}

static PyObject *
func_PartIsUtf8(PyObject *self, PyObject *args) {
  j8_buf_t in;
  int start;
  int end;

  if (!PyArg_ParseTuple(args, "s#ii", &(in.data), &(in.len), &start, &end)) {
    return NULL;
  }
  // Bounds check for safety
  assert(0 <= start);
  assert(end <= in.len);

  uint32_t codepoint;
  uint32_t state = UTF8_ACCEPT;

  for (int i = start; i < end; ++i) {
    // This var or a static_cast<> is necessary.  Should really change BigStr*
    // to use unsigned type
    unsigned char c = in.data[i];
    decode(&state, &codepoint, c);
    if (state == UTF8_REJECT) {
      return PyBool_FromLong(0);
    }
  }

  return PyBool_FromLong(state == UTF8_ACCEPT);
}


static PyMethodDef methods[] = {
  {"J8EncodeString", func_J8EncodeString, METH_VARARGS, ""},
  {"PartIsUtf8", func_PartIsUtf8, METH_VARARGS, ""},

  {NULL, NULL},
};

void initfastfunc(void) {
  Py_InitModule("fastfunc", methods);
}
