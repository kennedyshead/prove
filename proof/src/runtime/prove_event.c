#include "prove_event.h"
#include "prove_runtime.h"
#include <stdlib.h>

#ifndef _WIN32
#include <unistd.h>
#endif

Prove_EventNodeQueue *prove_event_queue_new(void) {
    Prove_EventNodeQueue *q = malloc(sizeof(Prove_EventNodeQueue));
    if (!q) prove_panic("OOM: event queue allocation");
    q->head = NULL;
    q->tail = NULL;
    q->count = 0;
    q->closed = false;
#ifndef _WIN32
    pthread_mutex_init(&q->lock, NULL);
    pthread_cond_init(&q->cond, NULL);
#endif
    return q;
}

void prove_event_queue_send(Prove_EventNodeQueue *q, int tag, void *payload) {
    Prove_EventNode *ev = malloc(sizeof(Prove_EventNode));
    if (!ev) prove_panic("OOM: event allocation");
    ev->next = NULL;
    ev->tag = tag;
    ev->payload = payload;
#ifndef _WIN32
    pthread_mutex_lock(&q->lock);
#endif
    if (q->tail) {
        q->tail->next = ev;
    } else {
        q->head = ev;
    }
    q->tail = ev;
    q->count++;
#ifndef _WIN32
    pthread_cond_signal(&q->cond);
    pthread_mutex_unlock(&q->lock);
#endif
}

Prove_EventNode *prove_event_queue_recv(Prove_EventNodeQueue *q, Prove_Coro *coro) {
#ifndef _WIN32
    pthread_mutex_lock(&q->lock);
#endif
    while (!q->head) {
        if (q->closed) {
#ifndef _WIN32
            pthread_mutex_unlock(&q->lock);
#endif
            return NULL;
        }
        if (coro) {
            if (prove_coro_cancelled(coro)) {
#ifndef _WIN32
                pthread_mutex_unlock(&q->lock);
#endif
                return NULL;
            }
#ifndef _WIN32
            pthread_mutex_unlock(&q->lock);
#endif
            prove_coro_yield(coro);
#ifndef _WIN32
            pthread_mutex_lock(&q->lock);
#endif
        } else {
            /* No coroutine — wait on condvar until event or close */
#ifndef _WIN32
            pthread_cond_wait(&q->cond, &q->lock);
#endif
        }
    }
    /* Dequeue head */
    Prove_EventNode *ev = q->head;
    q->head = ev->next;
    if (!q->head) q->tail = NULL;
    q->count--;
#ifndef _WIN32
    pthread_mutex_unlock(&q->lock);
#endif
    return ev;
}

void prove_event_queue_close(Prove_EventNodeQueue *q) {
#ifndef _WIN32
    pthread_mutex_lock(&q->lock);
#endif
    q->closed = true;
#ifndef _WIN32
    pthread_cond_broadcast(&q->cond);
    pthread_mutex_unlock(&q->lock);
#endif
}

void prove_event_queue_free(Prove_EventNodeQueue *q) {
#ifndef _WIN32
    pthread_cond_destroy(&q->cond);
    pthread_mutex_destroy(&q->lock);
#endif
    Prove_EventNode *ev = q->head;
    while (ev) {
        Prove_EventNode *next = ev->next;
        /* Note: payload is owned by the region/GC, not freed here */
        free(ev);
        ev = next;
    }
    free(q);
}
