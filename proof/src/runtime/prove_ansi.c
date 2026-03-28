#include "prove_ansi.h"
#include <string.h>

static const struct { const char *name; const char *esc; } _ansi_map[] = {
    /* Colors */
    {"default", "\033[0m"},
    {"black",   "\033[30m"},
    {"red",     "\033[31m"},
    {"green",   "\033[32m"},
    {"yellow",  "\033[33m"},
    {"blue",    "\033[34m"},
    {"magenta", "\033[35m"},
    {"cyan",    "\033[36m"},
    {"white",   "\033[37m"},
    /* Text styles */
    {"reset",         "\033[0m"},
    {"bold",          "\033[1m"},
    {"dim",           "\033[2m"},
    {"italic",        "\033[3m"},
    {"underline",     "\033[4m"},
    {"inverse",       "\033[7m"},
    {"strikethrough", "\033[9m"},
};

Prove_String *prove_ansi_escape(Prove_String *name) {
    if (!name) return prove_string_from_cstr("");
    for (size_t i = 0; i < sizeof(_ansi_map) / sizeof(_ansi_map[0]); i++) {
        if ((size_t)name->length == strlen(_ansi_map[i].name) &&
            memcmp(name->data, _ansi_map[i].name, name->length) == 0) {
            return prove_string_from_cstr(_ansi_map[i].esc);
        }
    }
    return prove_string_from_cstr("");
}
