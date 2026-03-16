#include "prove_hof.h"

Prove_List *prove_list_map(
    Prove_List *list,
    void *(*fn)(void *)
) {
#ifndef PROVE_RELEASE
    if (!list) prove_panic("hof: null list");
#endif
    Prove_List *out = prove_list_new(list->length);
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        void *mapped = fn(elem);
        prove_list_push(out, mapped);
    }
    return out;
}

void prove_list_each(
    Prove_List *list,
    void (*fn)(void *)
) {
#ifndef PROVE_RELEASE
    if (!list) prove_panic("hof: null list");
#endif
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        fn(elem);
    }
}

Prove_List *prove_list_filter(
    Prove_List *list,
    bool (*pred)(void *)
) {
#ifndef PROVE_RELEASE
    if (!list) prove_panic("hof: null list");
#endif
    int64_t hint = list->length < 8 ? list->length : list->length / 2;
    if (hint < 4) hint = 4;
    Prove_List *out = prove_list_new(hint);
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        if (pred(elem)) {
            prove_list_push(out, elem);
        }
    }
    return out;
}

void *prove_list_reduce(
    Prove_List *list,
    void *init,
    void *(*fn)(void *accum, void *elem)
) {
#ifndef PROVE_RELEASE
    if (!list) prove_panic("hof: null list");
#endif
    void *accum = init;
    for (int64_t i = 0; i < list->length; i++) {
        void *elem = prove_list_get(list, i);
        accum = fn(accum, elem);
    }
    return accum;
}
