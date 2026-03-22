/*
 * prove_gui.c — Graphic module C runtime.
 *
 * Wraps Nuklear (immediate-mode GUI) with an SDL2 + OpenGL backend.
 * All widget functions are called per-frame inside a renders/Draw arm.
 *
 * Nuklear is vendored as a single header (MIT / Public Domain).
 * SDL2 is the only external dependency.
 */

#include "prove_gui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── Platform detection ─────────────────────────────────────── */
#ifdef _WIN32
  #define WIN32_LEAN_AND_MEAN
  #include <windows.h>
#endif

/* ── SDL2 + OpenGL headers ──────────────────────────────────── */
#include <SDL2/SDL.h>
#include <SDL2/SDL_opengl.h>

/* ── Nuklear configuration ──────────────────────────────────── */
#define NK_INCLUDE_FIXED_TYPES
#define NK_INCLUDE_STANDARD_IO
#define NK_INCLUDE_STANDARD_VARARGS
#define NK_INCLUDE_DEFAULT_ALLOCATOR
#define NK_INCLUDE_VERTEX_BUFFER_OUTPUT
#define NK_INCLUDE_FONT_BAKING
#define NK_INCLUDE_DEFAULT_FONT
#define NK_IMPLEMENTATION
#define NK_SDL_GL2_IMPLEMENTATION
#include "vendor/nuklear.h"

/* ── Nuklear SDL2/GL2 backend (inline) ──────────────────────── */
/*
 * Minimal SDL2+OpenGL2 backend for Nuklear, adapted from the official
 * nuklear demo/sdl_opengl2 example. Inlined here to avoid extra files.
 */

struct nk_sdl_device {
    struct nk_buffer cmds;
    struct nk_draw_null_texture tex_null;
    GLuint font_tex;
};

struct nk_sdl {
    SDL_Window *win;
    struct nk_sdl_device ogl;
    struct nk_context ctx;
    struct nk_font_atlas atlas;
};

static struct nk_sdl _nk_sdl;

static void _nk_sdl_device_upload_atlas(const void *image, int width, int height) {
    struct nk_sdl_device *dev = &_nk_sdl.ogl;
    glGenTextures(1, &dev->font_tex);
    glBindTexture(GL_TEXTURE_2D, dev->font_tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, image);
}

static void _nk_sdl_device_create(void) {
    struct nk_sdl_device *dev = &_nk_sdl.ogl;
    nk_buffer_init_default(&dev->cmds);
}

static void _nk_sdl_device_destroy(void) {
    struct nk_sdl_device *dev = &_nk_sdl.ogl;
    glDeleteTextures(1, &dev->font_tex);
    nk_buffer_free(&dev->cmds);
}

static void _nk_sdl_render(enum nk_anti_aliasing AA) {
    struct nk_sdl_device *dev = &_nk_sdl.ogl;
    int width, height;
    int display_width, display_height;
    struct nk_vec2 scale;
    SDL_GetWindowSize(_nk_sdl.win, &width, &height);
    SDL_GL_GetDrawableSize(_nk_sdl.win, &display_width, &display_height);
    scale.x = (float)display_width / (float)width;
    scale.y = (float)display_height / (float)height;

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_TRANSFORM_BIT);
    glDisable(GL_CULL_FACE);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_SCISSOR_TEST);
    glEnable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    glViewport(0, 0, display_width, display_height);
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0, width, height, 0.0, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();

    {
        const struct nk_draw_command *cmd;
        const nk_draw_index *offset = NULL;
        struct nk_buffer vbuf, ebuf;

        /* Convert shapes into vertex buffer */
        static const struct nk_draw_vertex_layout_element vertex_layout[] = {
            {NK_VERTEX_POSITION, NK_FORMAT_FLOAT, 0},
            {NK_VERTEX_TEXCOORD, NK_FORMAT_FLOAT, 8},
            {NK_VERTEX_COLOR, NK_FORMAT_R8G8B8A8, 16},
            {NK_VERTEX_LAYOUT_END}
        };

        struct nk_convert_config config;
        memset(&config, 0, sizeof(config));
        config.vertex_layout = vertex_layout;
        config.vertex_size = 20;
        config.vertex_alignment = 4;
        config.tex_null = dev->tex_null;
        config.circle_segment_count = 22;
        config.curve_segment_count = 22;
        config.arc_segment_count = 22;
        config.global_alpha = 1.0f;
        config.shape_AA = AA;
        config.line_AA = AA;

        nk_buffer_init_default(&vbuf);
        nk_buffer_init_default(&ebuf);
        nk_convert(&_nk_sdl.ctx, &dev->cmds, &vbuf, &ebuf, &config);

        const float *vertices = nk_buffer_memory_const(&vbuf);
        glEnableClientState(GL_VERTEX_ARRAY);
        glEnableClientState(GL_TEXTURE_COORD_ARRAY);
        glEnableClientState(GL_COLOR_ARRAY);

        /* stride = 20 bytes: 2 floats pos + 2 floats uv + 4 bytes color */
        glVertexPointer(2, GL_FLOAT, 20, (const void *)((const char *)vertices));
        glTexCoordPointer(2, GL_FLOAT, 20, (const void *)((const char *)vertices + 8));
        glColorPointer(4, GL_UNSIGNED_BYTE, 20, (const void *)((const char *)vertices + 16));

        offset = (const nk_draw_index *)nk_buffer_memory_const(&ebuf);
        nk_draw_foreach(cmd, &_nk_sdl.ctx, &dev->cmds) {
            if (!cmd->elem_count) continue;
            glBindTexture(GL_TEXTURE_2D, (GLuint)cmd->texture.id);
            glScissor(
                (GLint)(cmd->clip_rect.x * scale.x),
                (GLint)((height - (GLint)(cmd->clip_rect.y + cmd->clip_rect.h)) * scale.y),
                (GLint)(cmd->clip_rect.w * scale.x),
                (GLint)(cmd->clip_rect.h * scale.y));
            glDrawElements(GL_TRIANGLES, (GLsizei)cmd->elem_count,
                           GL_UNSIGNED_SHORT, offset);
            offset += cmd->elem_count;
        }

        nk_buffer_free(&vbuf);
        nk_buffer_free(&ebuf);
    }

    glDisableClientState(GL_VERTEX_ARRAY);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);
    glDisableClientState(GL_COLOR_ARRAY);

    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glPopAttrib();

    nk_clear(&_nk_sdl.ctx);
    nk_buffer_clear(&dev->cmds);
}

static void _nk_sdl_font_stash_begin(struct nk_font_atlas **atlas) {
    nk_font_atlas_init_default(&_nk_sdl.atlas);
    nk_font_atlas_begin(&_nk_sdl.atlas);
    *atlas = &_nk_sdl.atlas;
}

static void _nk_sdl_font_stash_end(void) {
    const void *image;
    int w, h;
    image = nk_font_atlas_bake(&_nk_sdl.atlas, &w, &h, NK_FONT_ATLAS_RGBA32);
    _nk_sdl_device_upload_atlas(image, w, h);
    nk_font_atlas_end(&_nk_sdl.atlas,
        nk_handle_id((int)_nk_sdl.ogl.font_tex), &_nk_sdl.ogl.tex_null);
    if (_nk_sdl.atlas.default_font)
        nk_style_set_font(&_nk_sdl.ctx, &_nk_sdl.atlas.default_font->handle);
}

static int _nk_sdl_handle_event(SDL_Event *evt) {
    struct nk_context *ctx = &_nk_sdl.ctx;
    if (evt->type == SDL_KEYUP || evt->type == SDL_KEYDOWN) {
        int down = evt->type == SDL_KEYDOWN;
        SDL_Keycode sym = evt->key.keysym.sym;
        if (sym == SDLK_RSHIFT || sym == SDLK_LSHIFT) nk_input_key(ctx, NK_KEY_SHIFT, down);
        else if (sym == SDLK_DELETE) nk_input_key(ctx, NK_KEY_DEL, down);
        else if (sym == SDLK_RETURN) nk_input_key(ctx, NK_KEY_ENTER, down);
        else if (sym == SDLK_TAB) nk_input_key(ctx, NK_KEY_TAB, down);
        else if (sym == SDLK_BACKSPACE) nk_input_key(ctx, NK_KEY_BACKSPACE, down);
        else if (sym == SDLK_LEFT) nk_input_key(ctx, NK_KEY_LEFT, down);
        else if (sym == SDLK_RIGHT) nk_input_key(ctx, NK_KEY_RIGHT, down);
        else if (sym == SDLK_UP) nk_input_key(ctx, NK_KEY_UP, down);
        else if (sym == SDLK_DOWN) nk_input_key(ctx, NK_KEY_DOWN, down);
        else if (sym == SDLK_HOME) nk_input_key(ctx, NK_KEY_TEXT_START, down);
        else if (sym == SDLK_END) nk_input_key(ctx, NK_KEY_TEXT_END, down);
        else if (sym == SDLK_c && (evt->key.keysym.mod & KMOD_CTRL)) nk_input_key(ctx, NK_KEY_COPY, down);
        else if (sym == SDLK_v && (evt->key.keysym.mod & KMOD_CTRL)) nk_input_key(ctx, NK_KEY_PASTE, down);
        else if (sym == SDLK_x && (evt->key.keysym.mod & KMOD_CTRL)) nk_input_key(ctx, NK_KEY_CUT, down);
        else if (sym == SDLK_a && (evt->key.keysym.mod & KMOD_CTRL)) nk_input_key(ctx, NK_KEY_TEXT_SELECT_ALL, down);
        return 1;
    } else if (evt->type == SDL_MOUSEBUTTONDOWN || evt->type == SDL_MOUSEBUTTONUP) {
        int down = evt->type == SDL_MOUSEBUTTONDOWN;
        int x = evt->button.x, y = evt->button.y;
        if (evt->button.button == SDL_BUTTON_LEFT) nk_input_button(ctx, NK_BUTTON_LEFT, x, y, down);
        else if (evt->button.button == SDL_BUTTON_MIDDLE) nk_input_button(ctx, NK_BUTTON_MIDDLE, x, y, down);
        else if (evt->button.button == SDL_BUTTON_RIGHT) nk_input_button(ctx, NK_BUTTON_RIGHT, x, y, down);
        return 1;
    } else if (evt->type == SDL_MOUSEMOTION) {
        nk_input_motion(ctx, evt->motion.x, evt->motion.y);
        return 1;
    } else if (evt->type == SDL_MOUSEWHEEL) {
        nk_input_scroll(ctx, nk_vec2((float)evt->wheel.x, (float)evt->wheel.y));
        return 1;
    } else if (evt->type == SDL_TEXTINPUT) {
        nk_glyph glyph;
        memcpy(glyph, evt->text.text, NK_UTF_SIZE);
        nk_input_glyph(ctx, glyph);
        return 1;
    }
    return 0;
}

/* ── Module state ───────────────────────────────────────────── */
static SDL_Window *_sdl_window = NULL;
static SDL_GLContext _gl_context = NULL;
static Prove_EventNodeQueue *_event_queue = NULL;
static volatile bool _gui_running = false;
static int _win_width = 800;
static int _win_height = 600;
static char _win_title[256] = "Prove";

/* Temporary buffers for text_input widget */
#define PROVE_GUI_MAX_TEXT_INPUTS 32
#define PROVE_GUI_TEXT_BUF_SIZE 1024
static char _text_bufs[PROVE_GUI_MAX_TEXT_INPUTS][PROVE_GUI_TEXT_BUF_SIZE];
static int _text_lens[PROVE_GUI_MAX_TEXT_INPUTS];
static int _text_input_count = 0;

/* ── SDL key code to Prove Key lookup code ──────────────────── */
static int64_t _sdl_key_to_prove(SDL_Keycode sym) {
    switch (sym) {
        case SDLK_ESCAPE:    return 27;    /* Escape */
        case SDLK_RETURN:    return 13;    /* Enter */
        case SDLK_TAB:       return 9;     /* Tab */
        case SDLK_BACKSPACE: return 8;     /* Backspace */
        case SDLK_SPACE:     return 32;    /* Space */
        case SDLK_UP:        return 1001;  /* ArrowUp */
        case SDLK_DOWN:      return 1002;  /* ArrowDown */
        case SDLK_LEFT:      return 1003;  /* ArrowLeft */
        case SDLK_RIGHT:     return 1004;  /* ArrowRight */
        case SDLK_HOME:      return 1010;  /* Home */
        case SDLK_END:       return 1011;  /* End */
        case SDLK_PAGEUP:    return 1012;  /* PageUp */
        case SDLK_PAGEDOWN:  return 1013;  /* PageDown */
        case SDLK_DELETE:    return 1014;  /* Delete */
        case SDLK_INSERT:    return 1015;  /* Insert */
        case SDLK_F1:        return 1101;
        case SDLK_F2:        return 1102;
        case SDLK_F3:        return 1103;
        case SDLK_F4:        return 1104;
        case SDLK_F5:        return 1105;
        case SDLK_F6:        return 1106;
        case SDLK_F7:        return 1107;
        case SDLK_F8:        return 1108;
        case SDLK_F9:        return 1109;
        case SDLK_F10:       return 1110;
        case SDLK_F11:       return 1111;
        case SDLK_F12:       return 1112;
        default:
            if (sym >= 32 && sym < 127) return (int64_t)sym;
            return -1;
    }
}

/* ── atexit safety ──────────────────────────────────────────── */
static void _gui_atexit(void) {
    if (_gui_running) {
        prove_gui_cleanup();
    }
}

/* ── Lifecycle ──────────────────────────────────────────────── */

void prove_gui_init(Prove_EventNodeQueue *eq) {
    _event_queue = eq;
    _gui_running = true;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER | SDL_INIT_EVENTS) < 0) {
        fprintf(stderr, "prove: SDL_Init failed: %s\n", SDL_GetError());
        exit(1);
    }

    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    SDL_GL_SetAttribute(SDL_GL_STENCIL_SIZE, 8);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);

    _sdl_window = SDL_CreateWindow(
        _win_title,
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        _win_width, _win_height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE);
    if (!_sdl_window) {
        fprintf(stderr, "prove: SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        exit(1);
    }

    _gl_context = SDL_GL_CreateContext(_sdl_window);
    if (!_gl_context) {
        fprintf(stderr, "prove: SDL_GL_CreateContext failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(_sdl_window);
        SDL_Quit();
        exit(1);
    }

    /* Enable vsync for frame pacing */
    SDL_GL_SetSwapInterval(1);

    /* Initialize Nuklear */
    _nk_sdl_device_create();
    nk_init_default(&_nk_sdl.ctx, 0);
    _nk_sdl.ctx.clip.copy = NULL;
    _nk_sdl.ctx.clip.paste = NULL;
    _nk_sdl.ctx.clip.userdata = nk_handle_ptr(0);
    _nk_sdl.win = _sdl_window;

    /* Load default font */
    struct nk_font_atlas *atlas;
    _nk_sdl_font_stash_begin(&atlas);
    _nk_sdl_font_stash_end();

    atexit(_gui_atexit);
}

void prove_gui_cleanup(void) {
    if (!_gui_running) return;
    _gui_running = false;

    nk_font_atlas_clear(&_nk_sdl.atlas);
    nk_free(&_nk_sdl.ctx);
    _nk_sdl_device_destroy();

    if (_gl_context) {
        SDL_GL_DeleteContext(_gl_context);
        _gl_context = NULL;
    }
    if (_sdl_window) {
        SDL_DestroyWindow(_sdl_window);
        _sdl_window = NULL;
    }
    SDL_Quit();
    _event_queue = NULL;
}

void prove_gui_frame_begin(void) {
    SDL_Event evt;
    nk_input_begin(&_nk_sdl.ctx);

    _text_input_count = 0;

    while (SDL_PollEvent(&evt)) {
        /* Feed to Nuklear first */
        _nk_sdl_handle_event(&evt);

        /* Then translate to Prove events for the event queue */
        if (_event_queue) {
            switch (evt.type) {
                case SDL_QUIT: {
                    /* Exit tag = 9 */
                    prove_event_queue_send(_event_queue, 9, NULL);
                    break;
                }
                case SDL_KEYDOWN: {
                    int64_t key = _sdl_key_to_prove(evt.key.keysym.sym);
                    if (key >= 0) {
                        int64_t *payload = malloc(sizeof(int64_t));
                        if (payload) {
                            *payload = key;
                            /* KeyDown tag = 2 */
                            prove_event_queue_send(_event_queue, 2, payload);
                        }
                    }
                    break;
                }
                case SDL_KEYUP: {
                    int64_t key = _sdl_key_to_prove(evt.key.keysym.sym);
                    if (key >= 0) {
                        int64_t *payload = malloc(sizeof(int64_t));
                        if (payload) {
                            *payload = key;
                            /* KeyUp tag = 3 */
                            prove_event_queue_send(_event_queue, 3, payload);
                        }
                    }
                    break;
                }
                case SDL_MOUSEBUTTONDOWN: {
                    int64_t *payload = malloc(3 * sizeof(int64_t));
                    if (payload) {
                        payload[0] = evt.button.button;
                        payload[1] = evt.button.x;
                        payload[2] = evt.button.y;
                        /* MouseDown tag = 4 */
                        prove_event_queue_send(_event_queue, 4, payload);
                    }
                    break;
                }
                case SDL_MOUSEBUTTONUP: {
                    int64_t *payload = malloc(3 * sizeof(int64_t));
                    if (payload) {
                        payload[0] = evt.button.button;
                        payload[1] = evt.button.x;
                        payload[2] = evt.button.y;
                        /* MouseUp tag = 5 */
                        prove_event_queue_send(_event_queue, 5, payload);
                    }
                    break;
                }
                case SDL_MOUSEWHEEL: {
                    int64_t *payload = malloc(2 * sizeof(int64_t));
                    if (payload) {
                        payload[0] = evt.wheel.x;
                        payload[1] = evt.wheel.y;
                        /* Scroll tag = 6 */
                        prove_event_queue_send(_event_queue, 6, payload);
                    }
                    break;
                }
                case SDL_MOUSEMOTION: {
                    int64_t *payload = malloc(2 * sizeof(int64_t));
                    if (payload) {
                        payload[0] = evt.motion.x;
                        payload[1] = evt.motion.y;
                        /* MousePos tag = 7 */
                        prove_event_queue_send(_event_queue, 7, payload);
                    }
                    break;
                }
                case SDL_WINDOWEVENT: {
                    switch (evt.window.event) {
                        case SDL_WINDOWEVENT_RESIZED: {
                            int64_t *payload = malloc(2 * sizeof(int64_t));
                            if (payload) {
                                payload[0] = evt.window.data1;
                                payload[1] = evt.window.data2;
                                /* Resize tag = 8 */
                                prove_event_queue_send(_event_queue, 8, payload);
                            }
                            break;
                        }
                        case SDL_WINDOWEVENT_SHOWN:
                        case SDL_WINDOWEVENT_RESTORED: {
                            /* Visible — GraphicAppEvent tag = 10 */
                            prove_event_queue_send(_event_queue, 10, NULL);
                            break;
                        }
                        case SDL_WINDOWEVENT_HIDDEN:
                        case SDL_WINDOWEVENT_MINIMIZED: {
                            /* Hidden — GraphicAppEvent tag = 11 */
                            prove_event_queue_send(_event_queue, 11, NULL);
                            break;
                        }
                        case SDL_WINDOWEVENT_FOCUS_GAINED: {
                            /* Focused — GraphicAppEvent tag = 12 */
                            prove_event_queue_send(_event_queue, 12, NULL);
                            break;
                        }
                    }
                    break;
                }
            }
        }
    }
    nk_input_end(&_nk_sdl.ctx);
}

void prove_gui_frame_end(void) {
    int width, height;
    SDL_GetWindowSize(_sdl_window, &width, &height);

    glViewport(0, 0, width, height);
    glClear(GL_COLOR_BUFFER_BIT);
    glClearColor(0.10f, 0.10f, 0.10f, 1.0f);

    _nk_sdl_render(NK_ANTI_ALIASING_ON);
    SDL_GL_SwapWindow(_sdl_window);
}

/* ── Widget implementations ─────────────────────────────────── */

void prove_gui_window(Prove_String *title, int64_t width, int64_t height) {
    /* Update stored dimensions for initial window creation */
    if (width > 0) _win_width = (int)width;
    if (height > 0) _win_height = (int)height;

    /* Copy title to static buffer */
    if (title && title->length > 0) {
        size_t len = title->length < 255 ? title->length : 255;
        memcpy(_win_title, title->data, len);
        _win_title[len] = '\0';
    }

    /* Update SDL window if it exists */
    if (_sdl_window) {
        SDL_SetWindowTitle(_sdl_window, _win_title);
    }

    /* Begin Nuklear window filling the entire SDL window */
    int actual_w, actual_h;
    if (_sdl_window) {
        SDL_GetWindowSize(_sdl_window, &actual_w, &actual_h);
    } else {
        actual_w = _win_width;
        actual_h = _win_height;
    }

    nk_begin(&_nk_sdl.ctx, _win_title,
             nk_rect(0, 0, (float)actual_w, (float)actual_h),
             NK_WINDOW_NO_SCROLLBAR);
    nk_layout_row_dynamic(&_nk_sdl.ctx, 30, 1);
}

bool prove_gui_button(Prove_String *label) {
    char buf[256];
    size_t len = 0;
    if (label && label->length > 0) {
        len = label->length < 255 ? label->length : 255;
        memcpy(buf, label->data, len);
    }
    buf[len] = '\0';
    return nk_button_label(&_nk_sdl.ctx, buf) != 0;
}

void prove_gui_label(Prove_String *text) {
    char buf[1024];
    size_t len = 0;
    if (text && text->length > 0) {
        len = text->length < 1023 ? text->length : 1023;
        memcpy(buf, text->data, len);
    }
    buf[len] = '\0';
    nk_label(&_nk_sdl.ctx, buf, NK_TEXT_LEFT);
}

Prove_String *prove_gui_text_input(Prove_String *label, Prove_String *value) {
    char lbuf[256];
    size_t llen = 0;
    if (label && label->length > 0) {
        llen = label->length < 255 ? label->length : 255;
        memcpy(lbuf, label->data, llen);
    }
    lbuf[llen] = '\0';

    int idx = _text_input_count;
    if (idx >= PROVE_GUI_MAX_TEXT_INPUTS) idx = PROVE_GUI_MAX_TEXT_INPUTS - 1;
    else _text_input_count++;

    /* Initialize buffer from current value */
    if (value && value->length > 0) {
        size_t vlen = value->length < (PROVE_GUI_TEXT_BUF_SIZE - 1)
                          ? value->length : (PROVE_GUI_TEXT_BUF_SIZE - 1);
        memcpy(_text_bufs[idx], value->data, vlen);
        _text_bufs[idx][vlen] = '\0';
        _text_lens[idx] = (int)vlen;
    } else {
        _text_bufs[idx][0] = '\0';
        _text_lens[idx] = 0;
    }

    /* Label row + edit row */
    nk_label(&_nk_sdl.ctx, lbuf, NK_TEXT_LEFT);
    nk_edit_string_zero_terminated(&_nk_sdl.ctx, NK_EDIT_FIELD,
                                   _text_bufs[idx], PROVE_GUI_TEXT_BUF_SIZE,
                                   nk_filter_default);
    _text_lens[idx] = (int)strlen(_text_bufs[idx]);

    return prove_string_new(_text_bufs[idx], _text_lens[idx]);
}

bool prove_gui_checkbox(Prove_String *label, bool checked) {
    char buf[256];
    size_t len = 0;
    if (label && label->length > 0) {
        len = label->length < 255 ? label->length : 255;
        memcpy(buf, label->data, len);
    }
    buf[len] = '\0';

    nk_bool val = checked ? nk_true : nk_false;
    nk_checkbox_label(&_nk_sdl.ctx, buf, &val);
    return val != nk_false;
}

double prove_gui_slider(Prove_String *label, double min, double max, double value) {
    char buf[256];
    size_t len = 0;
    if (label && label->length > 0) {
        len = label->length < 255 ? label->length : 255;
        memcpy(buf, label->data, len);
    }
    buf[len] = '\0';

    nk_label(&_nk_sdl.ctx, buf, NK_TEXT_LEFT);
    float fval = (float)value;
    float fstep = (float)(max - min) / 100.0f;
    nk_slider_float(&_nk_sdl.ctx, (float)min, &fval, (float)max, fstep);
    return (double)fval;
}

void prove_gui_progress(int64_t current, int64_t max) {
    nk_size val = (nk_size)(current > 0 ? current : 0);
    nk_size mx = (nk_size)(max > 0 ? max : 1);
    nk_progress(&_nk_sdl.ctx, &val, mx, nk_false);
}

void prove_gui_quit(void) {
    if (_event_queue) {
        /* Exit tag = 9 */
        prove_event_queue_send(_event_queue, 9, NULL);
    }
    _gui_running = false;
}
