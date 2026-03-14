#include "prove_array.h"
#include <stdlib.h>
#include <string.h>

Prove_Array *prove_array_new(int64_t length, int64_t elem_size, const void *default_val) {
    Prove_Array *arr = (Prove_Array *)malloc(sizeof(Prove_Array));
    if (!arr) prove_panic("array: out of memory");
    arr->header.refcount = 1;
    arr->length = length;
    arr->elem_size = elem_size;
    /* Overflow guard: check that length * elem_size doesn't overflow */
    if (length > 0 && elem_size > 0 &&
        (size_t)length > SIZE_MAX / (size_t)elem_size) {
        prove_panic("array: allocation size overflow");
    }
    arr->data = malloc((size_t)(length * elem_size));
    if (!arr->data) prove_panic("array: out of memory");
    for (int64_t i = 0; i < length; i++) {
        memcpy((char *)arr->data + i * elem_size, default_val, (size_t)elem_size);
    }
    return arr;
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

Prove_Array *prove_array_map(Prove_Array *arr, void *(*fn)(void *),
                              int64_t result_elem_size) {
    int64_t zero = 0;
    Prove_Array *out = prove_array_new(arr->length, result_elem_size, &zero);
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        void *mapped = fn((void *)boxed);
        intptr_t result = (intptr_t)mapped;
        memcpy((char *)out->data + i * result_elem_size, &result,
               (size_t)result_elem_size);
    }
    return out;
}

void *prove_array_reduce(Prove_Array *arr, void *init,
                          void *(*fn)(void *accum, void *elem)) {
    void *accum = init;
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        accum = fn(accum, (void *)boxed);
    }
    return accum;
}

void prove_array_each(Prove_Array *arr, void (*fn)(void *)) {
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        fn((void *)boxed);
    }
}

Prove_List *prove_array_filter(Prove_Array *arr, bool (*pred)(void *)) {
    int64_t hint = arr->length < 8 ? arr->length : arr->length / 2;
    if (hint < 4) hint = 4;
    Prove_List *out = prove_list_new(hint);
    for (int64_t i = 0; i < arr->length; i++) {
        void *elem = (char *)arr->data + i * arr->elem_size;
        intptr_t boxed = 0;
        memcpy(&boxed, elem, (size_t)arr->elem_size);
        if (pred((void *)boxed)) {
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
