/* Prove par_map / par_filter / par_reduce — thread-based parallel HOFs.
 *
 * Uses pthreads for parallelism.  Safe because Prove's pure verbs
 * (transforms, validates, reads, creates, matches) guarantee no
 * shared mutable state.
 *
 * Falls back to sequential when:
 *   - num_workers resolves to <= 1
 *   - list length <= num_workers (overhead not worth it)
 *   - pthreads unavailable (compile-time check)
 *
 * When num_workers == 0, auto-detects based on available CPU cores.
 */

#include "prove_par_map.h"
#include <stdlib.h>

#ifdef _WIN32
/* Windows: sequential fallback only (pthreads not available). */
#define PROVE_HAS_PTHREADS 0
#else
#define PROVE_HAS_PTHREADS 1
#include <pthread.h>
#include <unistd.h>
#endif

/* ── Auto-detect worker count ──────────────────────────────────── */

static int64_t _auto_workers(int64_t requested) {
    if (requested > 0) return requested;
#if PROVE_HAS_PTHREADS
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return (n > 0) ? (int64_t)n : 4;
#else
    return 1;
#endif
}

/* ── Sequential fallbacks ──────────────────────────────────────── */

static Prove_List *_par_map_sequential(Prove_List *list, Prove_MapFn fn, void *ctx) {
    int64_t len = prove_list_len(list);
    Prove_List *result = prove_list_new(len);
    for (int64_t i = 0; i < len; i++) {
        prove_list_push(result, fn(prove_list_get(list, i), ctx));
    }
    return result;
}

static Prove_List *_par_filter_sequential(Prove_List *list, Prove_FilterFn pred, void *ctx) {
    int64_t len = prove_list_len(list);
    Prove_List *result = prove_list_new(len);
    for (int64_t i = 0; i < len; i++) {
        void *elem = prove_list_get(list, i);
        if (pred(elem, ctx)) {
            prove_list_push(result, elem);
        }
    }
    return result;
}

static void *_par_reduce_sequential(Prove_List *list, void *init, Prove_ReduceFn fn, void *ctx) {
    int64_t len = prove_list_len(list);
    void *accum = init;
    for (int64_t i = 0; i < len; i++) {
        accum = fn(accum, prove_list_get(list, i), ctx);
    }
    return accum;
}

#if PROVE_HAS_PTHREADS

/* ── Threaded map implementation ───────────────────────────────── */

typedef struct {
    Prove_List *input;
    void      **output;     /* pre-allocated output slots */
    Prove_MapFn fn;
    void       *ctx;
    int64_t     start;
    int64_t     end;
} _ParMapChunk;

static void *_par_map_worker(void *arg) {
    _ParMapChunk *chunk = (_ParMapChunk *)arg;
    for (int64_t i = chunk->start; i < chunk->end; i++) {
        chunk->output[i] = chunk->fn(prove_list_get(chunk->input, i), chunk->ctx);
    }
    return NULL;
}

Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, void *ctx, int64_t num_workers) {
    int64_t len = prove_list_len(list);
    if (len == 0) return prove_list_new(0);

    num_workers = _auto_workers(num_workers);

    /* Fall back to sequential for trivial cases */
    if (num_workers <= 1 || len <= num_workers) {
        return _par_map_sequential(list, fn, ctx);
    }

    /* Cap workers to list length */
    if (num_workers > len) num_workers = len;

    /* Pre-allocate output buffer */
    void **output = (void **)calloc((size_t)len, sizeof(void *));
    if (!output) return _par_map_sequential(list, fn, ctx);

    /* Create chunk descriptors */
    int64_t chunk_size = (len + num_workers - 1) / num_workers;
    _ParMapChunk *chunks = (_ParMapChunk *)malloc(sizeof(_ParMapChunk) * (size_t)num_workers);
    pthread_t *threads = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)num_workers);
    if (!chunks || !threads) {
        free(output);
        free(chunks);
        free(threads);
        return _par_map_sequential(list, fn, ctx);
    }

    int64_t actual = 0;
    for (int64_t i = 0; i < num_workers; i++) {
        int64_t s = i * chunk_size;
        if (s >= len) break;
        int64_t e = s + chunk_size;
        if (e > len) e = len;

        chunks[actual].input  = list;
        chunks[actual].output = output;
        chunks[actual].fn     = fn;
        chunks[actual].ctx    = ctx;
        chunks[actual].start  = s;
        chunks[actual].end    = e;

        if (pthread_create(&threads[actual], NULL, _par_map_worker, &chunks[actual]) != 0) {
            /* Thread creation failed — run this chunk sequentially */
            _par_map_worker(&chunks[actual]);
        } else {
            actual++;
        }
    }

    /* Join all threads */
    for (int64_t i = 0; i < actual; i++) {
        pthread_join(threads[i], NULL);
    }

    /* Build result list from output buffer */
    Prove_List *result = prove_list_new(len);
    for (int64_t i = 0; i < len; i++) {
        prove_list_push(result, output[i]);
    }

    free(output);
    free(chunks);
    free(threads);
    return result;
}

/* ── Threaded filter implementation ────────────────────────────── */

typedef struct {
    Prove_List   *input;
    bool         *keep;      /* per-element predicate results */
    Prove_FilterFn pred;
    void          *ctx;
    int64_t       start;
    int64_t       end;
} _ParFilterChunk;

static void *_par_filter_worker(void *arg) {
    _ParFilterChunk *chunk = (_ParFilterChunk *)arg;
    for (int64_t i = chunk->start; i < chunk->end; i++) {
        chunk->keep[i] = chunk->pred(prove_list_get(chunk->input, i), chunk->ctx);
    }
    return NULL;
}

Prove_List *prove_par_filter(Prove_List *list, Prove_FilterFn pred, void *ctx, int64_t num_workers) {
    int64_t len = prove_list_len(list);
    if (len == 0) return prove_list_new(0);

    num_workers = _auto_workers(num_workers);

    if (num_workers <= 1 || len <= num_workers) {
        return _par_filter_sequential(list, pred, ctx);
    }

    if (num_workers > len) num_workers = len;

    bool *keep = (bool *)calloc((size_t)len, sizeof(bool));
    if (!keep) return _par_filter_sequential(list, pred, ctx);

    int64_t chunk_size = (len + num_workers - 1) / num_workers;
    _ParFilterChunk *chunks = (_ParFilterChunk *)malloc(sizeof(_ParFilterChunk) * (size_t)num_workers);
    pthread_t *threads = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)num_workers);
    if (!chunks || !threads) {
        free(keep);
        free(chunks);
        free(threads);
        return _par_filter_sequential(list, pred, ctx);
    }

    int64_t actual = 0;
    for (int64_t i = 0; i < num_workers; i++) {
        int64_t s = i * chunk_size;
        if (s >= len) break;
        int64_t e = s + chunk_size;
        if (e > len) e = len;

        chunks[actual].input = list;
        chunks[actual].keep  = keep;
        chunks[actual].pred  = pred;
        chunks[actual].ctx   = ctx;
        chunks[actual].start = s;
        chunks[actual].end   = e;

        if (pthread_create(&threads[actual], NULL, _par_filter_worker, &chunks[actual]) != 0) {
            _par_filter_worker(&chunks[actual]);
        } else {
            actual++;
        }
    }

    for (int64_t i = 0; i < actual; i++) {
        pthread_join(threads[i], NULL);
    }

    /* Build result preserving order */
    Prove_List *result = prove_list_new(len);
    for (int64_t i = 0; i < len; i++) {
        if (keep[i]) {
            prove_list_push(result, prove_list_get(list, i));
        }
    }

    free(keep);
    free(chunks);
    free(threads);
    return result;
}

/* ── Threaded reduce implementation ────────────────────────────── */

/* Parallel reduce strategy: partition the list, reduce each chunk
 * sequentially with the given fn, then merge chunk results sequentially.
 * The first chunk starts with `init`; subsequent chunks start with the
 * first element of their partition (so fn must be associative for true
 * parallelism — the compiler enforces pure verbs which makes this safe
 * for the common numeric cases). */

typedef struct {
    Prove_List   *input;
    Prove_ReduceFn fn;
    void         *ctx;
    void         *init;
    void         *result;
    int64_t       start;
    int64_t       end;
} _ParReduceChunk;

static void *_par_reduce_worker(void *arg) {
    _ParReduceChunk *chunk = (_ParReduceChunk *)arg;
    void *accum = chunk->init;
    for (int64_t i = chunk->start; i < chunk->end; i++) {
        accum = chunk->fn(accum, prove_list_get(chunk->input, i), chunk->ctx);
    }
    chunk->result = accum;
    return NULL;
}

void *prove_par_reduce(Prove_List *list, void *init, Prove_ReduceFn fn, void *ctx, int64_t num_workers) {
    int64_t len = prove_list_len(list);
    if (len == 0) return init;

    num_workers = _auto_workers(num_workers);

    if (num_workers <= 1 || len <= num_workers) {
        return _par_reduce_sequential(list, init, fn, ctx);
    }

    if (num_workers > len) num_workers = len;

    int64_t chunk_size = (len + num_workers - 1) / num_workers;
    _ParReduceChunk *chunks = (_ParReduceChunk *)malloc(sizeof(_ParReduceChunk) * (size_t)num_workers);
    pthread_t *threads = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)num_workers);
    if (!chunks || !threads) {
        free(chunks);
        free(threads);
        return _par_reduce_sequential(list, init, fn, ctx);
    }

    int64_t actual_chunks = 0;
    for (int64_t i = 0; i < num_workers; i++) {
        int64_t s = i * chunk_size;
        if (s >= len) break;
        int64_t e = s + chunk_size;
        if (e > len) e = len;

        chunks[actual_chunks].input  = list;
        chunks[actual_chunks].fn     = fn;
        chunks[actual_chunks].ctx    = ctx;
        chunks[actual_chunks].start  = s;
        chunks[actual_chunks].end    = e;
        chunks[actual_chunks].result = NULL;

        if (i == 0) {
            /* First chunk uses the caller-provided init */
            chunks[actual_chunks].init = init;
        } else {
            /* Subsequent chunks use their first element as init, start from s+1 */
            chunks[actual_chunks].init = prove_list_get(list, s);
            chunks[actual_chunks].start = s + 1;
        }

        actual_chunks++;
    }

    /* Launch threads */
    int64_t launched = 0;
    for (int64_t i = 0; i < actual_chunks; i++) {
        if (pthread_create(&threads[i], NULL, _par_reduce_worker, &chunks[i]) != 0) {
            _par_reduce_worker(&chunks[i]);
        } else {
            launched++;
        }
    }

    for (int64_t i = 0; i < actual_chunks; i++) {
        if (i < launched) {
            pthread_join(threads[i], NULL);
        }
    }

    /* Merge chunk results sequentially */
    void *result = chunks[0].result;
    for (int64_t i = 1; i < actual_chunks; i++) {
        result = fn(result, chunks[i].result, ctx);
    }

    free(chunks);
    free(threads);
    return result;
}

/* ── Threaded each implementation ──────────────────────────────── */

typedef struct {
    Prove_List  *input;
    Prove_EachFn fn;
    void        *ctx;
    int64_t      start;
    int64_t      end;
} _ParEachChunk;

static void _par_each_sequential(Prove_List *list, Prove_EachFn fn, void *ctx) {
    int64_t len = prove_list_len(list);
    for (int64_t i = 0; i < len; i++) {
        fn(prove_list_get(list, i), ctx);
    }
}

static void *_par_each_worker(void *arg) {
    _ParEachChunk *chunk = (_ParEachChunk *)arg;
    for (int64_t i = chunk->start; i < chunk->end; i++) {
        chunk->fn(prove_list_get(chunk->input, i), chunk->ctx);
    }
    return NULL;
}

void prove_par_each(Prove_List *list, Prove_EachFn fn, void *ctx, int64_t num_workers) {
    int64_t len = prove_list_len(list);
    if (len == 0) return;

    num_workers = _auto_workers(num_workers);

    if (num_workers <= 1 || len <= num_workers) {
        _par_each_sequential(list, fn, ctx);
        return;
    }

    if (num_workers > len) num_workers = len;

    int64_t chunk_size = (len + num_workers - 1) / num_workers;
    _ParEachChunk *chunks = (_ParEachChunk *)malloc(sizeof(_ParEachChunk) * (size_t)num_workers);
    pthread_t *threads = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)num_workers);
    if (!chunks || !threads) {
        free(chunks);
        free(threads);
        _par_each_sequential(list, fn, ctx);
        return;
    }

    int64_t actual = 0;
    for (int64_t i = 0; i < num_workers; i++) {
        int64_t s = i * chunk_size;
        if (s >= len) break;
        int64_t e = s + chunk_size;
        if (e > len) e = len;

        chunks[actual].input = list;
        chunks[actual].fn    = fn;
        chunks[actual].ctx   = ctx;
        chunks[actual].start = s;
        chunks[actual].end   = e;

        if (pthread_create(&threads[actual], NULL, _par_each_worker, &chunks[actual]) != 0) {
            _par_each_worker(&chunks[actual]);
        } else {
            actual++;
        }
    }

    for (int64_t i = 0; i < actual; i++) {
        pthread_join(threads[i], NULL);
    }

    free(chunks);
    free(threads);
}

#else /* !PROVE_HAS_PTHREADS */

static void _par_each_sequential(Prove_List *list, Prove_EachFn fn, void *ctx) {
    int64_t len = prove_list_len(list);
    for (int64_t i = 0; i < len; i++) {
        fn(prove_list_get(list, i), ctx);
    }
}

Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, void *ctx, int64_t num_workers) {
    (void)num_workers;
    return _par_map_sequential(list, fn, ctx);
}

Prove_List *prove_par_filter(Prove_List *list, Prove_FilterFn pred, void *ctx, int64_t num_workers) {
    (void)num_workers;
    return _par_filter_sequential(list, pred, ctx);
}

void *prove_par_reduce(Prove_List *list, void *init, Prove_ReduceFn fn, void *ctx, int64_t num_workers) {
    (void)num_workers;
    return _par_reduce_sequential(list, init, fn, ctx);
}

void prove_par_each(Prove_List *list, Prove_EachFn fn, void *ctx, int64_t num_workers) {
    (void)num_workers;
    _par_each_sequential(list, fn, ctx);
}

#endif /* PROVE_HAS_PTHREADS */
