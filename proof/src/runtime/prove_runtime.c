/* Prove runtime startup — initialises arena + intern table. */
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>

#if defined(__GLIBC__) || defined(__APPLE__)
  #include <execinfo.h>
#endif

#include "prove_runtime.h"
#include "prove_arena.h"
#include "prove_intern.h"
#include "prove_region.h"

extern void prove_string_init_statics(void);

static ProveArena *_global_arena = NULL;
static ProveInternTable *_global_intern = NULL;
static ProveRegion *_global_region = NULL;

#define MAX_BACKTRACE 64

/* Async-signal-safe helper: write a string literal to stderr */
static void _safe_write(const char *s) {
    size_t len = 0;
    while (s[len]) len++;
    (void)write(STDERR_FILENO, s, len);
}

static const char *_signal_name(int sig) {
    switch (sig) {
        case SIGSEGV: return "SIGSEGV — null pointer dereference or invalid memory access";
        case SIGABRT: return "SIGABRT — aborted (assertion failure or panic)";
        case SIGFPE:  return "SIGFPE — arithmetic error (division by zero)";
        case SIGILL:  return "SIGILL — illegal instruction";
        default:      return NULL;
    }
}

static void prove_backtrace_handler(int sig) {
    _safe_write("\n========================================\n");
    _safe_write("Prove runtime error: ");
    const char *name = _signal_name(sig);
    if (name) {
        _safe_write(name);
    } else {
        _safe_write("signal ");
        char numbuf[16];
        int idx = 0;
        int s = sig < 0 ? -sig : sig;
        if (sig < 0) numbuf[idx++] = '-';
        char tmp[16];
        int tlen = 0;
        do { tmp[tlen++] = '0' + (s % 10); s /= 10; } while (s > 0);
        for (int i = tlen - 1; i >= 0; i--) numbuf[idx++] = tmp[i];
        (void)write(STDERR_FILENO, numbuf, (size_t)idx);
    }
    _safe_write("\n========================================\n");

#if defined(__GLIBC__) || defined(__APPLE__)
    void *buffer[MAX_BACKTRACE];
    int n = backtrace(buffer, MAX_BACKTRACE);
    backtrace_symbols_fd(buffer, n, STDERR_FILENO);
#endif

    _safe_write("========================================\n");
    _exit(1);
}

void prove_runtime_init(void) {
    /* Set up signal handlers for backtraces */
    signal(SIGSEGV, prove_backtrace_handler);
    signal(SIGABRT, prove_backtrace_handler);
    signal(SIGFPE, prove_backtrace_handler);
    signal(SIGILL, prove_backtrace_handler);
    
    _global_arena = prove_arena_new(0);
    if (!_global_arena) {
        fprintf(stderr, "prove: out of memory (arena init)\n");
        exit(1);
    }
    _global_intern = prove_intern_table_new(_global_arena);
    if (!_global_intern) {
        fprintf(stderr, "prove: out of memory (intern table init)\n");
        exit(1);
    }
    _global_region = prove_region_new();
    if (!_global_region) {
        fprintf(stderr, "prove: out of memory (region init)\n");
        exit(1);
    }
    prove_string_init_statics();
}

void prove_runtime_cleanup(void) {
    if (_global_region) {
        prove_region_free(_global_region);
        _global_region = NULL;
    }
    if (_global_intern) {
        prove_intern_table_free(_global_intern);
        _global_intern = NULL;
    }
    if (_global_arena) {
        prove_arena_free(_global_arena);
        _global_arena = NULL;
    }
}

ProveRegion *prove_global_region(void) {
    return _global_region;
}
