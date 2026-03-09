#ifndef PROVE_CORO_H
#define PROVE_CORO_H

#include <stddef.h>
#include <stdbool.h>

/* ── Stackful coroutines via ucontext_t (POSIX) ─────────────────
 *
 * On POSIX systems (macOS, Linux) coroutines use ucontext_t for
 * true stackful cooperative multitasking.
 *
 * On Windows (or when ucontext is unavailable) a sequential fallback
 * is used: coroutines run to completion immediately without yielding.
 * The same API compiles and produces correct single-threaded results.
 */

#if defined(_WIN32) || defined(_WIN64)
#  define PROVE_CORO_SEQUENTIAL 1
#else
#  include <ucontext.h>
#  define PROVE_CORO_SEQUENTIAL 0
#endif

typedef enum {
    PROVE_CORO_CREATED,
    PROVE_CORO_RUNNING,
    PROVE_CORO_SUSPENDED,
    PROVE_CORO_DONE
} Prove_CoroState;

typedef struct Prove_Coro {
#if !PROVE_CORO_SEQUENTIAL
    ucontext_t  ctx;
    ucontext_t  caller_ctx;
    void       *stack;
    size_t      stack_size;
#endif
    Prove_CoroState state;
    void       *result;     /* result slot for attached */
    void       *arg;        /* argument passed on start */
    int         cancelled;  /* cancellation flag */
    void      (*fn)(struct Prove_Coro *);  /* body function (sequential mode) */
} Prove_Coro;

#define PROVE_CORO_STACK_DEFAULT (64 * 1024)

Prove_Coro *prove_coro_new(void (*fn)(Prove_Coro *), size_t stack_size);
void  prove_coro_start(Prove_Coro *coro, void *arg);
void  prove_coro_resume(Prove_Coro *coro);
void  prove_coro_yield(Prove_Coro *coro);
void  prove_coro_cancel(Prove_Coro *coro);
bool  prove_coro_done(Prove_Coro *coro);
bool  prove_coro_cancelled(Prove_Coro *coro);
void  prove_coro_free(Prove_Coro *coro);

#endif /* PROVE_CORO_H */
