/* Prove runtime startup — initialises arena + intern table. */
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <execinfo.h>

#include "prove_runtime.h"
#include "prove_arena.h"
#include "prove_intern.h"

static ProveArena *_global_arena = NULL;
static ProveInternTable *_global_intern = NULL;

#define MAX_BACKTRACE 64

static void prove_backtrace_handler(int sig) {
    void *buffer[MAX_BACKTRACE];
    int n = backtrace(buffer, MAX_BACKTRACE);
    char **symbols = backtrace_symbols(buffer, n);
    
    fprintf(stderr, "\n========================================\n");
    fprintf(stderr, "Prove runtime error (signal %d):\n", sig);
    fprintf(stderr, "========================================\n");
    fprintf(stderr, "Stack trace (%d frames):\n", n);
    
    for (int i = 1; i < n && symbols != NULL; i++) {
        fprintf(stderr, "  [%d] %s\n", i, symbols[i]);
    }
    
    if (symbols) {
        free(symbols);
    }
    
    fprintf(stderr, "========================================\n");
    exit(1);
}

void prove_runtime_init(void) {
    /* Set up signal handlers for backtraces */
    signal(SIGSEGV, prove_backtrace_handler);
    signal(SIGABRT, prove_backtrace_handler);
    signal(SIGFPE, prove_backtrace_handler);
    signal(SIGILL, prove_backtrace_handler);
    
    _global_arena = prove_arena_new(0);
    _global_intern = prove_intern_table_new(_global_arena);
}

void prove_runtime_cleanup(void) {
    if (_global_intern) {
        prove_intern_table_free(_global_intern);
        _global_intern = NULL;
    }
    if (_global_arena) {
        prove_arena_free(_global_arena);
        _global_arena = NULL;
    }
}
