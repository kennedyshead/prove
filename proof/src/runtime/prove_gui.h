#ifndef PROVE_GUI_H
#define PROVE_GUI_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_event.h"

/* ── Widget functions (immediate-mode, called each frame) ──── */

/* Create or begin a named window with the given pixel dimensions.
 * Must be called once per frame before any widget calls. */
void prove_gui_window(Prove_String *title, int64_t width, int64_t height);

/* Render a clickable button. Returns true on the frame it's clicked. */
bool prove_gui_button(Prove_String *label);

/* Render a static text label. */
void prove_gui_label(Prove_String *text);

/* Render an editable text field. Returns the current string contents. */
Prove_String *prove_gui_text_input(Prove_String *label, Prove_String *value);

/* Render a checkbox. Returns the current boolean state. */
bool prove_gui_checkbox(Prove_String *label, bool checked);

/* Render a horizontal slider. Returns the current float value. */
double prove_gui_slider(Prove_String *label, double min, double max, double value);

/* Render a progress bar (current out of max). */
void prove_gui_progress(int64_t current, int64_t max);

/* Programmatically close the window and exit the render loop. */
void prove_gui_quit(void);

/* ── Lifecycle (used by renders loop) ─────────────────────── */

/* Initialize GUI backend: create SDL2 window, OpenGL context,
 * set up Nuklear, and start feeding events into the queue. */
void prove_gui_init(Prove_EventNodeQueue *eq);

/* Cleanup GUI backend: destroy Nuklear context, SDL window, etc. */
void prove_gui_cleanup(void);

/* Begin a new frame (poll SDL events, feed Nuklear input). */
void prove_gui_frame_begin(void);

/* End frame (render Nuklear draw commands via OpenGL, swap buffers). */
void prove_gui_frame_end(void);

#endif /* PROVE_GUI_H */
