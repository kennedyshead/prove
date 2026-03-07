#include "prove_list_ops.h"

/* ── Length ───────────────────────────────────────────────────── */

int64_t prove_list_ops_length(Prove_List *list) {
    return prove_list_len(list);
}

/* ── First / Last ────────────────────────────────────────────── */

Prove_Option_int64_t prove_list_ops_first_int(Prove_List *list) {
    if (!list || list->length == 0) {
        return Prove_Option_int64_t_none();
    }
    int64_t val = *(int64_t *)prove_list_get(list, 0);
    return Prove_Option_int64_t_some(val);
}

Prove_Option_Prove_Stringptr prove_list_ops_first_str(Prove_List *list) {
    if (!list || list->length == 0) {
        return Prove_Option_Prove_Stringptr_none();
    }
    Prove_String *val = *(Prove_String **)prove_list_get(list, 0);
    return Prove_Option_Prove_Stringptr_some(val);
}

Prove_Option_int64_t prove_list_ops_last_int(Prove_List *list) {
    if (!list || list->length == 0) {
        return Prove_Option_int64_t_none();
    }
    int64_t val = *(int64_t *)prove_list_get(list, list->length - 1);
    return Prove_Option_int64_t_some(val);
}

Prove_Option_Prove_Stringptr prove_list_ops_last_str(Prove_List *list) {
    if (!list || list->length == 0) {
        return Prove_Option_Prove_Stringptr_none();
    }
    Prove_String *val = *(Prove_String **)prove_list_get(list, list->length - 1);
    return Prove_Option_Prove_Stringptr_some(val);
}

/* ── Empty ───────────────────────────────────────────────────── */

bool prove_list_ops_empty(Prove_List *list) {
    return !list || list->length == 0;
}

/* ── Contains ────────────────────────────────────────────────── */

bool prove_list_ops_contains_int(Prove_List *list, int64_t value) {
    if (!list) return false;
    for (int64_t i = 0; i < list->length; i++) {
        int64_t elem = *(int64_t *)prove_list_get(list, i);
        if (elem == value) return true;
    }
    return false;
}

bool prove_list_ops_contains_str(Prove_List *list, Prove_String *value) {
    if (!list) return false;
    for (int64_t i = 0; i < list->length; i++) {
        Prove_String *elem = *(Prove_String **)prove_list_get(list, i);
        if (prove_string_eq(elem, value)) return true;
    }
    return false;
}

/* ── Index ───────────────────────────────────────────────────── */

Prove_Option_int64_t prove_list_ops_index_int(Prove_List *list, int64_t value) {
    if (!list) return Prove_Option_int64_t_none();
    for (int64_t i = 0; i < list->length; i++) {
        int64_t elem = *(int64_t *)prove_list_get(list, i);
        if (elem == value) return Prove_Option_int64_t_some(i);
    }
    return Prove_Option_int64_t_none();
}

Prove_Option_int64_t prove_list_ops_index_str(Prove_List *list, Prove_String *value) {
    if (!list) return Prove_Option_int64_t_none();
    for (int64_t i = 0; i < list->length; i++) {
        Prove_String *elem = *(Prove_String **)prove_list_get(list, i);
        if (prove_string_eq(elem, value)) return Prove_Option_int64_t_some(i);
    }
    return Prove_Option_int64_t_none();
}

/* ── Slice ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_slice(Prove_List *list, int64_t start, int64_t end) {
    if (!list) return prove_list_new(sizeof(int64_t), 4);

    /* Clamp bounds */
    if (start < 0) start = 0;
    if (end > list->length) end = list->length;
    if (start >= end) return prove_list_new(list->elem_size, 4);

    int64_t count = end - start;
    Prove_List *result = prove_list_new(list->elem_size, count);
    memcpy(result->data,
           list->data + list->elem_size * (size_t)start,
           list->elem_size * (size_t)count);
    result->length = count;
    return result;
}

/* ── Reverse ─────────────────────────────────────────────────── */

Prove_List *prove_list_ops_reverse(Prove_List *list) {
    if (!list || list->length == 0) {
        return prove_list_new(sizeof(int64_t), 4);
    }

    Prove_List *result = prove_list_new(list->elem_size, list->length);
    result->length = list->length;
    size_t esz = list->elem_size;
    for (int64_t i = 0; i < list->length; i++) {
        memcpy(result->data + esz * (size_t)i,
               list->data + esz * (size_t)(list->length - 1 - i),
               esz);
    }
    return result;
}

/* ── Sort ────────────────────────────────────────────────────── */

static int _cmp_int(const void *a, const void *b) {
    int64_t va = *(const int64_t *)a;
    int64_t vb = *(const int64_t *)b;
    return (va > vb) - (va < vb);
}

static int _cmp_str(const void *a, const void *b) {
    Prove_String *sa = *(Prove_String *const *)a;
    Prove_String *sb = *(Prove_String *const *)b;
    int64_t min_len = sa->length < sb->length ? sa->length : sb->length;
    int cmp = memcmp(sa->data, sb->data, (size_t)min_len);
    if (cmp != 0) return cmp;
    return (sa->length > sb->length) - (sa->length < sb->length);
}

Prove_List *prove_list_ops_sort_int(Prove_List *list) {
    if (!list) return prove_list_new(sizeof(int64_t), 4);
    Prove_List *result = prove_list_new(list->elem_size, list->length > 0 ? list->length : 4);
    if (list->length > 0) {
        memcpy(result->data, list->data, list->elem_size * (size_t)list->length);
        result->length = list->length;
        if (list->length > 1) {
            qsort(result->data, (size_t)result->length, result->elem_size, _cmp_int);
        }
    }
    return result;
}

Prove_List *prove_list_ops_sort_str(Prove_List *list) {
    if (!list) return prove_list_new(sizeof(Prove_String *), 4);
    Prove_List *result = prove_list_new(list->elem_size, list->length > 0 ? list->length : 4);
    if (list->length > 0) {
        memcpy(result->data, list->data, list->elem_size * (size_t)list->length);
        result->length = list->length;
        if (list->length > 1) {
            qsort(result->data, (size_t)result->length, result->elem_size, _cmp_str);
        }
    }
    return result;
}

/* ── Range ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_range(int64_t start, int64_t end) {
    if (start >= end) return prove_list_new(sizeof(int64_t), 4);

    int64_t count = end - start;
    Prove_List *result = prove_list_new(sizeof(int64_t), count);
    for (int64_t i = start; i < end; i++) {
        prove_list_push(&result, &i);
    }
    return result;
}
