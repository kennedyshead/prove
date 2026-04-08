#include "prove_list_ops.h"
#include <stdlib.h>
#include <string.h>

/*
 * Elements are stored in lists as void* pointers:
 *   - Integers: (void*)(intptr_t)value
 *   - Strings:  (void*)Prove_String*
 *   - Other pointers: (void*)ptr
 */

/* ── Length ───────────────────────────────────────────────────── */

int64_t prove_list_ops_length(Prove_List *list) {
    return prove_list_len(list);
}

/* ── First / Last (shared) ──────────────────────────────────── */

static Prove_Option _prove_list_ops_first(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[0]);
}

static Prove_Option _prove_list_ops_last(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[list->length - 1]);
}

/* ── First / Last (generic — List<Value>) ──────────────────── */

Prove_Option prove_list_ops_first(Prove_List *list) {
    return _prove_list_ops_first(list);
}

Prove_Option prove_list_ops_last(Prove_List *list) {
    return _prove_list_ops_last(list);
}

/* ── First / Last (int) ─────────────────────────────────────── */

Prove_Option prove_list_ops_first_int(Prove_List *list) {
    return _prove_list_ops_first(list);
}

Prove_Option prove_list_ops_last_int(Prove_List *list) {
    return _prove_list_ops_last(list);
}

/* ── First / Last (str) ─────────────────────────────────────── */

Prove_Option prove_list_ops_first_str(Prove_List *list) {
    return _prove_list_ops_first(list);
}

Prove_Option prove_list_ops_last_str(Prove_List *list) {
    return _prove_list_ops_last(list);
}

/* ── First / Last (float) ──────────────────────────────────── */

Prove_Option prove_list_ops_first_float(Prove_List *list) {
    return _prove_list_ops_first(list);
}

Prove_Option prove_list_ops_last_float(Prove_List *list) {
    return _prove_list_ops_last(list);
}

/* ── Value (get element at position) ───────────────────────── */

Prove_Option prove_list_ops_value(int64_t position, Prove_List *list) {
    if (position < 0 || position >= list->length) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[position]);
}

/* ── Empty ───────────────────────────────────────────────────── */

bool prove_list_ops_empty(Prove_List *list) {
    return list->length == 0;
}

/* ── Contains (int) ─────────────────────────────────────────── */

bool prove_list_ops_contains_int(Prove_List *list, int64_t value) {
    for (int64_t i = 0; i < list->length; i++) {
        if ((int64_t)(intptr_t)list->data[i] == value) return true;
    }
    return false;
}

/* ── Contains (str) ─────────────────────────────────────────── */

bool prove_list_ops_contains_str(Prove_List *list, Prove_String *value) {
    for (int64_t i = 0; i < list->length; i++) {
        if (prove_string_eq((Prove_String *)list->data[i], value)) return true;
    }
    return false;
}

/* ── Contains (float) ──────────────────────────────────────── */

bool prove_list_ops_contains_float(Prove_List *list, double value) {
    for (int64_t i = 0; i < list->length; i++) {
        double v;
        memcpy(&v, &list->data[i], sizeof(double));
        if (v == value) return true;
    }
    return false;
}

/* ── Index (int) ────────────────────────────────────────────── */

Prove_Option prove_list_ops_index_int(Prove_List *list, int64_t value) {
    for (int64_t i = 0; i < list->length; i++) {
        if ((int64_t)(intptr_t)list->data[i] == value) {
            return prove_option_some((Prove_Value *)(intptr_t)i);
        }
    }
    return prove_option_none();
}

/* ── Index (str) ────────────────────────────────────────────── */

Prove_Option prove_list_ops_index_str(Prove_List *list, Prove_String *value) {
    for (int64_t i = 0; i < list->length; i++) {
        if (prove_string_eq((Prove_String *)list->data[i], value)) {
            return prove_option_some((Prove_Value *)(intptr_t)i);
        }
    }
    return prove_option_none();
}

/* ── Index (float) ─────────────────────────────────────────── */

Prove_Option prove_list_ops_index_float(Prove_List *list, double value) {
    for (int64_t i = 0; i < list->length; i++) {
        double v;
        memcpy(&v, &list->data[i], sizeof(double));
        if (v == value) {
            return prove_option_some((Prove_Value *)(intptr_t)i);
        }
    }
    return prove_option_none();
}

/* ── Slice ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_slice(Prove_List *list, int64_t start, int64_t end) {
    /* Clamp bounds */
    if (start < 0) start = 0;
    if (end > list->length) end = list->length;
    if (start >= end) return prove_list_new(4);

    int64_t count = end - start;
    Prove_List *result = prove_list_new(count);
    memcpy(result->data, list->data + start,
           sizeof(void *) * (size_t)count);
    result->length = count;
    return result;
}

/* ── Reverse ─────────────────────────────────────────────────── */

Prove_List *prove_list_ops_reverse(Prove_List *list) {
    if (list->length == 0) {
        return prove_list_new(4);
    }

    Prove_List *result = prove_list_new(list->length);
    result->length = list->length;
    for (int64_t i = 0; i < list->length; i++) {
        result->data[i] = list->data[list->length - 1 - i];
    }
    return result;
}

/* ── Sort (int) ─────────────────────────────────────────────── */

#define ISORT_THRESHOLD 24

/* Typed insertion sort for small lists — avoids qsort callback overhead */
static void _isort_int_list(void **data, int64_t n) {
    for (int64_t i = 1; i < n; i++) {
        void *key = data[i];
        int64_t kv = (int64_t)(intptr_t)key;
        int64_t j = i - 1;
        while (j >= 0 && (int64_t)(intptr_t)data[j] > kv) {
            data[j + 1] = data[j];
            j--;
        }
        data[j + 1] = key;
    }
}

static int _cmp_int(const void *a, const void *b) {
    int64_t va = (int64_t)(intptr_t)*(void *const *)a;
    int64_t vb = (int64_t)(intptr_t)*(void *const *)b;
    return (va > vb) - (va < vb);
}

Prove_List *prove_list_ops_sort_int(Prove_List *list) {
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    if (list->length > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
        result->length = list->length;
        if (list->length > 1) {
            if (list->length <= ISORT_THRESHOLD) {
                _isort_int_list(result->data, result->length);
            } else {
                qsort(result->data, (size_t)result->length, sizeof(void *), _cmp_int);
            }
        }
    }
    return result;
}

/* ── Sort (str) ─────────────────────────────────────────────── */

static int _cmp_str(const void *a, const void *b) {
    Prove_String *sa = *(Prove_String *const *)a;
    Prove_String *sb = *(Prove_String *const *)b;
    int64_t min_len = sa->length < sb->length ? sa->length : sb->length;
    int cmp = memcmp(sa->data, sb->data, (size_t)min_len);
    if (cmp != 0) return cmp;
    return (sa->length > sb->length) - (sa->length < sb->length);
}

Prove_List *prove_list_ops_sort_str(Prove_List *list) {
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    if (list->length > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
        result->length = list->length;
        if (list->length > 1) {
            qsort(result->data, (size_t)result->length, sizeof(void *), _cmp_str);
        }
    }
    return result;
}

/* ── Sort (float) ──────────────────────────────────────────── */

static int _cmp_float(const void *a, const void *b) {
    double va, vb;
    memcpy(&va, a, sizeof(double));
    memcpy(&vb, b, sizeof(double));
    return (va > vb) - (va < vb);
}

Prove_List *prove_list_ops_sort_float(Prove_List *list) {
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    if (list->length > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
        result->length = list->length;
        if (list->length > 1) {
            qsort(result->data, (size_t)result->length, sizeof(void *), _cmp_float);
        }
    }
    return result;
}

/* ── Range ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_range(int64_t start, int64_t end) {
    if (start >= end) return prove_list_new(4);

    int64_t count = end - start;
    Prove_List *result = prove_list_new(count);
    for (int64_t i = 0; i < count; i++) {
        result->data[i] = (void *)(intptr_t)(start + i);
    }
    result->length = count;
    return result;
}

/* ── Get (unchecked indexed access) ─────────────────────────── */

int64_t prove_list_ops_get_int(Prove_List *list, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= list->length) prove_panic("list: index out of bounds");
#endif
    return (int64_t)(intptr_t)list->data[idx];
}

Prove_String *prove_list_ops_get_str(Prove_List *list, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= list->length) prove_panic("list: index out of bounds");
#endif
    return (Prove_String *)list->data[idx];
}

double prove_list_ops_get_float(Prove_List *list, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= list->length) prove_panic("list: index out of bounds");
#endif
    void *raw = list->data[idx];
    double val;
    memcpy(&val, &raw, sizeof(double));
    return val;
}

void *prove_list_ops_get_value(Prove_List *list, int64_t idx) {
#ifndef PROVE_RELEASE
    if (idx < 0 || idx >= list->length) prove_panic("list: index out of bounds");
#endif
    return list->data[idx];
}

/* ── Get safe (bounds-checked, returns Option) ───────────────── */

Prove_Option prove_list_ops_get_safe_int(Prove_List *list, int64_t idx) {
    if (idx < 0 || idx >= list->length) return prove_option_none();
    return prove_option_some((Prove_Value *)(intptr_t)(int64_t)(intptr_t)list->data[idx]);
}

Prove_Option prove_list_ops_get_safe_str(Prove_List *list, int64_t idx) {
    if (idx < 0 || idx >= list->length) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[idx]);
}

Prove_Option prove_list_ops_get_safe_float(Prove_List *list, int64_t idx) {
    if (idx < 0 || idx >= list->length) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[idx]);
}

Prove_Option prove_list_ops_get_safe_value(Prove_List *list, int64_t idx) {
    if (idx < 0 || idx >= list->length) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[idx]);
}

Prove_List *prove_list_ops_range_step(int64_t start, int64_t end, int64_t step) {
    if (step == 0) return prove_list_new(4);
    if (step > 0 && start >= end) return prove_list_new(4);
    if (step < 0 && start <= end) return prove_list_new(4);

    int64_t diff = end - start;
    int64_t count = (diff + step - (diff > 0 ? 1 : -1)) / step;
    if (count < 0) count = 0;
    Prove_List *result = prove_list_new(count > 0 ? count : 4);
    int64_t idx = 0;
    if (step > 0) {
        for (int64_t i = start; i < end; i += step) {
            result->data[idx++] = (void *)(intptr_t)i;
        }
    } else {
        for (int64_t i = start; i > end; i += step) {
            result->data[idx++] = (void *)(intptr_t)i;
        }
    }
    result->length = idx;
    return result;
}

/* ── Set (copy-on-write) ─────────────────────────────────────── */

Prove_List *prove_list_ops_set(Prove_List *list, int64_t idx, void *value) {
#ifndef PROVE_RELEASE
    if (!list || idx < 0 || idx > list->length) return list;
#endif
    if (idx == list->length) {
        Prove_List *result = prove_list_new(list->length + 1);
        if (list->length > 0) {
            memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
        }
        result->data[idx] = value;
        result->length = list->length + 1;
        return result;
    }
    /* Copy-on-write: mutate in-place when sole owner */
    if (list->header.refcount == 1) {
        list->data[idx] = value;
        return list;
    }
    Prove_List *result = prove_list_new(list->length);
    if (idx > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)idx);
    }
    result->data[idx] = value;
    if (idx + 1 < list->length) {
        memcpy(result->data + idx + 1, list->data + idx + 1,
               sizeof(void *) * (size_t)(list->length - idx - 1));
    }
    result->length = list->length;
    return result;
}

/* ── Remove (copy-on-write) ──────────────────────────────────── */

Prove_List *prove_list_ops_remove(Prove_List *list, int64_t idx) {
#ifndef PROVE_RELEASE
    if (!list || idx < 0 || idx >= list->length) return list;
#endif
    int64_t new_len = list->length - 1;
    Prove_List *result = prove_list_new(new_len > 0 ? new_len : 4);
    if (idx > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)idx);
    }
    if (idx < new_len) {
        memcpy(result->data + idx, list->data + idx + 1,
               sizeof(void *) * (size_t)(new_len - idx));
    }
    result->length = new_len;
    return result;
}

/* ── Extend (concatenate two lists) ──────────────────────────── */

Prove_List *prove_list_ops_extend(Prove_List *list, Prove_List *other) {
    int64_t new_len = list->length + other->length;
    Prove_List *result = prove_list_new(new_len);
    if (list->length > 0) {
        memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
    }
    if (other->length > 0) {
        memcpy(result->data + list->length, other->data,
               sizeof(void *) * (size_t)other->length);
    }
    result->length = new_len;
    return result;
}

/* ── Replace (int, single value) ────────────────────────────── */

Prove_List *prove_list_ops_replace_int(Prove_List *list, int64_t old_val, int64_t new_val) {
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    for (int64_t i = 0; i < list->length; i++) {
        if ((int64_t)(intptr_t)list->data[i] == old_val) {
            result->data[i] = (void *)(intptr_t)new_val;
        } else {
            result->data[i] = list->data[i];
        }
    }
    result->length = list->length;
    return result;
}

/* ── Replace (str, single value) ────────────────────────────── */

Prove_List *prove_list_ops_replace_str(Prove_List *list, Prove_String *old_val, Prove_String *new_val) {
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    for (int64_t i = 0; i < list->length; i++) {
        if (prove_string_eq((Prove_String *)list->data[i], old_val)) {
            prove_retain(&new_val->header);
            result->data[i] = (void *)new_val;
        } else {
            prove_retain(&((Prove_String *)list->data[i])->header);
            result->data[i] = list->data[i];
        }
    }
    result->length = list->length;
    return result;
}

/* ── Replace (int, list-to-list mapping) ────────────────────── */

Prove_List *prove_list_ops_replace_map_int(Prove_List *list, Prove_List *old_vals, Prove_List *new_vals) {
#ifndef PROVE_RELEASE
    if (old_vals->length != new_vals->length) return list;
#endif
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    for (int64_t i = 0; i < list->length; i++) {
        int64_t elem = (int64_t)(intptr_t)list->data[i];
        void *replaced = list->data[i];
        for (int64_t j = 0; j < old_vals->length; j++) {
            if (elem == (int64_t)(intptr_t)old_vals->data[j]) {
                replaced = new_vals->data[j];
                break;
            }
        }
        result->data[i] = replaced;
    }
    result->length = list->length;
    return result;
}

/* ── Replace (str, list-to-list mapping) ────────────────────── */

Prove_List *prove_list_ops_replace_map_str(Prove_List *list, Prove_List *old_vals, Prove_List *new_vals) {
#ifndef PROVE_RELEASE
    if (old_vals->length != new_vals->length) return list;
#endif
    Prove_List *result = prove_list_new(list->length > 0 ? list->length : 4);
    for (int64_t i = 0; i < list->length; i++) {
        Prove_String *elem = (Prove_String *)list->data[i];
        void *replaced = list->data[i];
        for (int64_t j = 0; j < old_vals->length; j++) {
            if (prove_string_eq(elem, (Prove_String *)old_vals->data[j])) {
                replaced = new_vals->data[j];
                break;
            }
        }
        prove_retain(&((Prove_String *)replaced)->header);
        result->data[i] = replaced;
    }
    result->length = list->length;
    return result;
}
