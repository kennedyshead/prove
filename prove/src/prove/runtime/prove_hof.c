#include "prove_hof.h"
#include <string.h>

Prove_List *prove_list_map(
    Prove_List *list,
    void *(*fn)(const void *),
    size_t result_elem_size
) {
    if (!list) return prove_list_new(result_elem_size, 4);
    Prove_List *out = prove_list_new(result_elem_size, list->length);
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        void *mapped = fn(elem);
        prove_list_push(&out, &mapped);
    }
    return out;
}

Prove_List *prove_list_filter(
    Prove_List *list,
    bool (*pred)(const void *)
) {
    if (!list) return prove_list_new(list ? list->elem_size : sizeof(int64_t), 4);
    Prove_List *out = prove_list_new(list->elem_size, list->length);
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        if (pred(elem)) {
            prove_list_push(&out, elem);
        }
    }
    return out;
}

void prove_list_reduce(
    Prove_List *list,
    void *accum,
    void (*fn)(void *accum, const void *elem)
) {
    if (!list) return;
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        fn(accum, elem);
    }
}
