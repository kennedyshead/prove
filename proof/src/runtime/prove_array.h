#ifndef PROVE_ARRAY_H
#define PROVE_ARRAY_H

#include "prove_runtime.h"
#include "prove_list.h"
#include <stdbool.h>

/* ── Prove_Array (typed, contiguous, fixed-size) ─────────────── */

typedef struct {
    Prove_Header header;
    int64_t      length;
    int64_t      elem_size;  /* bytes per element */
    void        *data;       /* flat buffer */
} Prove_Array;

/* Create a new array of `length` elements, each `elem_size` bytes.
   Every element is initialised to `default_val` (by value copy of elem_size bytes). */
Prove_Array *prove_array_new(int64_t length, int64_t elem_size, const void *default_val);

/* Typed constructors for common element types */
Prove_Array *prove_array_new_bool(int64_t size, bool default_val);
Prove_Array *prove_array_new_int(int64_t size, int64_t default_val);
Prove_Array *prove_array_new_float(int64_t size, double default_val);

/* Get element at index as a void* (for pointer types) or intptr_t-cast (for scalars).
   The caller is responsible for casting back to the correct type. */
void *prove_array_get(Prove_Array *arr, int64_t idx);

/* Typed getters */
bool    prove_array_get_bool(Prove_Array *arr, int64_t idx);
int64_t prove_array_get_int(Prove_Array *arr, int64_t idx);
double  prove_array_get_float(Prove_Array *arr, int64_t idx);

/* Return a new array (copy-on-write) with element at idx replaced by val. */
Prove_Array *prove_array_set(Prove_Array *arr, int64_t idx, const void *val);

/* Typed setters (copy-on-write) */
Prove_Array *prove_array_set_bool(Prove_Array *arr, int64_t idx, bool val);
Prove_Array *prove_array_set_int(Prove_Array *arr, int64_t idx, int64_t val);
Prove_Array *prove_array_set_float(Prove_Array *arr, int64_t idx, double val);

/* In-place mutation — caller must own the array (:[Mutable]). */
/* Returns the array pointer for chaining */
Prove_Array *prove_array_set_mut(Prove_Array *arr, int64_t idx, const void *val);

/* Typed setters (in-place) for mutable arrays - returns arr for chaining */
Prove_Array *prove_array_set_mut_bool(Prove_Array *arr, int64_t idx, bool val);
Prove_Array *prove_array_set_mut_int(Prove_Array *arr, int64_t idx, int64_t val);
Prove_Array *prove_array_set_mut_float(Prove_Array *arr, int64_t idx, double val);

/* Number of elements. */
int64_t prove_array_length(Prove_Array *arr);

/* ── Bounds-checked access (returns Option) ──────────────────── */

#include "prove_option.h"

/* Bounds-checked get: returns Option<Boolean> */
Prove_Option prove_array_get_safe_bool(Prove_Array *arr, int64_t idx);

/* Bounds-checked get: returns Option<Integer> */
Prove_Option prove_array_get_safe_int(Prove_Array *arr, int64_t idx);

/* Bounds-checked get: returns Option<Float> */
Prove_Option prove_array_get_safe_float(Prove_Array *arr, int64_t idx);

/* Bounds-checked set (copy-on-write): returns Option<Array<Boolean>> */
Prove_Option prove_array_set_safe_bool(Prove_Array *arr, int64_t idx, bool val);

/* Bounds-checked set (copy-on-write): returns Option<Array<Integer>> */
Prove_Option prove_array_set_safe_int(Prove_Array *arr, int64_t idx, int64_t val);

/* Bounds-checked set (copy-on-write): returns Option<Array<Float>> */
Prove_Option prove_array_set_safe_float(Prove_Array *arr, int64_t idx, double val);

/* ── Higher-order operations ─────────────────────────────────── */

/* Map: apply fn to each element, producing a new array of same length.
   result_elem_size is the byte-width of the output element type. */
Prove_Array *prove_array_map(Prove_Array *arr, void *(*fn)(void *, void *),
                              void *ctx, int64_t result_elem_size);

/* Reduce: fold array from left with an accumulator. */
void *prove_array_reduce(Prove_Array *arr, void *init,
                          void *(*fn)(void *accum, void *elem, void *ctx),
                          void *ctx);

/* Each: call fn for side effect on each element. */
void prove_array_each(Prove_Array *arr, void (*fn)(void *, void *), void *ctx);

/* Filter: keep elements matching predicate; returns Prove_List
   because the output length is unknown at compile time. */
Prove_List *prove_array_filter(Prove_Array *arr, bool (*pred)(void *, void *), void *ctx);

/* ── Conversions ─────────────────────────────────────────────── */

/* Copy array contents to a new Prove_List (boxing each element). */
Prove_List *prove_array_to_list(Prove_Array *arr);

/* Copy a Prove_List into a new Prove_Array.
   elem_size is the byte width of the unboxed element type.
   unbox_fn extracts the raw value from a void* list element. */
Prove_Array *prove_array_from_list(Prove_List *list, int64_t elem_size,
                                    void (*unbox_fn)(void *elem, void *out));

#endif /* PROVE_ARRAY_H */
