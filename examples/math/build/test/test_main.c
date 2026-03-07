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




/* ── Test infrastructure ──── */

static int _tests_run = 0;
static int _tests_passed = 0;
static int _tests_failed = 0;

static void _test_pass(const char *name) {
    _tests_run++;
    _tests_passed++;
}

static void _test_fail(const char *name, const char *msg) {
    _tests_run++;
    _tests_failed++;
    fprintf(stderr, "FAIL %s: %s\n", name, msg);
}

static uint64_t _rng_state = 0x12345678DEADBEEF;

static uint64_t _rng_next(void) {
    _rng_state ^= _rng_state << 13;
    _rng_state ^= _rng_state >> 7;
    _rng_state ^= _rng_state << 17;
    return _rng_state;
}

static int64_t _rng_int(void) {
    return (int64_t)_rng_next();
}

static int64_t _rng_int_range(int64_t lo, int64_t hi) {
    if (lo >= hi) return lo;
    uint64_t range = (uint64_t)(hi - lo + 1);
    return lo + (int64_t)(_rng_next() % range);
}

static double _rng_double(void) {
    return (double)_rng_next() / (double)UINT64_MAX * 200.0 - 100.0;
}

static void _test_prop_add_1(void) {
    for (int _i = 0; _i < 10; _i++) {
        int64_t a = _rng_int();
        int64_t b = _rng_int();
        if (!((a == a))) continue;
        int64_t _result = prv_transforms_add_Integer_Integer(a, b);
        if (!((_result == (a + b)))) {
            _test_fail("_test_prop_add_1", "ensures[0] violated");
            return;
        }
    }
    _test_pass("_test_prop_add_1");
}

static void _test_boundary_add_2(void) {
    (void)prv_transforms_add_Integer_Integer(0L, 0L);
    (void)prv_transforms_add_Integer_Integer(1L, 1L);
    (void)prv_transforms_add_Integer_Integer(-1L, -1L);
    (void)prv_transforms_add_Integer_Integer(INT64_MAX, INT64_MAX);
    (void)prv_transforms_add_Integer_Integer(INT64_MIN, INT64_MIN);
    _test_pass("_test_boundary_add_2");
}

static void _test_prop_double_3(void) {
    for (int _i = 0; _i < 10; _i++) {
        int64_t n = _rng_int();
        if (!((n == n))) continue;
        int64_t _result = prv_transforms_double_Integer(n);
        if (!((_result == (n * 2L)))) {
            _test_fail("_test_prop_double_3", "ensures[0] violated");
            return;
        }
    }
    _test_pass("_test_prop_double_3");
}

static void _test_boundary_double_4(void) {
    (void)prv_transforms_double_Integer(0L);
    (void)prv_transforms_double_Integer(1L);
    (void)prv_transforms_double_Integer(-1L);
    (void)prv_transforms_double_Integer(INT64_MAX);
    (void)prv_transforms_double_Integer(INT64_MIN);
    _test_pass("_test_boundary_double_4");
}

static void _test_prop_abs_val_5(void) {
    for (int _i = 0; _i < 10; _i++) {
        int64_t n = _rng_int();
        if (!((n >= 0L))) continue;
        int64_t _result = prv_transforms_abs_val_Integer(n);
        if (!((_result >= 0L))) {
            _test_fail("_test_prop_abs_val_5", "ensures[0] violated");
            return;
        }
    }
    _test_pass("_test_prop_abs_val_5");
}

static void _test_boundary_abs_val_6(void) {
    (void)prv_transforms_abs_val_Integer(0L);
    (void)prv_transforms_abs_val_Integer(1L);
    (void)prv_transforms_abs_val_Integer(-1L);
    (void)prv_transforms_abs_val_Integer(INT64_MAX);
    (void)prv_transforms_abs_val_Integer(INT64_MIN);
    _test_pass("_test_boundary_abs_val_6");
}

static void _test_believe_abs_val_7(void) {
    for (int _i = 0; _i < 30; _i++) {
        int64_t n = _rng_int();
        if (!((n >= 0L))) continue;
        int64_t _result = prv_transforms_abs_val_Integer(n);
        if (!((_result >= 0L))) {
            _test_fail("_test_believe_abs_val_7", "believe[0] violated");
            return;
        }
    }
    _test_pass("_test_believe_abs_val_7");
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    _test_prop_add_1();
    _test_boundary_add_2();
    _test_prop_double_3();
    _test_boundary_double_4();
    _test_prop_abs_val_5();
    _test_boundary_abs_val_6();
    _test_believe_abs_val_7();

    fprintf(stdout, "\n%d tests, %d passed, %d failed\n", _tests_run, _tests_passed, _tests_failed);
    return _tests_failed > 0 ? 1 : 0;
}
