#include "prove_terminal.h"
#include "prove_ansi.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>

#ifdef _WIN32
/* Minimal Windows support — not full featured */
#include <windows.h>
#include <conio.h>

static bool _raw_mode = false;
static DWORD _orig_mode = 0;

bool prove_terminal_validates(void) {
    return GetConsoleWindow() != NULL;
}

void prove_terminal_raw(void) {
    HANDLE h = GetStdHandle(STD_INPUT_HANDLE);
    GetConsoleMode(h, &_orig_mode);
    SetConsoleMode(h, _orig_mode & ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT));
    _raw_mode = true;
}

void prove_terminal_cooked(void) {
    if (_raw_mode) {
        HANDLE h = GetStdHandle(STD_INPUT_HANDLE);
        SetConsoleMode(h, _orig_mode);
        _raw_mode = false;
    }
}

Prove_Position prove_terminal_size(void) {
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    GetConsoleScreenBufferInfo(GetStdHandle(STD_OUTPUT_HANDLE), &csbi);
    Prove_Position pos;
    pos.x = csbi.srWindow.Right - csbi.srWindow.Left + 1;
    pos.y = csbi.srWindow.Bottom - csbi.srWindow.Top + 1;
    return pos;
}

int64_t prove_terminal_read_key(void) {
    int c = _getch();
    if (c == 0 || c == 0xE0) {
        c = _getch();
        switch (c) {
            case 72: return 1001; /* ArrowUp */
            case 80: return 1002; /* ArrowDown */
            case 75: return 1003; /* ArrowLeft */
            case 77: return 1004; /* ArrowRight */
            case 71: return 1010; /* Home */
            case 79: return 1011; /* End */
            case 73: return 1012; /* PageUp */
            case 81: return 1013; /* PageDown */
            case 83: return 1014; /* Delete */
            case 82: return 1015; /* Insert */
            case 59: return 1101; /* F1 */
            case 60: return 1102; /* F2 */
            case 61: return 1103; /* F3 */
            case 62: return 1104; /* F4 */
            case 63: return 1105; /* F5 */
            case 64: return 1106; /* F6 */
            case 65: return 1107; /* F7 */
            case 66: return 1108; /* F8 */
            case 67: return 1109; /* F9 */
            case 68: return 1110; /* F10 */
            default: return c;
        }
    }
    return (int64_t)c;
}

#else /* POSIX */

#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <pthread.h>

static bool _raw_mode = false;
static struct termios _orig_termios;
static Prove_EventNodeQueue *_event_queue = NULL;
static volatile sig_atomic_t _resize_pending = 0;
static pthread_t _input_thread;
static volatile bool _input_running = false;

/* ── atexit safety ───────────────────────────────────────────── */

static void _restore_cooked(void) {
    if (_raw_mode) {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &_orig_termios);
        _raw_mode = false;
    }
}

/* ── SIGWINCH handler ────────────────────────────────────────── */

static void _sigwinch_handler(int sig) {
    (void)sig;
    _resize_pending = 1;
}

/* Check for pending SIGWINCH and send resize event from the main loop
 * (async-signal-safe — no malloc or mutex in the signal handler). */
void prove_terminal_check_resize(Prove_EventNodeQueue *q) {
    if (!_resize_pending) return;
    _resize_pending = 0;
    if (!q) return;

    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0) {
        int64_t *payload = malloc(2 * sizeof(int64_t));
        if (payload) {
            payload[0] = ws.ws_col;
            payload[1] = ws.ws_row;
            /* Resize tag = 8 (matching AppEvent variant order:
               Draw=0, Tick=1, KeyDown=2, KeyUp=3,
               MouseDown=4, MouseUp=5, Scroll=6, MousePos=7,
               Resize=8, Exit=9) */
            prove_event_queue_send(q, 8, payload);
        }
    }
}

/* ── Terminal validation ─────────────────────────────────────── */

bool prove_terminal_validates(void) {
    return isatty(STDOUT_FILENO) != 0;
}

/* ── Raw/cooked mode ─────────────────────────────────────────── */

void prove_terminal_raw(void) {
    if (_raw_mode) return;
    if (tcgetattr(STDIN_FILENO, &_orig_termios) < 0) return;

    static bool atexit_registered = false;
    if (!atexit_registered) {
        atexit(_restore_cooked);
        atexit_registered = true;
    }

    struct termios raw = _orig_termios;
    raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    raw.c_oflag &= ~(OPOST);
    raw.c_cflag |= (CS8);
    raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;

    tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
    _raw_mode = true;

    /* Install SIGWINCH handler */
    struct sigaction sa;
    sa.sa_handler = _sigwinch_handler;
    sa.sa_flags = SA_RESTART;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGWINCH, &sa, NULL);
}

void prove_terminal_cooked(void) {
    if (_raw_mode) {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &_orig_termios);
        _raw_mode = false;
    }
}

/* ── Query ───────────────────────────────────────────────────── */

Prove_Position prove_terminal_size(void) {
    Prove_Position pos = {80, 24}; /* sensible default */
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0) {
        pos.x = ws.ws_col;
        pos.y = ws.ws_row;
    }
    return pos;
}

/* ── Key reading ─────────────────────────────────────────────── */

/* Read a raw byte from stdin, retrying on EINTR. Returns -1 on EOF. */
static int _read_byte(void) {
    unsigned char c;
    while (1) {
        ssize_t n = read(STDIN_FILENO, &c, 1);
        if (n == 1) return c;
        if (n == 0) return -1; /* EOF */
        if (errno == EINTR) continue; /* interrupted by signal, retry */
        return -1;
    }
}

/* Try to read one more byte with a short timeout (for escape sequences).
 * Returns -1 if no byte available within ~50ms. */
static int _read_byte_timeout(void) {
    fd_set fds;
    struct timeval tv;
    FD_ZERO(&fds);
    FD_SET(STDIN_FILENO, &fds);
    tv.tv_sec = 0;
    tv.tv_usec = 50000; /* 50ms */
    if (select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) > 0) {
        return _read_byte();
    }
    return -1;
}

int64_t prove_terminal_read_key(void) {
    int c = _read_byte();
    if (c < 0) return -1;

    /* ESC sequence */
    if (c == 27) {
        int next = _read_byte_timeout();
        if (next < 0) return 27; /* bare Escape */

        if (next == '[') {
            /* CSI sequence */
            int seq = _read_byte_timeout();
            if (seq < 0) return 27;

            /* Numeric sequences: ESC [ <number> ~ */
            if (seq >= '0' && seq <= '9') {
                int tilde = _read_byte_timeout();
                if (tilde == '~') {
                    switch (seq) {
                        case '1': return 1010; /* Home */
                        case '3': return 1014; /* Delete */
                        case '4': return 1011; /* End */
                        case '5': return 1012; /* PageUp */
                        case '6': return 1013; /* PageDown */
                        case '7': return 1010; /* Home (alt) */
                        case '8': return 1011; /* End (alt) */
                    }
                }
                /* Function keys: ESC [ 1 <digit> ~ */
                if (seq == '1' && tilde >= '0' && tilde <= '9') {
                    int final = _read_byte_timeout();
                    if (final == '~') {
                        switch (tilde) {
                            case '5': return 1105; /* F5 */
                            case '7': return 1106; /* F6 */
                            case '8': return 1107; /* F7 */
                            case '9': return 1108; /* F8 */
                        }
                    }
                }
                if (seq == '2' && tilde >= '0' && tilde <= '9') {
                    int final = _read_byte_timeout();
                    if (final == '~') {
                        switch (tilde) {
                            case '0': return 1109; /* F9 */
                            case '1': return 1110; /* F10 */
                            case '3': return 1111; /* F11 */
                            case '4': return 1112; /* F12 */
                        }
                    }
                }
                return seq; /* unknown numeric sequence */
            }

            /* Arrow keys and simple sequences */
            switch (seq) {
                case 'A': return 1001; /* ArrowUp */
                case 'B': return 1002; /* ArrowDown */
                case 'C': return 1004; /* ArrowRight */
                case 'D': return 1003; /* ArrowLeft */
                case 'H': return 1010; /* Home */
                case 'F': return 1011; /* End */
            }
            return seq;
        }

        /* ESC O sequences (SS3) */
        if (next == 'O') {
            int seq = _read_byte_timeout();
            if (seq < 0) return 27;
            switch (seq) {
                case 'P': return 1101; /* F1 */
                case 'Q': return 1102; /* F2 */
                case 'R': return 1103; /* F3 */
                case 'S': return 1104; /* F4 */
                case 'H': return 1010; /* Home */
                case 'F': return 1011; /* End */
            }
            return seq;
        }

        return 27; /* bare ESC + unknown */
    }

    /* Regular keys */
    return (int64_t)c;
}

/* ── Input thread ────────────────────────────────────────────── */

static void *_input_thread_fn(void *arg) {
    Prove_EventNodeQueue *eq = (Prove_EventNodeQueue *)arg;
    while (_input_running) {
        int64_t key = prove_terminal_read_key();
        if (key < 0) break;

        /* Allocate KeyDown event payload: single int64_t for key code */
        int64_t *payload = malloc(sizeof(int64_t));
        if (payload) {
            *payload = key;
            /* KeyDown tag = 2 (matching AppEvent variant order) */
            prove_event_queue_send(eq, 2, payload);
        }
    }
    return NULL;
}

#endif /* _WIN32 / POSIX */

/* ── Color / TextStyle ANSI (shared) ─────────────────────────── */

Prove_String *prove_terminal_color_ansi(Prove_String *name) {
    return prove_ansi_escape(name);
}

/* ── ANSI output (shared) ────────────────────────────────────── */

void prove_terminal_write(Prove_String *text) {
    if (text) {
        fwrite(text->data, 1, text->length, stdout);
        fflush(stdout);
    }
}

void prove_terminal_write_at(int64_t x, int64_t y, Prove_String *text) {
    /* ANSI: ESC[row;colH (1-based) */
    printf("\033[%lld;%lldH", (long long)(y + 1), (long long)(x + 1));
    if (text) {
        fwrite(text->data, 1, text->length, stdout);
    }
    fflush(stdout);
}

void prove_terminal_clear(void) {
    /* Clear screen and move cursor to top-left */
    fputs("\033[2J\033[H", stdout);
    fflush(stdout);
}

void prove_terminal_cursor(int64_t x, int64_t y) {
    printf("\033[%lld;%lldH", (long long)(y + 1), (long long)(x + 1));
    fflush(stdout);
}

/* ── Lifecycle ───────────────────────────────────────────────── */

void prove_terminal_init(Prove_EventNodeQueue *eq) {
#ifndef _WIN32
    _event_queue = eq;
    prove_terminal_raw();

    /* Start input thread */
    _input_running = true;
    pthread_create(&_input_thread, NULL, _input_thread_fn, eq);
#else
    (void)eq;
    prove_terminal_raw();
#endif
}

void prove_terminal_cleanup(void) {
#ifndef _WIN32
    _input_running = false;
    /* The input thread may be blocked on read — send a byte to unblock */
    pthread_cancel(_input_thread);
    pthread_join(_input_thread, NULL);
    _event_queue = NULL;
#endif
    prove_terminal_cooked();
}
