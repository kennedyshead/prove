#include "prove_array.h"
#include <stdlib.h>
#include <string.h>

/* Internal: allocate array without default-filling data buffer */
static Prove_Array *_prove_array_new_uninit(int64_t length, size_t elem_size) {
    Prove_Array *arr = (Prove_Array *)prove_alloc(sizeof(Prove_Array));
    arr->length = length;
    arr->elem_size = (int64_t)elem_size;
    if (length > 0 && elem_size > 0 &&
        (size_t)length > SIZE_MAX / elem_size) {
        prove_panic("array: allocation size overflow");
    }
    arr->data = malloc((size_t)length * elem_size);
    if (!arr->data) prove_panic("array: out of memory");
    return arr;
}

Prove_Array *prove_array_new(int64_t length, int64_t elem_size, const void *default_val) {
    Prove_Array *arr = _prove_array_new_uninit(length, (size_t)elem_size);
    for (int64_t i = 0; i < length; i++) {
        memcpy((char *)arr->data + i * elem_size, default_val, (size_t)elem_size);
    }
    return arr;
}

void prove_array_free(Prove_Array *arr) {
    if (!arr) return;
    free(arr->data);
    free(arr);
}

Prove_Array *prove_array_new_bool(int64_t size, bool default_val) {
    return prove_array_new(size, sizeof(bool), &default_val);
}

Prove_Array *prove_array_new_int(int64_t size, int64_t default_val) {
    return prove_array_new(size, sizeof(int64_t), &default_val);
}

void *prove_array_get(Prove_Array *arr, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    return (char *)arr->data + idx * arr->elem_size;
}

bool prove_array_get_bool(Prove_Array *arr, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    bool val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(bool));
    return val;
}

int64_t prove_array_get_int(Prove_Array *arr, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    int64_t val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(int64_t));
    return val;
}

Prove_Array *prove_array_set(Prove_Array *arr, int64_t idx, const void *val) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    /* Copy-on-write optimization: mutate in-place when sole owner */
    if (arr->header.refcount == 1) {
        return prove_array_set_mut(arr, idx, val);
    }
    Prove_Array *copy = (Prove_Array *)malloc(sizeof(Prove_Array));
    if (!copy) prove_panic("array: out of memory");
    copy->header.refcount = 1;
    copy->length = arr->length;
    copy->elem_size = arr->elem_size;
    copy->data = malloc((size_t)(arr->length * arr->elem_size));
    if (!copy->data) prove_panic("array: out of memory");
    memcpy(copy->data, arr->data, (size_t)(arr->length * arr->elem_size));
    memcpy((char *)copy->data + idx * arr->elem_size, val, (size_t)arr->elem_size);
    return copy;
}

Prove_Array *prove_array_set_bool(Prove_Array *arr, int64_t idx, bool val) {
    return prove_array_set(arr, idx, &val);
}

Prove_Array *prove_array_set_int(Prove_Array *arr, int64_t idx, int64_t val) {
    return prove_array_set(arr, idx, &val);
}

Prove_Array *prove_array_set_mut(Prove_Array *arr, int64_t idx, const void *val) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    memcpy((char *)arr->data + idx * arr->elem_size, val, (size_t)arr->elem_size);
    return arr;
}

Prove_Array *prove_array_set_mut_bool(Prove_Array *arr, int64_t idx, bool val) {
    prove_array_set_mut(arr, idx, &val);
    return arr;
}

Prove_Array *prove_array_set_mut_int(Prove_Array *arr, int64_t idx, int64_t val) {
    prove_array_set_mut(arr, idx, &val);
    return arr;
}

int64_t prove_array_length(Prove_Array *arr) {
    return arr->length;
}

/* ── Bounds-checked access ───────────────────────────────────── */

Prove_Option prove_array_get_safe_bool(Prove_Array *arr, int64_t idx) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    bool val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(bool));
    return prove_option_some((Prove_Value *)(intptr_t)val);
}

Prove_Option prove_array_get_safe_int(Prove_Array *arr, int64_t idx) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    int64_t val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(int64_t));
    return prove_option_some((Prove_Value *)(intptr_t)val);
}

Prove_Option prove_array_set_safe_bool(Prove_Array *arr, int64_t idx, bool val) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    return prove_option_some((Prove_Value *)prove_array_set_bool(arr, idx, val));
}

Prove_Option prove_array_set_safe_int(Prove_Array *arr, int64_t idx, int64_t val) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    return prove_option_some((Prove_Value *)prove_array_set_int(arr, idx, val));
}

/* ── Higher-order operations ─────────────────────────────────── */

Prove_Array *prove_array_map(Prove_Array *arr, void *(*fn)(void *, void *),
                              void *ctx, int64_t result_elem_size) {
    int64_t zero = 0;
    Prove_Array *out = prove_array_new(arr->length, result_elem_size, &zero);
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        void *mapped = fn((void *)boxed, ctx);
        intptr_t result = (intptr_t)mapped;
        memcpy((char *)out->data + i * result_elem_size, &result,
               (size_t)result_elem_size);
    }
    return out;
}

void *prove_array_reduce(Prove_Array *arr, void *init,
                          void *(*fn)(void *accum, void *elem, void *ctx),
                          void *ctx) {
    void *accum = init;
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        accum = fn(accum, (void *)boxed, ctx);
    }
    return accum;
}

void prove_array_each(Prove_Array *arr, void (*fn)(void *, void *), void *ctx) {
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        fn((void *)boxed, ctx);
    }
}

Prove_List *prove_array_filter(Prove_Array *arr, bool (*pred)(void *, void *), void *ctx) {
    int64_t hint = arr->length < 8 ? arr->length : arr->length / 2;
    if (hint < 4) hint = 4;
    Prove_List *out = prove_list_new(hint);
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        if (pred((void *)boxed, ctx)) {
            prove_list_push(out, (void *)boxed);
        }
    }
    return out;
}

/* ── Conversions ─────────────────────────────────────────────── */

Prove_List *prove_array_to_list(Prove_Array *arr) {
    Prove_List *list = prove_list_new(arr->length);
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        if (arr->elem_size == sizeof(void *)) {
            prove_list_push(list, *(void **)elem);
        } else {
            intptr_t val = 0;
            memcpy(&val, elem, (size_t)arr->elem_size);
            prove_list_push(list, (void *)val);
        }
    }
    return list;
}

Prove_Array *prove_array_from_list(Prove_List *list, int64_t elem_size,
                                    void (*unbox_fn)(void *elem, void *out)) {
    int64_t len = prove_list_len(list);
    /* Use 0 as default initializer placeholder */
    int64_t zero = 0;
    Prove_Array *arr = prove_array_new(len, elem_size, &zero);
    for (int64_t i = 0; i < len; i++) {
        void *raw = prove_list_get(list, i);
        void *dst = (char *)arr->data + i * elem_size;
        if (unbox_fn) {
            unbox_fn(raw, dst);
        } else {
            intptr_t val = (intptr_t)raw;
            memcpy(dst, &val, (size_t)elem_size);
        }
    }
    return arr;
}

/* ── Missing float implementations ───────────────────────────── */

Prove_Array *prove_array_new_float(int64_t size, double default_val) {
    return prove_array_new(size, sizeof(double), &default_val);
}

double prove_array_get_float(Prove_Array *arr, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= arr->length) prove_panic("array: index out of bounds");
#endif
    double val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(double));
    return val;
}

Prove_Array *prove_array_set_float(Prove_Array *arr, int64_t idx, double val) {
    return prove_array_set(arr, idx, &val);
}

Prove_Array *prove_array_set_mut_float(Prove_Array *arr, int64_t idx, double val) {
    prove_array_set_mut(arr, idx, &val);
    return arr;
}

Prove_Option prove_array_get_safe_float(Prove_Array *arr, int64_t idx) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    double val;
    memcpy(&val, (char *)arr->data + idx * arr->elem_size, sizeof(double));
    void *boxed;
    memcpy(&boxed, &val, sizeof(void *));
    return prove_option_some((Prove_Value *)boxed);
}

Prove_Option prove_array_set_safe_float(Prove_Array *arr, int64_t idx, double val) {
    if (idx < 0 || idx >= arr->length) return prove_option_none();
    return prove_option_some((Prove_Value *)prove_array_set_float(arr, idx, val));
}

/* ── First / Last ─────────────────────────────────────────────── */

Prove_Option prove_array_first_bool(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    bool val;
    memcpy(&val, arr->data, sizeof(bool));
    return prove_option_some((Prove_Value *)(intptr_t)(int64_t)val);
}

Prove_Option prove_array_first_int(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    int64_t val;
    memcpy(&val, arr->data, sizeof(int64_t));
    return prove_option_some((Prove_Value *)(intptr_t)val);
}

Prove_Option prove_array_first_float(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    double val;
    memcpy(&val, arr->data, sizeof(double));
    void *boxed;
    memcpy(&boxed, &val, sizeof(void *));
    return prove_option_some((Prove_Value *)boxed);
}

Prove_Option prove_array_last_bool(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    bool val;
    memcpy(&val, (char *)arr->data + (arr->length - 1) * arr->elem_size, sizeof(bool));
    return prove_option_some((Prove_Value *)(intptr_t)(int64_t)val);
}

Prove_Option prove_array_last_int(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    int64_t val;
    memcpy(&val, (char *)arr->data + (arr->length - 1) * arr->elem_size, sizeof(int64_t));
    return prove_option_some((Prove_Value *)(intptr_t)val);
}

Prove_Option prove_array_last_float(Prove_Array *arr) {
    if (arr->length == 0) return prove_option_none();
    double val;
    memcpy(&val, (char *)arr->data + (arr->length - 1) * arr->elem_size, sizeof(double));
    void *boxed;
    memcpy(&boxed, &val, sizeof(void *));
    return prove_option_some((Prove_Value *)boxed);
}

/* ── Empty ────────────────────────────────────────────────────── */

bool prove_array_empty(Prove_Array *arr) {
    return arr->length == 0;
}

/* ── Contains ─────────────────────────────────────────────────── */

bool prove_array_contains_bool(Prove_Array *arr, bool value) {
    for (int64_t i = 0; i < arr->length; i++) {
        bool v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(bool));
        if (v == value) return true;
    }
    return false;
}

bool prove_array_contains_int(Prove_Array *arr, int64_t value) {
    for (int64_t i = 0; i < arr->length; i++) {
        int64_t v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(int64_t));
        if (v == value) return true;
    }
    return false;
}

bool prove_array_contains_float(Prove_Array *arr, double value) {
    for (int64_t i = 0; i < arr->length; i++) {
        double v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(double));
        if (v == value) return true;
    }
    return false;
}

/* ── Index ────────────────────────────────────────────────────── */

Prove_Option prove_array_index_int(Prove_Array *arr, int64_t value) {
    for (int64_t i = 0; i < arr->length; i++) {
        int64_t v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(int64_t));
        if (v == value) return prove_option_some((Prove_Value *)(intptr_t)i);
    }
    return prove_option_none();
}

Prove_Option prove_array_index_bool(Prove_Array *arr, bool value) {
    for (int64_t i = 0; i < arr->length; i++) {
        bool v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(bool));
        if (v == value) return prove_option_some((Prove_Value *)(intptr_t)i);
    }
    return prove_option_none();
}

Prove_Option prove_array_index_float(Prove_Array *arr, double value) {
    for (int64_t i = 0; i < arr->length; i++) {
        double v;
        memcpy(&v, (char *)arr->data + i * arr->elem_size, sizeof(double));
        if (v == value) return prove_option_some((Prove_Value *)(intptr_t)i);
    }
    return prove_option_none();
}

/* ── Slice ────────────────────────────────────────────────────── */

static Prove_Array *_prove_array_slice(Prove_Array *arr, int64_t start, int64_t end) {
    if (start < 0) start = 0;
    if (end > arr->length) end = arr->length;
    int64_t count = (start < end) ? (end - start) : 0;
    int64_t alloc_len = count > 0 ? count : 1;
    Prove_Array *out = _prove_array_new_uninit(alloc_len, (size_t)arr->elem_size);
    out->length = count;
    if (count > 0) {
        memcpy(out->data, (char *)arr->data + start * arr->elem_size,
               (size_t)(count * arr->elem_size));
    }
    return out;
}

Prove_Array *prove_array_slice_bool(Prove_Array *arr, int64_t start, int64_t end) {
    return _prove_array_slice(arr, start, end);
}

Prove_Array *prove_array_slice_int(Prove_Array *arr, int64_t start, int64_t end) {
    return _prove_array_slice(arr, start, end);
}

Prove_Array *prove_array_slice_float(Prove_Array *arr, int64_t start, int64_t end) {
    return _prove_array_slice(arr, start, end);
}

/* ── Reverse ──────────────────────────────────────────────────── */

static Prove_Array *_prove_array_reverse(Prove_Array *arr) {
    int64_t alloc_len = arr->length > 0 ? arr->length : 1;
    Prove_Array *out = _prove_array_new_uninit(alloc_len, (size_t)arr->elem_size);
    out->length = arr->length;
    for (int64_t i = 0; i < arr->length; i++) {
        void *src = (char *)arr->data + (arr->length - 1 - i) * arr->elem_size;
        void *dst = (char *)out->data + i * arr->elem_size;
        memcpy(dst, src, (size_t)arr->elem_size);
    }
    return out;
}

Prove_Array *prove_array_reverse_bool(Prove_Array *arr) {
    return _prove_array_reverse(arr);
}

Prove_Array *prove_array_reverse_int(Prove_Array *arr) {
    return _prove_array_reverse(arr);
}

Prove_Array *prove_array_reverse_float(Prove_Array *arr) {
    return _prove_array_reverse(arr);
}

/* ── Sort ─────────────────────────────────────────────────────── */

static int _cmp_arr_int(const void *a, const void *b) {
    int64_t va, vb;
    memcpy(&va, a, sizeof(int64_t));
    memcpy(&vb, b, sizeof(int64_t));
    return (va > vb) - (va < vb);
}

static int _cmp_arr_float(const void *a, const void *b) {
    double va, vb;
    memcpy(&va, a, sizeof(double));
    memcpy(&vb, b, sizeof(double));
    return (va > vb) - (va < vb);
}

Prove_Array *prove_array_sort_int(Prove_Array *arr) {
    int64_t alloc_len = arr->length > 0 ? arr->length : 1;
    Prove_Array *out = _prove_array_new_uninit(alloc_len, (size_t)arr->elem_size);
    out->length = arr->length;
    if (arr->length > 0) {
        memcpy(out->data, arr->data, (size_t)(arr->length * arr->elem_size));
        if (arr->length > 1) {
            qsort(out->data, (size_t)arr->length, (size_t)arr->elem_size, _cmp_arr_int);
        }
    }
    return out;
}

Prove_Array *prove_array_sort_float(Prove_Array *arr) {
    int64_t alloc_len = arr->length > 0 ? arr->length : 1;
    Prove_Array *out = _prove_array_new_uninit(alloc_len, (size_t)arr->elem_size);
    out->length = arr->length;
    if (arr->length > 0) {
        memcpy(out->data, arr->data, (size_t)(arr->length * arr->elem_size));
        if (arr->length > 1) {
            qsort(out->data, (size_t)arr->length, (size_t)arr->elem_size, _cmp_arr_float);
        }
    }
    return out;
}
