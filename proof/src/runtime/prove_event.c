#include "prove_event.h"
#include "prove_runtime.h"
#include <stdlib.h>

Prove_EventNodeQueue *prove_event_queue_new(void) {
    Prove_EventNodeQueue *q = malloc(sizeof(Prove_EventNodeQueue));
    if (!q) prove_panic("OOM: event queue allocation");
    q->head = NULL;
    q->tail = NULL;
    q->count = 0;
    q->closed = false;
    return q;
}

void prove_event_queue_send(Prove_EventNodeQueue *q, int tag, void *payload) {
    Prove_EventNode *ev = malloc(sizeof(Prove_EventNode));
    if (!ev) prove_panic("OOM: event allocation");
    ev->next = NULL;
    ev->tag = tag;
    ev->payload = payload;
    if (q->tail) {
        q->tail->next = ev;
    } else {
        q->head = ev;
    }
    q->tail = ev;
    q->count++;
}

Prove_EventNode *prove_event_queue_recv(Prove_EventNodeQueue *q, Prove_Coro *coro) {
    while (!q->head) {
        if (q->closed) return NULL;      /* all workers done, no more events */
        if (prove_coro_cancelled(coro)) return NULL;
        prove_coro_yield(coro);          /* cooperatively wait */
    }
    /* Dequeue head */
    Prove_EventNode *ev = q->head;
    q->head = ev->next;
    if (!q->head) q->tail = NULL;
    q->count--;
    return ev;
}

void prove_event_queue_close(Prove_EventNodeQueue *q) {
    q->closed = true;
}

void prove_event_queue_free(Prove_EventNodeQueue *q) {
    Prove_EventNode *ev = q->head;
    while (ev) {
        Prove_EventNode *next = ev->next;
        /* Note: payload is owned by the region/GC, not freed here */
        free(ev);
        ev = next;
    }
    free(q);
}
