#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_time.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_Time* now = prove_time_now();
    prove_retain(now);
    prove_println(prove_string_from_cstr("got current time"));
    Prove_Date* d = prove_time_creates_date(2026L, 3L, 6L);
    prove_retain(d);
    prove_println(prove_string_concat(prove_string_from_cstr("days in march 2026: "), prove_string_from_int(prove_time_reads_days(2026L, 3L))));
    Prove_Clock* c = prove_time_creates_clock(14L, 30L, 0L);
    prove_retain(c);
    prove_println(prove_string_from_cstr("clock created: 14:30:00"));
    Prove_Duration* dur = prove_time_creates_duration(1L, 30L, 0L);
    prove_retain(dur);
    prove_println(prove_string_from_cstr("duration: 1h 30m"));
    prove_runtime_cleanup();
    return 0;
}

