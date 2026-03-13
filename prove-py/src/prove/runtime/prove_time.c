#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "prove_time.h"
#include <time.h>
#include <stdio.h>

/* ── Helpers ─────────────────────────────────────────────────── */

static int _is_leap_year(int32_t year) {
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

static int32_t _days_in_month(int32_t year, int32_t month) {
    static const int32_t days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (month < 1 || month > 12) return 0;
    if (month == 2 && _is_leap_year(year)) return 29;
    return days[month];
}

/* Zeller-like day-of-week: 0=Monday..6=Sunday */
static int32_t _day_of_week(int32_t year, int32_t month, int32_t day) {
    /* Tomohiko Sakamoto's algorithm */
    static const int t[] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
    int y = year;
    if (month < 3) y -= 1;
    int dow = (y + y/4 - y/100 + y/400 + t[month - 1] + day) % 7;
    /* Sakamoto returns 0=Sunday..6=Saturday, convert to 0=Monday..6=Sunday */
    return (dow + 6) % 7;
}

static void _epoch_to_date_clock(int64_t epoch_secs, int32_t *year, int32_t *month,
                                  int32_t *day, int32_t *hour, int32_t *minute,
                                  int32_t *second) {
    time_t t = (time_t)epoch_secs;
    struct tm result;
#ifdef _WIN32
    gmtime_s(&result, &t);
#else
    gmtime_r(&t, &result);
#endif
    *year = result.tm_year + 1900;
    *month = result.tm_mon + 1;
    *day = result.tm_mday;
    *hour = result.tm_hour;
    *minute = result.tm_min;
    *second = result.tm_sec;
}

static int64_t _date_clock_to_epoch(int32_t year, int32_t month, int32_t day,
                                     int32_t hour, int32_t minute, int32_t second) {
    struct tm tm_val;
    memset(&tm_val, 0, sizeof(tm_val));
    tm_val.tm_year = year - 1900;
    tm_val.tm_mon = month - 1;
    tm_val.tm_mday = day;
    tm_val.tm_hour = hour;
    tm_val.tm_min = minute;
    tm_val.tm_sec = second;
    tm_val.tm_isdst = 0;
    /* Use timegm for UTC (_GNU_SOURCE defined at top) */
#if defined(__linux__) || defined(__APPLE__) || defined(_GNU_SOURCE)
    return (int64_t)timegm(&tm_val);
#else
    return (int64_t)mktime(&tm_val);
#endif
}

/* ── Time channel ────────────────────────────────────────────── */

Prove_Time *prove_time_now(void) {
    Prove_Time *t = prove_alloc(sizeof(Prove_Time));
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    t->seconds = (int64_t)ts.tv_sec;
    t->nanoseconds = (int32_t)ts.tv_nsec;
    return t;
}

bool prove_time_validates(Prove_Time *t) {
    if (!t) return false;
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    return t->seconds < now.tv_sec ||
           (t->seconds == now.tv_sec && t->nanoseconds < now.tv_nsec);
}

/* ── Duration channel ────────────────────────────────────────── */

Prove_Duration *prove_time_creates_duration(int64_t hours, int64_t minutes, int64_t seconds) {
    Prove_Duration *d = prove_alloc(sizeof(Prove_Duration));
    d->seconds = hours * 3600 + minutes * 60 + seconds;
    d->nanoseconds = 0;
    return d;
}

int64_t prove_time_reads_duration(Prove_Duration *d) {
    if (!d) return 0;
    return d->seconds;
}

bool prove_time_validates_duration(Prove_Duration *d) {
    if (!d) return false;
    return d->seconds > 0 || (d->seconds == 0 && d->nanoseconds > 0);
}

Prove_Duration *prove_time_transforms_duration(Prove_Time *start, Prove_Time *stop) {
    Prove_Duration *d = prove_alloc(sizeof(Prove_Duration));
    d->seconds = stop->seconds - start->seconds;
    d->nanoseconds = stop->nanoseconds - start->nanoseconds;
    if (d->nanoseconds < 0) {
        d->seconds -= 1;
        d->nanoseconds += 1000000000;
    }
    return d;
}

/* ── Date channel ────────────────────────────────────────────── */

Prove_Date *prove_time_reads_date(Prove_Time *t) {
    Prove_Date *d = prove_alloc(sizeof(Prove_Date));
    int32_t year, month, day, h, m, s;
    _epoch_to_date_clock(t->seconds, &year, &month, &day, &h, &m, &s);
    d->year = year;
    d->month = month;
    d->day = day;
    return d;
}

Prove_Date *prove_time_creates_date(int64_t year, int64_t month, int64_t day) {
    Prove_Date *d = prove_alloc(sizeof(Prove_Date));
    d->year = (int32_t)year;
    d->month = (int32_t)month;
    d->day = (int32_t)day;
    return d;
}

bool prove_time_validates_date(int64_t year, int64_t month, int64_t day) {
    if (month < 1 || month > 12) return false;
    int32_t max_day = _days_in_month((int32_t)year, (int32_t)month);
    return day >= 1 && day <= max_day;
}

Prove_Date *prove_time_transforms_date(Prove_Date *date, int64_t days) {
    /* Convert to epoch, add days, convert back */
    int64_t epoch = _date_clock_to_epoch(date->year, date->month, date->day, 12, 0, 0);
    epoch += days * 86400;
    Prove_Date *result = prove_alloc(sizeof(Prove_Date));
    int32_t year, month, day, h, m, s;
    _epoch_to_date_clock(epoch, &year, &month, &day, &h, &m, &s);
    result->year = year;
    result->month = month;
    result->day = day;
    return result;
}

/* ── DateTime channel ────────────────────────────────────────── */

Prove_DateTime *prove_time_reads_datetime(Prove_Time *t) {
    Prove_DateTime *dt = prove_alloc(sizeof(Prove_DateTime));
    int32_t year, month, day, hour, minute, second;
    _epoch_to_date_clock(t->seconds, &year, &month, &day, &hour, &minute, &second);
    dt->date = prove_alloc(sizeof(Prove_Date));
    dt->date->year = year;
    dt->date->month = month;
    dt->date->day = day;
    dt->clock = prove_alloc(sizeof(Prove_Clock));
    dt->clock->hour = hour;
    dt->clock->minute = minute;
    dt->clock->second = second;
    return dt;
}

Prove_DateTime *prove_time_creates_datetime(Prove_Date *date, Prove_Clock *clock) {
    Prove_DateTime *dt = prove_alloc(sizeof(Prove_DateTime));
    dt->date = date;
    dt->clock = clock;
    return dt;
}

bool prove_time_validates_datetime(Prove_DateTime *dt) {
    if (!dt || !dt->date || !dt->clock) return false;
    if (!prove_time_validates_date(dt->date->year, dt->date->month, dt->date->day))
        return false;
    if (!prove_time_validates_clock(dt->clock->hour, dt->clock->minute, dt->clock->second))
        return false;
    return true;
}

Prove_Time *prove_time_transforms_datetime(Prove_DateTime *dt) {
    Prove_Time *t = prove_alloc(sizeof(Prove_Time));
    t->seconds = _date_clock_to_epoch(dt->date->year, dt->date->month, dt->date->day,
                                       dt->clock->hour, dt->clock->minute, dt->clock->second);
    t->nanoseconds = 0;
    return t;
}

/* ── Days channel ────────────────────────────────────────────── */

int64_t prove_time_reads_days(int64_t year, int64_t month) {
    return (int64_t)_days_in_month((int32_t)year, (int32_t)month);
}

bool prove_time_validates_days(int64_t year) {
    return _is_leap_year((int32_t)year);
}

/* ── Weekday channel ─────────────────────────────────────────── */

int64_t prove_time_reads_weekday(Prove_Date *date) {
    return (int64_t)_day_of_week(date->year, date->month, date->day);
}

bool prove_time_validates_weekday(Prove_Date *date) {
    int32_t dow = _day_of_week(date->year, date->month, date->day);
    return dow >= 5; /* Saturday=5, Sunday=6 */
}

/* ── Clock channel ───────────────────────────────────────────── */

Prove_Clock *prove_time_reads_clock(Prove_Time *t) {
    Prove_Clock *c = prove_alloc(sizeof(Prove_Clock));
    int32_t year, month, day, hour, minute, second;
    _epoch_to_date_clock(t->seconds, &year, &month, &day, &hour, &minute, &second);
    c->hour = hour;
    c->minute = minute;
    c->second = second;
    return c;
}

Prove_Clock *prove_time_creates_clock(int64_t hour, int64_t minute, int64_t second) {
    Prove_Clock *c = prove_alloc(sizeof(Prove_Clock));
    c->hour = (int32_t)hour;
    c->minute = (int32_t)minute;
    c->second = (int32_t)second;
    return c;
}

bool prove_time_validates_clock(int64_t hour, int64_t minute, int64_t second) {
    return hour >= 0 && hour <= 23 &&
           minute >= 0 && minute <= 59 &&
           second >= 0 && second <= 59;
}

/* ── Format integration ──────────────────────────────────────── */

static int _str_eq(Prove_String *s, const char *cstr) {
    int64_t len = (int64_t)strlen(cstr);
    if (s->length != len) return 0;
    return memcmp(s->data, cstr, (size_t)len) == 0;
}

Prove_String *prove_time_format_time(Prove_Time *t, Prove_String *pattern) {
    int32_t year, month, day, hour, minute, second;
    _epoch_to_date_clock(t->seconds, &year, &month, &day, &hour, &minute, &second);
    char buf[64];
    if (_str_eq(pattern, "ISO8601") || _str_eq(pattern, "%Y-%m-%dT%H:%M:%S")) {
        snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
                 year, month, day, hour, minute, second);
    } else if (_str_eq(pattern, "%H:%M:%S")) {
        snprintf(buf, sizeof(buf), "%02d:%02d:%02d", hour, minute, second);
    } else if (_str_eq(pattern, "%Y-%m-%d")) {
        snprintf(buf, sizeof(buf), "%04d-%02d-%02d", year, month, day);
    } else {
        snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
                 year, month, day, hour, minute, second);
    }
    return prove_string_from_cstr(buf);
}

Prove_Time *prove_time_parse_time(Prove_String *source, Prove_String *pattern) {
    char src[128];
    int64_t copy_len = source->length < 127 ? source->length : 127;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int year = 0, month = 0, day = 0, hour = 0, minute = 0, second = 0;
    if (_str_eq(pattern, "ISO8601") || _str_eq(pattern, "%Y-%m-%dT%H:%M:%S")) {
        sscanf(src, "%d-%d-%dT%d:%d:%d", &year, &month, &day, &hour, &minute, &second);
    } else if (_str_eq(pattern, "%H:%M:%S")) {
        sscanf(src, "%d:%d:%d", &hour, &minute, &second);
        year = 1970; month = 1; day = 1;
    } else if (_str_eq(pattern, "%Y-%m-%d")) {
        sscanf(src, "%d-%d-%d", &year, &month, &day);
    }

    Prove_Time *t = prove_alloc(sizeof(Prove_Time));
    t->seconds = _date_clock_to_epoch(year, month, day, hour, minute, second);
    t->nanoseconds = 0;
    return t;
}

bool prove_time_validates_time(Prove_String *source, Prove_String *pattern) {
    char src[128];
    int64_t copy_len = source->length < 127 ? source->length : 127;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int y, m, d, h, mi, s;
    if (_str_eq(pattern, "ISO8601") || _str_eq(pattern, "%Y-%m-%dT%H:%M:%S")) {
        return sscanf(src, "%d-%d-%dT%d:%d:%d", &y, &m, &d, &h, &mi, &s) == 6;
    } else if (_str_eq(pattern, "%Y-%m-%d")) {
        return sscanf(src, "%d-%d-%d", &y, &m, &d) == 3;
    } else if (_str_eq(pattern, "%H:%M:%S")) {
        return sscanf(src, "%d:%d:%d", &h, &mi, &s) == 3;
    }
    return false;
}

Prove_String *prove_time_format_date(Prove_Date *d, Prove_String *pattern) {
    char buf[32];
    (void)pattern;
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", d->year, d->month, d->day);
    return prove_string_from_cstr(buf);
}

Prove_Date *prove_time_parse_date(Prove_String *source, Prove_String *pattern) {
    (void)pattern;
    char src[32];
    int64_t copy_len = source->length < 31 ? source->length : 31;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int y = 0, m = 0, d = 0;
    sscanf(src, "%d-%d-%d", &y, &m, &d);
    return prove_time_creates_date(y, m, d);
}

bool prove_time_validates_date_str(Prove_String *source, Prove_String *pattern) {
    (void)pattern;
    char src[32];
    int64_t copy_len = source->length < 31 ? source->length : 31;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int y, m, d;
    if (sscanf(src, "%d-%d-%d", &y, &m, &d) != 3) return false;
    return prove_time_validates_date(y, m, d);
}

Prove_String *prove_time_format_datetime(Prove_DateTime *dt, Prove_String *pattern) {
    char buf[64];
    (void)pattern;
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
             dt->date->year, dt->date->month, dt->date->day,
             dt->clock->hour, dt->clock->minute, dt->clock->second);
    return prove_string_from_cstr(buf);
}

Prove_DateTime *prove_time_parse_datetime(Prove_String *source, Prove_String *pattern) {
    (void)pattern;
    char src[64];
    int64_t copy_len = source->length < 63 ? source->length : 63;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int y = 0, mo = 0, d = 0, h = 0, mi = 0, s = 0;
    sscanf(src, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &s);
    Prove_Date *date = prove_time_creates_date(y, mo, d);
    Prove_Clock *clock = prove_time_creates_clock(h, mi, s);
    return prove_time_creates_datetime(date, clock);
}

bool prove_time_validates_datetime_str(Prove_String *source, Prove_String *pattern) {
    (void)pattern;
    char src[64];
    int64_t copy_len = source->length < 63 ? source->length : 63;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int y, mo, d, h, mi, s;
    return sscanf(src, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &s) == 6;
}

Prove_String *prove_time_format_duration(Prove_Duration *d, Prove_String *pattern) {
    (void)pattern;
    char buf[64];
    int64_t total = d->seconds;
    int64_t hours = total / 3600;
    int64_t minutes = (total % 3600) / 60;
    int64_t seconds = total % 60;
    snprintf(buf, sizeof(buf), "%02lld:%02lld:%02lld",
             (long long)hours, (long long)minutes, (long long)seconds);
    return prove_string_from_cstr(buf);
}

Prove_Duration *prove_time_parse_duration(Prove_String *source, Prove_String *pattern) {
    (void)pattern;
    char src[64];
    int64_t copy_len = source->length < 63 ? source->length : 63;
    memcpy(src, source->data, (size_t)copy_len);
    src[copy_len] = '\0';

    int h = 0, m = 0, s = 0;
    sscanf(src, "%d:%d:%d", &h, &m, &s);
    return prove_time_creates_duration(h, m, s);
}
