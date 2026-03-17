#ifndef _XOPEN_SOURCE
#  define _XOPEN_SOURCE 600
#endif
#include "prove_coro.h"
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* ── Sequential fallback (Windows / no ucontext) ─────────────── */

#if PROVE_CORO_SEQUENTIAL

Prove_Coro *prove_coro_new(void (*fn)(Prove_Coro *), size_t stack_size) {
    (void)stack_size;
    Prove_Coro *c = calloc(1, sizeof(Prove_Coro));
    if (!c) return NULL;
    c->fn    = fn;
    c->state = PROVE_CORO_CREATED;
    return c;
}

void prove_coro_start(Prove_Coro *coro, void *arg) {
    coro->arg   = arg;
    coro->state = PROVE_CORO_RUNNING;
    coro->fn(coro);
    coro->state = PROVE_CORO_DONE;
}

/* In sequential mode resume/yield are no-ops — body ran to completion. */
void prove_coro_resume(Prove_Coro *coro) { (void)coro; }
void prove_coro_yield(Prove_Coro *coro)  { (void)coro; }

void prove_coro_cancel(Prove_Coro *coro) {
    if (coro) coro->cancelled = 1;
}

bool prove_coro_done(Prove_Coro *coro) {
    return coro && coro->state == PROVE_CORO_DONE;
}

bool prove_coro_cancelled(Prove_Coro *coro) {
    return coro && coro->cancelled;
}

void prove_coro_free(Prove_Coro *coro) {
    free(coro);
}

#else /* POSIX ucontext_t implementation */

/* Trampoline: called by makecontext — bridges ucontext to our fn. */
static void _coro_trampoline(uint32_t hi, uint32_t lo) {
    uintptr_t ptr = ((uintptr_t)hi << 32) | (uintptr_t)lo;
    Prove_Coro *coro = (Prove_Coro *)(void *)ptr;
    coro->fn(coro);
    coro->state = PROVE_CORO_DONE;
    /* Return to caller_ctx */
    swapcontext(&coro->ctx, &coro->caller_ctx);
}

Prove_Coro *prove_coro_new(void (*fn)(Prove_Coro *), size_t stack_size) {
    if (stack_size == 0) stack_size = PROVE_CORO_STACK_DEFAULT;
    Prove_Coro *c = calloc(1, sizeof(Prove_Coro));
    if (!c) return NULL;
    c->stack = malloc(stack_size);
    if (!c->stack) { free(c); return NULL; }
    c->stack_size = stack_size;
    c->fn         = fn;
    c->state      = PROVE_CORO_CREATED;

    if (getcontext(&c->ctx) != 0) {
        free(c->stack);
        free(c);
        return NULL;
    }
    c->ctx.uc_stack.ss_sp   = c->stack;
    c->ctx.uc_stack.ss_size = stack_size;
    c->ctx.uc_link          = NULL; /* we manage returns manually */

    /* Split pointer into two uint32_t args for makecontext portability. */
    uintptr_t ptr = (uintptr_t)(void *)c;
    uint32_t  hi  = (uint32_t)(ptr >> 32);
    uint32_t  lo  = (uint32_t)(ptr & 0xFFFFFFFFu);
    makecontext(&c->ctx, (void (*)(void))_coro_trampoline, 2, hi, lo);

    return c;
}

void prove_coro_start(Prove_Coro *coro, void *arg) {
    coro->arg   = arg;
    coro->state = PROVE_CORO_RUNNING;
    swapcontext(&coro->caller_ctx, &coro->ctx);
}

void prove_coro_resume(Prove_Coro *coro) {
    if (!coro || coro->state == PROVE_CORO_DONE) return;
    coro->state = PROVE_CORO_RUNNING;
    swapcontext(&coro->caller_ctx, &coro->ctx);
}

void prove_coro_yield(Prove_Coro *coro) {
    coro->state = PROVE_CORO_SUSPENDED;
    swapcontext(&coro->ctx, &coro->caller_ctx);
}

void prove_coro_cancel(Prove_Coro *coro) {
    if (coro) coro->cancelled = 1;
}

bool prove_coro_done(Prove_Coro *coro) {
    return coro && coro->state == PROVE_CORO_DONE;
}

bool prove_coro_cancelled(Prove_Coro *coro) {
    return coro && coro->cancelled;
}

void prove_coro_free(Prove_Coro *coro) {
    if (!coro) return;
    free(coro->stack);
    free(coro);
}

#endif /* PROVE_CORO_SEQUENTIAL */
