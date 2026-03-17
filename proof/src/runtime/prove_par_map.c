/* Prove par_map — thread-based parallel map over lists.
 *
 * Uses pthreads for parallelism.  Safe because Prove's pure verbs
 * (transforms, validates, reads, creates, matches) guarantee no
 * shared mutable state.
 *
 * Falls back to sequential map when:
 *   - num_workers <= 1
 *   - list length <= num_workers (overhead not worth it)
 *   - pthreads unavailable (compile-time check)
 */

#include "prove_par_map.h"
#include <stdlib.h>

#ifdef _WIN32
/* Windows: sequential fallback only (pthreads not available). */
#define PROVE_HAS_PTHREADS 0
#else
#define PROVE_HAS_PTHREADS 1
#include <pthread.h>
#endif

/* ── Sequential fallback ─────────────────────────────────────── */

static Prove_List *_par_map_sequential(Prove_List *list, Prove_MapFn fn) {
    int64_t len = prove_list_len(list);
    Prove_List *result = prove_list_new(len);
    for (int64_t i = 0; i < len; i++) {
        prove_list_push(result, fn(prove_list_get(list, i)));
    }
    return result;
}

#if PROVE_HAS_PTHREADS

/* ── Threaded implementation ─────────────────────────────────── */

typedef struct {
    Prove_List *input;
    void      **output;     /* pre-allocated output slots */
    Prove_MapFn fn;
    int64_t     start;
    int64_t     end;
} _ParMapChunk;

static void *_par_map_worker(void *arg) {
    _ParMapChunk *chunk = (_ParMapChunk *)arg;
    for (int64_t i = chunk->start; i < chunk->end; i++) {
        chunk->output[i] = chunk->fn(prove_list_get(chunk->input, i));
    }
    return NULL;
}

Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, int64_t num_workers) {
    int64_t len = prove_list_len(list);
    if (len == 0) return prove_list_new(0);

    /* Fall back to sequential for trivial cases */
    if (num_workers <= 1 || len <= num_workers) {
        return _par_map_sequential(list, fn);
    }

    /* Cap workers to list length */
    if (num_workers > len) num_workers = len;

    /* Pre-allocate output buffer */
    void **output = (void **)calloc((size_t)len, sizeof(void *));
    if (!output) return _par_map_sequential(list, fn);

    /* Create chunk descriptors */
    int64_t chunk_size = (len + num_workers - 1) / num_workers;
    _ParMapChunk *chunks = (_ParMapChunk *)malloc(sizeof(_ParMapChunk) * (size_t)num_workers);
    pthread_t *threads = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)num_workers);
    if (!chunks || !threads) {
        free(output);
        free(chunks);
        free(threads);
        return _par_map_sequential(list, fn);
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

#else /* !PROVE_HAS_PTHREADS */

Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, int64_t num_workers) {
    (void)num_workers;
    return _par_map_sequential(list, fn);
}

#endif /* PROVE_HAS_PTHREADS */
