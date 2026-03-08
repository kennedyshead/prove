"""Tests for the Time C runtime module."""

from __future__ import annotations

import textwrap

from runtime_helpers import compile_and_run


class TestTimeNow:
    def test_now_returns_nonzero(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Time *t = prove_time_now();
                printf("%d\\n", t->seconds > 0 ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="now")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_now_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Time *t = prove_time_now();
                /* A time in the past should validate (it's before now) */
                t->seconds -= 10;
                printf("%d\\n", prove_time_validates(t) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="now_val")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestTimeDuration:
    def test_creates_duration(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Duration *d = prove_time_creates_duration(1, 30, 45);
                printf("%lld\\n", (long long)prove_time_reads_duration(d));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dur_create")
        assert result.returncode == 0
        # 1*3600 + 30*60 + 45 = 5445
        assert result.stdout.strip() == "5445"

    def test_validates_duration_positive(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Duration *d = prove_time_creates_duration(0, 0, 10);
                printf("%d\\n", prove_time_validates_duration(d) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dur_val")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_validates_duration_zero(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Duration *d = prove_time_creates_duration(0, 0, 0);
                printf("%d\\n", prove_time_validates_duration(d) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dur_zero")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_transforms_duration(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Time *start = prove_time_now();
                Prove_Time *stop = prove_time_now();
                stop->seconds = start->seconds + 5;
                Prove_Duration *d = prove_time_transforms_duration(start, stop);
                printf("%lld\\n", (long long)d->seconds);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dur_trans")
        assert result.returncode == 0
        assert result.stdout.strip() == "5"


class TestTimeDate:
    def test_creates_date(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *d = prove_time_creates_date(2024, 3, 15);
                printf("%d-%d-%d\\n", d->year, d->month, d->day);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="date_create")
        assert result.returncode == 0
        assert result.stdout.strip() == "2024-3-15"

    def test_validates_date_valid(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_time_validates_date(2024, 2, 29) ? 1 : 0);
                printf("%d\\n", prove_time_validates_date(2024, 12, 31) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="date_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # 2024 is leap year
        assert lines[1] == "1"

    def test_validates_date_invalid(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_time_validates_date(2023, 2, 29) ? 1 : 0);
                printf("%d\\n", prove_time_validates_date(2024, 13, 1) ? 1 : 0);
                printf("%d\\n", prove_time_validates_date(2024, 4, 31) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="date_inv")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "0"  # 2023 not leap year
        assert lines[1] == "0"  # month 13
        assert lines[2] == "0"  # April has 30 days

    def test_transforms_date_add_days(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *d = prove_time_creates_date(2024, 1, 30);
                Prove_Date *d2 = prove_time_transforms_date(d, 2);
                printf("%d-%d-%d\\n", d2->year, d2->month, d2->day);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="date_add")
        assert result.returncode == 0
        assert result.stdout.strip() == "2024-2-1"


class TestTimeDays:
    def test_reads_days_in_month(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_time_reads_days(2024, 1));
                printf("%lld\\n", (long long)prove_time_reads_days(2024, 2));
                printf("%lld\\n", (long long)prove_time_reads_days(2023, 2));
                printf("%lld\\n", (long long)prove_time_reads_days(2024, 4));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="days")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "31"  # January
        assert lines[1] == "29"  # Feb leap year
        assert lines[2] == "28"  # Feb non-leap
        assert lines[3] == "30"  # April

    def test_validates_leap_year(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_time_validates_days(2024) ? 1 : 0);
                printf("%d\\n", prove_time_validates_days(2023) ? 1 : 0);
                printf("%d\\n", prove_time_validates_days(2000) ? 1 : 0);
                printf("%d\\n", prove_time_validates_days(1900) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="leap")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # 2024 is leap
        assert lines[1] == "0"  # 2023 not leap
        assert lines[2] == "1"  # 2000 div by 400
        assert lines[3] == "0"  # 1900 div by 100 but not 400


class TestTimeWeekday:
    def test_reads_weekday(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                /* 2024-01-01 is a Monday */
                Prove_Date *d = prove_time_creates_date(2024, 1, 1);
                printf("%lld\\n", (long long)prove_time_reads_weekday(d));
                /* 2024-01-06 is a Saturday */
                Prove_Date *d2 = prove_time_creates_date(2024, 1, 6);
                printf("%lld\\n", (long long)prove_time_reads_weekday(d2));
                /* 2024-01-07 is a Sunday */
                Prove_Date *d3 = prove_time_creates_date(2024, 1, 7);
                printf("%lld\\n", (long long)prove_time_reads_weekday(d3));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="weekday")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "0"  # Monday
        assert lines[1] == "5"  # Saturday
        assert lines[2] == "6"  # Sunday

    def test_validates_weekend(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *mon = prove_time_creates_date(2024, 1, 1);
                Prove_Date *sat = prove_time_creates_date(2024, 1, 6);
                Prove_Date *sun = prove_time_creates_date(2024, 1, 7);
                printf("%d\\n", prove_time_validates_weekday(mon) ? 1 : 0);
                printf("%d\\n", prove_time_validates_weekday(sat) ? 1 : 0);
                printf("%d\\n", prove_time_validates_weekday(sun) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="weekend")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "0"  # Monday not weekend
        assert lines[1] == "1"  # Saturday is weekend
        assert lines[2] == "1"  # Sunday is weekend


class TestTimeClock:
    def test_creates_clock(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Clock *c = prove_time_creates_clock(14, 30, 45);
                printf("%d:%d:%d\\n", c->hour, c->minute, c->second);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="clock")
        assert result.returncode == 0
        assert result.stdout.strip() == "14:30:45"

    def test_validates_clock(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_time_validates_clock(0, 0, 0) ? 1 : 0);
                printf("%d\\n", prove_time_validates_clock(23, 59, 59) ? 1 : 0);
                printf("%d\\n", prove_time_validates_clock(24, 0, 0) ? 1 : 0);
                printf("%d\\n", prove_time_validates_clock(12, 60, 0) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="clock_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # midnight valid
        assert lines[1] == "1"  # 23:59:59 valid
        assert lines[2] == "0"  # hour 24 invalid
        assert lines[3] == "0"  # minute 60 invalid


class TestTimeDateTime:
    def test_creates_and_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *date = prove_time_creates_date(2024, 6, 15);
                Prove_Clock *clock = prove_time_creates_clock(10, 30, 0);
                Prove_DateTime *dt = prove_time_creates_datetime(date, clock);
                printf("%d\\n", prove_time_validates_datetime(dt) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dt")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_roundtrip_datetime(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *date = prove_time_creates_date(2024, 6, 15);
                Prove_Clock *clock = prove_time_creates_clock(10, 30, 0);
                Prove_DateTime *dt = prove_time_creates_datetime(date, clock);
                Prove_Time *t = prove_time_transforms_datetime(dt);
                Prove_DateTime *dt2 = prove_time_reads_datetime(t);
                printf("%d-%d-%d %d:%d:%d\\n",
                       dt2->date->year, dt2->date->month, dt2->date->day,
                       dt2->clock->hour, dt2->clock->minute, dt2->clock->second);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dt_rt")
        assert result.returncode == 0
        assert result.stdout.strip() == "2024-6-15 10:30:0"


class TestTimeFormat:
    def test_format_time_iso(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Date *date = prove_time_creates_date(2024, 3, 15);
                Prove_Clock *clock = prove_time_creates_clock(14, 30, 45);
                Prove_DateTime *dt = prove_time_creates_datetime(date, clock);
                Prove_Time *t = prove_time_transforms_datetime(dt);
                Prove_String *pat = prove_string_from_cstr("ISO8601");
                Prove_String *s = prove_time_format_time(t, pat);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="fmt_iso")
        assert result.returncode == 0
        assert result.stdout.strip() == "2024-03-15T14:30:45"

    def test_format_duration(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_Duration *d = prove_time_creates_duration(2, 5, 30);
                Prove_String *pat = prove_string_from_cstr("");
                Prove_String *s = prove_time_format_duration(d, pat);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="fmt_dur")
        assert result.returncode == 0
        assert result.stdout.strip() == "02:05:30"

    def test_parse_time_iso(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *src = prove_string_from_cstr("2024-03-15T14:30:45");
                Prove_String *pat = prove_string_from_cstr("ISO8601");
                Prove_Time *t = prove_time_parse_time(src, pat);
                Prove_String *s = prove_time_format_time(t, pat);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="parse_iso")
        assert result.returncode == 0
        assert result.stdout.strip() == "2024-03-15T14:30:45"

    def test_validates_time_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_time.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *pat = prove_string_from_cstr("ISO8601");
                Prove_String *good = prove_string_from_cstr("2024-03-15T14:30:45");
                Prove_String *bad = prove_string_from_cstr("not-a-time");
                printf("%d\\n", prove_time_validates_time(good, pat) ? 1 : 0);
                printf("%d\\n", prove_time_validates_time(bad, pat) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="val_str")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"
        assert lines[1] == "0"
