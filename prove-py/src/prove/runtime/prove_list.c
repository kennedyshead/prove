#include "prove_list.h"
#include <string.h>

Prove_List *prove_list_new(size_t elem_size, int64_t initial_cap) {
    if (initial_cap < 4) initial_cap = 4;
    size_t data_bytes = elem_size * (size_t)initial_cap;
    Prove_List *l = (Prove_List *)prove_alloc(sizeof(Prove_List) + data_bytes);
    l->length = 0;
    l->capacity = initial_cap;
    l->elem_size = elem_size;
    return l;
}

void prove_list_push(Prove_List **list, const void *elem) {
    Prove_List *l = *list;
    if (l->length >= l->capacity) {
        int64_t new_cap = l->capacity * 2;
        size_t new_bytes = sizeof(Prove_List) + l->elem_size * (size_t)new_cap;
        Prove_List *new_list = (Prove_List *)realloc(l, new_bytes);
        if (!new_list) {
            prove_panic("list realloc failed");
        }
        new_list->capacity = new_cap;
        *list = new_list;
        l = new_list;
    }
    memcpy(l->data + l->elem_size * (size_t)l->length, elem, l->elem_size);
    l->length++;
}

void *prove_list_get(Prove_List *list, int64_t index) {
    if (index < 0 || index >= list->length) {
        prove_panic("list index out of bounds");
    }
    return list->data + list->elem_size * (size_t)index;
}

int64_t prove_list_len(Prove_List *list) {
    return list ? list->length : 0;
}

void prove_list_free(Prove_List *list, void (*free_elem)(void *)) {
    if (!list) return;
    if (free_elem) {
        for (int64_t i = 0; i < list->length; i++) {
            void *elem = list->data + list->elem_size * (size_t)i;
            free_elem(elem);
        }
    }
    free(list);
}
