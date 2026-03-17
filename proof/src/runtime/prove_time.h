#ifndef PROVE_TIME_H
#define PROVE_TIME_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── Time types ──────────────────────────────────────────────── */

typedef struct {
    Prove_Header header;
    int64_t seconds;
    int32_t nanoseconds;
} Prove_Time;

typedef struct {
    Prove_Header header;
    int64_t seconds;
    int32_t nanoseconds;
} Prove_Duration;

typedef struct {
    Prove_Header header;
    int32_t year;
    int32_t month;
    int32_t day;
} Prove_Date;

typedef struct {
    Prove_Header header;
    int32_t hour;
    int32_t minute;
    int32_t second;
} Prove_Clock;

typedef struct {
    Prove_Header header;
    Prove_Date *date;
    Prove_Clock *clock;
} Prove_DateTime;

/* Weekday: 0=Monday..6=Sunday, stored as int64_t */

/* ── Time channel ────────────────────────────────────────────── */

Prove_Time *prove_time_now(void);
bool        prove_time_validates(Prove_Time *t);

/* ── Duration channel ────────────────────────────────────────── */

Prove_Duration *prove_time_creates_duration(int64_t hours, int64_t minutes, int64_t seconds);
int64_t         prove_time_reads_duration(Prove_Duration *d);
bool            prove_time_validates_duration(Prove_Duration *d);
Prove_Duration *prove_time_transforms_duration(Prove_Time *start, Prove_Time *stop);

/* ── Date channel ────────────────────────────────────────────── */

Prove_Date *prove_time_reads_date(Prove_Time *t);
Prove_Date *prove_time_creates_date(int64_t year, int64_t month, int64_t day);
bool        prove_time_validates_date(int64_t year, int64_t month, int64_t day);
Prove_Date *prove_time_transforms_date(Prove_Date *date, int64_t days);

/* ── DateTime channel ────────────────────────────────────────── */

Prove_DateTime *prove_time_reads_datetime(Prove_Time *t);
Prove_DateTime *prove_time_creates_datetime(Prove_Date *date, Prove_Clock *clock);
bool            prove_time_validates_datetime(Prove_DateTime *dt);
Prove_Time     *prove_time_transforms_datetime(Prove_DateTime *dt);

/* ── Days channel ────────────────────────────────────────────── */

int64_t prove_time_reads_days(int64_t year, int64_t month);
bool    prove_time_validates_days(int64_t year);

/* ── Weekday channel ─────────────────────────────────────────── */

int64_t prove_time_reads_weekday(Prove_Date *date);
bool    prove_time_validates_weekday(Prove_Date *date);

/* ── Clock channel ───────────────────────────────────────────── */

Prove_Clock *prove_time_reads_clock(Prove_Time *t);
Prove_Clock *prove_time_creates_clock(int64_t hour, int64_t minute, int64_t second);
bool         prove_time_validates_clock(int64_t hour, int64_t minute, int64_t second);

/* ── Format integration (C functions for Format module) ──────── */

Prove_String   *prove_time_format_time(Prove_Time *t, Prove_String *pattern);
Prove_Time     *prove_time_parse_time(Prove_String *source, Prove_String *pattern);
bool            prove_time_validates_time(Prove_String *source, Prove_String *pattern);
Prove_String   *prove_time_format_date(Prove_Date *d, Prove_String *pattern);
Prove_Date     *prove_time_parse_date(Prove_String *source, Prove_String *pattern);
bool            prove_time_validates_date_str(Prove_String *source, Prove_String *pattern);
Prove_String   *prove_time_format_datetime(Prove_DateTime *dt, Prove_String *pattern);
Prove_DateTime *prove_time_parse_datetime(Prove_String *source, Prove_String *pattern);
bool            prove_time_validates_datetime_str(Prove_String *source, Prove_String *pattern);
Prove_String   *prove_time_format_duration(Prove_Duration *d, Prove_String *pattern);
Prove_Duration *prove_time_parse_duration(Prove_String *source, Prove_String *pattern);

#endif /* PROVE_TIME_H */
