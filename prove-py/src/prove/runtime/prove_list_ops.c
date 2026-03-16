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

/* ── First / Last (int) ─────────────────────────────────────── */

Prove_Option prove_list_ops_first_int(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[0]);
}

Prove_Option prove_list_ops_last_int(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[list->length - 1]);
}

/* ── First / Last (str) ─────────────────────────────────────── */

Prove_Option prove_list_ops_first_str(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[0]);
}

Prove_Option prove_list_ops_last_str(Prove_List *list) {
    if (list->length == 0) return prove_option_none();
    return prove_option_some((Prove_Value *)list->data[list->length - 1]);
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
            qsort(result->data, (size_t)result->length, sizeof(void *), _cmp_int);
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
