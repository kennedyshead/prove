#ifndef PROVE_INPUT_OUTPUT_H
#define PROVE_INPUT_OUTPUT_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_result.h"

/* ── ProcessResult record ────────────────────────────────────── */

typedef struct {
    int64_t       exit_code;
    Prove_String *standard_output;
    Prove_String *standard_error;
} Prove_ProcessResult;

/* ── DirEntry tagged type (0=File, 1=Directory) ─────────────── */

typedef struct {
    uint8_t       tag;  /* 0 = File, 1 = Directory */
    Prove_String *name;
    Prove_String *path;
} Prove_DirEntry;

/* ── ExitCode (alias for Integer) ────────────────────────────── */

typedef int64_t Prove_ExitCode;

/* ── File I/O ────────────────────────────────────────────────── */

Prove_Result prove_file_read(Prove_String *path);
Prove_Result prove_file_write(Prove_String *path, Prove_String *content);

/* ── Console validates ───────────────────────────────────────── */

bool prove_io_console_validates(void);

/* ── File validates ──────────────────────────────────────────── */

bool prove_io_file_validates(Prove_String *path);

/* ── System channel ──────────────────────────────────────────── */

Prove_ProcessResult prove_io_system_inputs(Prove_String *cmd, Prove_List *args);
void                prove_io_system_outputs(int64_t code);
bool                prove_io_system_validates(Prove_String *cmd);

/* ── Dir channel ─────────────────────────────────────────────── */

Prove_List *prove_io_dir_inputs(Prove_String *path);
Prove_Result prove_io_dir_outputs(Prove_String *path);
bool         prove_io_dir_validates(Prove_String *path);

/* ── Process channel (argv) ──────────────────────────────────── */

void         prove_io_init_args(int argc, char **argv);
Prove_List  *prove_io_process_inputs(void);
bool         prove_io_process_validates(Prove_String *value);

#endif /* PROVE_INPUT_OUTPUT_H */
