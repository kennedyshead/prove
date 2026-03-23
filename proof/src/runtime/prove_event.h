#ifndef PROVE_EVENT_H
#define PROVE_EVENT_H

#include <stdbool.h>
#include <stddef.h>
#include "prove_coro.h"

#ifndef _WIN32
#include <pthread.h>
#endif

/* ── Event node (intrusive linked list) ────────────────────── */
typedef struct Prove_EventNode {
    struct Prove_EventNode *next;
    int    tag;        /* algebraic variant tag */
    void  *payload;    /* variant payload (NULL for unit variants) */
} Prove_EventNode;

/* ── Event queue (FIFO, thread-safe) ──────────────────────── */
typedef struct {
    Prove_EventNode *head;
    Prove_EventNode *tail;
    int  count;
    bool closed;       /* true after all workers finish */
#ifndef _WIN32
    pthread_mutex_t lock;
    pthread_cond_t  cond;
#endif
} Prove_EventNodeQueue;

/* ── API ───────────────────────────────────────────────────── */

/* Create a new empty event queue. */
Prove_EventNodeQueue *prove_event_queue_new(void);

/* Push an event onto the queue (called by attached workers). */
void prove_event_queue_send(Prove_EventNodeQueue *q, int tag, void *payload);

/* Receive the next event, yielding the coro until one is available.
 * Returns NULL if the queue is closed and empty. */
Prove_EventNode *prove_event_queue_recv(Prove_EventNodeQueue *q, Prove_Coro *coro);

/* Close the queue (no more events will be sent). */
void prove_event_queue_close(Prove_EventNodeQueue *q);

/* Free the queue and all remaining events. */
void prove_event_queue_free(Prove_EventNodeQueue *q);

#endif /* PROVE_EVENT_H */
