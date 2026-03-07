#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_runtime.h"
#include "prove_string.h"


/* Memoization tables for pure functions */

/* _memo_transforms_add: 2 params, 1 stmts */
typedef struct _memo_transforms_add_entry {
    uint64_t key;
    int64_t value;
    bool valid;
} _memo_transforms_add_entry;
static _memo_transforms_add_entry _memo_transforms_add[32] = {0};

/* _memo_transforms_double: 1 params, 2 stmts */
typedef struct _memo_transforms_double_entry {
    uint64_t key;
    int64_t value;
    bool valid;
} _memo_transforms_double_entry;
static _memo_transforms_double_entry _memo_transforms_double[32] = {0};

/* _memo_transforms_abs_val: 1 params, 1 stmts */
typedef struct _memo_transforms_abs_val_entry {
    uint64_t key;
    int64_t value;
    bool valid;
} _memo_transforms_abs_val_entry;
static _memo_transforms_abs_val_entry _memo_transforms_abs_val[32] = {0};

int64_t prv_transforms_add_Integer_Integer(int64_t a, int64_t b);
int64_t prv_transforms_double_Integer(int64_t n);
int64_t prv_transforms_abs_val_Integer(int64_t n);

int64_t prv_transforms_add_Integer_Integer(int64_t a, int64_t b) {
    prove_region_enter(prove_global_region());
    int64_t _tmp1 = (a + b);
    return _tmp1;
    prove_region_exit(prove_global_region());
}

int64_t prv_transforms_double_Integer(int64_t n) {
    prove_region_enter(prove_global_region());
    int64_t result = (n * 2L);
    int64_t _tmp2 = result;
    return _tmp2;
    prove_region_exit(prove_global_region());
}

int64_t prv_transforms_abs_val_Integer(int64_t n) {
    prove_region_enter(prove_global_region());
    int64_t _tmp3 = n;
    return _tmp3;
    prove_region_exit(prove_global_region());
}

int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    prove_println(prove_string_from_int((_memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].valid && _memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].key == (((uint64_t)(10L)) * 31 + (uint64_t)(20L))) ? _memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].value : ((_memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].key = (((uint64_t)(10L)) * 31 + (uint64_t)(20L)), _memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].value = prv_transforms_add_Integer_Integer(10L, 20L), _memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].valid = 1, _memo_transforms_add[(((((uint64_t)(10L)) * 31 + (uint64_t)(20L))) % 32)].value))));
    prove_println(prove_string_from_int((_memo_transforms_double[(((uint64_t)(15L)) % 32)].valid && _memo_transforms_double[(((uint64_t)(15L)) % 32)].key == (uint64_t)(15L)) ? _memo_transforms_double[(((uint64_t)(15L)) % 32)].value : ((_memo_transforms_double[(((uint64_t)(15L)) % 32)].key = (uint64_t)(15L), _memo_transforms_double[(((uint64_t)(15L)) % 32)].value = prv_transforms_double_Integer(15L), _memo_transforms_double[(((uint64_t)(15L)) % 32)].valid = 1, _memo_transforms_double[(((uint64_t)(15L)) % 32)].value))));
    prove_println(prove_string_from_int((_memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].valid && _memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].key == (uint64_t)((-42L))) ? _memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].value : ((_memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].key = (uint64_t)((-42L)), _memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].value = prv_transforms_abs_val_Integer((-42L)), _memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].valid = 1, _memo_transforms_abs_val[(((uint64_t)((-42L))) % 32)].value))));
    prove_runtime_cleanup();
    return 0;
}

