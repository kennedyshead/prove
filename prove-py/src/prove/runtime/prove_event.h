#ifndef PROVE_EVENT_H
#define PROVE_EVENT_H

#include <stdbool.h>
#include <stddef.h>
#include "prove_coro.h"

/* ── Event node (intrusive linked list) ────────────────────── */
typedef struct Prove_Event {
    struct Prove_Event *next;
    int    tag;        /* algebraic variant tag */
    void  *payload;    /* variant payload (NULL for unit variants) */
} Prove_Event;

/* ── Event queue (FIFO, single-threaded) ───────────────────── */
typedef struct {
    Prove_Event *head;
    Prove_Event *tail;
    int  count;
    bool closed;       /* true after all workers finish */
} Prove_EventQueue;

/* ── API ───────────────────────────────────────────────────── */

/* Create a new empty event queue. */
Prove_EventQueue *prove_event_queue_new(void);

/* Push an event onto the queue (called by attached workers). */
void prove_event_queue_send(Prove_EventQueue *q, int tag, void *payload);

/* Receive the next event, yielding the coro until one is available.
 * Returns NULL if the queue is closed and empty. */
Prove_Event *prove_event_queue_recv(Prove_EventQueue *q, Prove_Coro *coro);

/* Close the queue (no more events will be sent). */
void prove_event_queue_close(Prove_EventQueue *q);

/* Free the queue and all remaining events. */
void prove_event_queue_free(Prove_EventQueue *q);

#endif /* PROVE_EVENT_H */
