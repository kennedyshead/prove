#ifndef PROVE_TERMINAL_H
#define PROVE_TERMINAL_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_event.h"

/* ── Position type (matches UI.Position) ─────────────────────── */
#ifndef PROVE_POSITION_DEFINED
#define PROVE_POSITION_DEFINED
#define _PROVE_UNITY_Prove_Position
typedef struct Prove_Position {
    int64_t x;
    int64_t y;
} Prove_Position;
#endif

/* ── Terminal validation ─────────────────────────────────────── */

/* Check if stdout is connected to an interactive terminal. */
bool prove_terminal_validates(void);

/* ── Raw/cooked mode ─────────────────────────────────────────── */

/* Enable raw mode: disable line buffering, echo, signal processing.
 * Registers atexit handler to restore cooked mode on exit/crash. */
void prove_terminal_raw(void);

/* Restore cooked mode: re-enable line buffering, echo, signals. */
void prove_terminal_cooked(void);

/* ── Output ──────────────────────────────────────────────────── */

/* Write text at the current cursor position. */
void prove_terminal_write(Prove_String *text);

/* Write text at a specific screen position (column x, row y). */
void prove_terminal_write_at(int64_t x, int64_t y, Prove_String *text);

/* Clear the entire screen and reset cursor to (0, 0). */
void prove_terminal_clear(void);

/* Move the cursor to screen position (column x, row y). */
void prove_terminal_cursor(int64_t x, int64_t y);

/* ── Color ANSI ──────────────────────────────────────────────── */

/* Convert a Color or TextStyle name to its ANSI SGR escape sequence.
 * Delegates to prove_ansi_escape() from prove_ansi.h. */
Prove_String *prove_terminal_color_ansi(Prove_String *name);

/* ── Query ───────────────────────────────────────────────────── */

/* Get terminal dimensions. Returns Position where x=cols, y=rows. */
Prove_Position prove_terminal_size(void);

/* ── Key reading ─────────────────────────────────────────────── */

/* Read a single key press, returning the Key lookup code.
 * Handles escape sequences for arrow keys, function keys, etc.
 * Returns -1 on EOF. */
int64_t prove_terminal_read_key(void);

/* ── Lifecycle (used by renders loop) ────────────────────────── */

/* Initialize terminal backend and start input thread feeding events
 * into the given event queue. */
void prove_terminal_init(Prove_EventNodeQueue *eq);

/* Cleanup terminal backend: stop input thread, restore cooked mode. */
void prove_terminal_cleanup(void);

/* Check for pending SIGWINCH and send resize event to the queue.
 * Call from the main event loop, not from a signal handler. */
void prove_terminal_check_resize(Prove_EventNodeQueue *eq);

#endif /* PROVE_TERMINAL_H */
