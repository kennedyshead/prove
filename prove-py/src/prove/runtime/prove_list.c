#include "prove_list.h"
#include <string.h>

Prove_List *prove_list_new(int64_t initial_cap) {
    if (initial_cap < 4) initial_cap = 4;
    Prove_List *l = (Prove_List *)prove_alloc(sizeof(Prove_List));
    l->data = (void **)calloc((size_t)initial_cap, sizeof(void *));
    if (!l->data) prove_panic("list data alloc failed");
    l->length = 0;
    l->capacity = initial_cap;
    l->is_region = false;
    return l;
}

Prove_List *prove_list_new_region(ProveRegion *r, int64_t initial_cap) {
    if (initial_cap < 4) initial_cap = 4;
    Prove_List *l = (Prove_List *)prove_region_alloc(r, sizeof(Prove_List));
    if (!l) prove_panic("list region alloc failed");
    l->data = (void **)prove_region_alloc(r, sizeof(void *) * (size_t)initial_cap);
    if (!l->data) prove_panic("list data region alloc failed");
    l->length = 0;
    l->capacity = initial_cap;
    l->is_region = true;
    return l;
}

void prove_list_push(Prove_List *list, void *elem) {
    if (list->length >= list->capacity) {
        int64_t new_cap = list->capacity * 2;
        if (list->is_region) {
            /* Region data cannot be realloc'd — switch to heap */
            void **new_data = (void **)malloc(sizeof(void *) * (size_t)new_cap);
            if (!new_data) prove_panic("list realloc failed");
            memcpy(new_data, list->data, sizeof(void *) * (size_t)list->length);
            /* Old region buffer freed when region is freed */
            list->data = new_data;
            list->is_region = false;
        } else {
            void **new_data = (void **)realloc(list->data, sizeof(void *) * (size_t)new_cap);
            if (!new_data) prove_panic("list realloc failed");
            list->data = new_data;
        }
        list->capacity = new_cap;
    }
    list->data[list->length++] = elem;
}

void *prove_list_get(Prove_List *list, int64_t index) {
    if (index < 0 || index >= list->length) {
        prove_panic("list index out of bounds");
    }
    return list->data[index];
}

int64_t prove_list_len(Prove_List *list) {
    return list ? list->length : 0;
}

void prove_list_free(Prove_List *list) {
    if (!list) return;
    free(list->data);
    free(list);
}
