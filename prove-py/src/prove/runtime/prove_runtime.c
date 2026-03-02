/* Prove runtime startup — initialises arena + intern table. */
#include "prove_runtime.h"
#include "prove_arena.h"
#include "prove_intern.h"

static ProveArena *_global_arena = NULL;
static ProveInternTable *_global_intern = NULL;

void prove_runtime_init(void) {
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
