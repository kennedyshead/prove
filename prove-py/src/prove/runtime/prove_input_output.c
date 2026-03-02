/* Prove InputOutput runtime — file, system, dir, process channels. */

#include "prove_input_output.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <dirent.h>

/* ── File I/O ────────────────────────────────────────────────── */

Prove_Result prove_file_read(Prove_String *path) {
    /* Build null-terminated path */
    char *cpath = (char *)malloc((size_t)path->length + 1);
    if (!cpath) return prove_result_err(prove_string_from_cstr("out of memory"));
    memcpy(cpath, path->data, (size_t)path->length);
    cpath[path->length] = '\0';

    FILE *f = fopen(cpath, "rb");
    if (!f) {
        Prove_String *msg = prove_string_from_cstr(strerror(errno));
        free(cpath);
        return prove_result_err(msg);
    }
    free(cpath);

    /* Read entire file */
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size < 0) {
        fclose(f);
        return prove_result_err(prove_string_from_cstr("failed to determine file size"));
    }

    char *buf = (char *)malloc((size_t)size);
    if (!buf) {
        fclose(f);
        return prove_result_err(prove_string_from_cstr("out of memory"));
    }

    size_t read_bytes = fread(buf, 1, (size_t)size, f);
    fclose(f);

    Prove_String *content = prove_string_new(buf, (int64_t)read_bytes);
    free(buf);
    return prove_result_ok_ptr(content);
}

Prove_Result prove_file_write(Prove_String *path, Prove_String *content) {
    char *cpath = (char *)malloc((size_t)path->length + 1);
    if (!cpath) return prove_result_err(prove_string_from_cstr("out of memory"));
    memcpy(cpath, path->data, (size_t)path->length);
    cpath[path->length] = '\0';

    FILE *f = fopen(cpath, "wb");
    if (!f) {
        Prove_String *msg = prove_string_from_cstr(strerror(errno));
        free(cpath);
        return prove_result_err(msg);
    }
    free(cpath);

    size_t written = fwrite(content->data, 1, (size_t)content->length, f);
    fclose(f);

    if ((int64_t)written != content->length) {
        return prove_result_err(prove_string_from_cstr("incomplete write"));
    }
    return prove_result_ok();
}

/* ── Console validates ───────────────────────────────────────── */

bool prove_io_console_validates(void) {
    return !feof(stdin);
}

/* ── File validates ──────────────────────────────────────────── */

bool prove_io_file_validates(Prove_String *path) {
    char *cpath = (char *)malloc((size_t)path->length + 1);
    if (!cpath) return false;
    memcpy(cpath, path->data, (size_t)path->length);
    cpath[path->length] = '\0';

    int ok = access(cpath, F_OK) == 0;
    free(cpath);
    return ok;
}

/* ── Helper: extract C string from Prove_String ──────────────── */

static char *_to_cstr(Prove_String *s) {
    char *buf = (char *)malloc((size_t)s->length + 1);
    if (!buf) return NULL;
    memcpy(buf, s->data, (size_t)s->length);
    buf[s->length] = '\0';
    return buf;
}

/* ── System channel ──────────────────────────────────────────── */

Prove_ProcessResult prove_io_system_inputs(Prove_String *cmd, Prove_List *args) {
    Prove_ProcessResult result;
    result.exit_code = -1;
    result.standard_output = prove_string_from_cstr("");
    result.standard_error = prove_string_from_cstr("");

    char *ccmd = _to_cstr(cmd);
    if (!ccmd) return result;

    /* Build argv array: [cmd, args..., NULL] */
    int64_t nargs = args ? prove_list_len(args) : 0;
    char **argv = (char **)calloc((size_t)(nargs + 2), sizeof(char *));
    if (!argv) { free(ccmd); return result; }

    argv[0] = ccmd;
    for (int64_t i = 0; i < nargs; i++) {
        Prove_String *arg = *(Prove_String **)prove_list_get(args, i);
        argv[i + 1] = _to_cstr(arg);
    }
    argv[nargs + 1] = NULL;

    /* Create pipes for stdout and stderr */
    int out_pipe[2], err_pipe[2];
    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0) {
        for (int64_t i = 0; i <= nargs; i++) free(argv[i]);
        free(argv);
        return result;
    }

    pid_t pid = fork();
    if (pid < 0) {
        /* Fork failed */
        close(out_pipe[0]); close(out_pipe[1]);
        close(err_pipe[0]); close(err_pipe[1]);
        for (int64_t i = 0; i <= nargs; i++) free(argv[i]);
        free(argv);
        return result;
    }

    if (pid == 0) {
        /* Child process */
        close(out_pipe[0]);
        close(err_pipe[0]);
        dup2(out_pipe[1], STDOUT_FILENO);
        dup2(err_pipe[1], STDERR_FILENO);
        close(out_pipe[1]);
        close(err_pipe[1]);
        execvp(ccmd, argv);
        _exit(127);  /* exec failed */
    }

    /* Parent process */
    close(out_pipe[1]);
    close(err_pipe[1]);

    /* Read stdout */
    char buf[4096];
    ssize_t n;
    Prove_String *out_str = prove_string_from_cstr("");
    while ((n = read(out_pipe[0], buf, sizeof(buf))) > 0) {
        Prove_String *chunk = prove_string_new(buf, (int64_t)n);
        Prove_String *tmp = prove_string_concat(out_str, chunk);
        out_str = tmp;
    }
    close(out_pipe[0]);

    /* Read stderr */
    Prove_String *err_str = prove_string_from_cstr("");
    while ((n = read(err_pipe[0], buf, sizeof(buf))) > 0) {
        Prove_String *chunk = prove_string_new(buf, (int64_t)n);
        Prove_String *tmp = prove_string_concat(err_str, chunk);
        err_str = tmp;
    }
    close(err_pipe[0]);

    /* Wait for child */
    int status;
    waitpid(pid, &status, 0);

    result.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    result.standard_output = out_str;
    result.standard_error = err_str;

    for (int64_t i = 0; i <= nargs; i++) free(argv[i]);
    free(argv);
    return result;
}

void prove_io_system_outputs(int64_t code) {
    exit((int)code);
}

bool prove_io_system_validates(Prove_String *cmd) {
    char *ccmd = _to_cstr(cmd);
    if (!ccmd) return false;

    /* Check if command contains a path separator */
    if (strchr(ccmd, '/')) {
        int ok = access(ccmd, X_OK) == 0;
        free(ccmd);
        return ok;
    }

    /* Search PATH */
    const char *path_env = getenv("PATH");
    if (!path_env) { free(ccmd); return false; }

    char *path_copy = strdup(path_env);
    if (!path_copy) { free(ccmd); return false; }

    char *dir = strtok(path_copy, ":");
    while (dir) {
        char full[4096];
        snprintf(full, sizeof(full), "%s/%s", dir, ccmd);
        if (access(full, X_OK) == 0) {
            free(path_copy);
            free(ccmd);
            return true;
        }
        dir = strtok(NULL, ":");
    }
    free(path_copy);
    free(ccmd);
    return false;
}

/* ── Dir channel ─────────────────────────────────────────────── */

Prove_List *prove_io_dir_inputs(Prove_String *path) {
    char *cpath = _to_cstr(path);
    if (!cpath) return prove_list_new(sizeof(Prove_DirEntry), 4);

    DIR *d = opendir(cpath);
    if (!d) {
        free(cpath);
        return prove_list_new(sizeof(Prove_DirEntry), 4);
    }

    Prove_List *list = prove_list_new(sizeof(Prove_DirEntry), 16);
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        /* Skip . and .. */
        if (ent->d_name[0] == '.' &&
            (ent->d_name[1] == '\0' ||
             (ent->d_name[1] == '.' && ent->d_name[2] == '\0')))
            continue;

        Prove_DirEntry entry;
        entry.name = prove_string_from_cstr(ent->d_name);

        /* Build full path */
        size_t plen = strlen(cpath);
        size_t nlen = strlen(ent->d_name);
        char *full = (char *)malloc(plen + 1 + nlen + 1);
        if (full) {
            memcpy(full, cpath, plen);
            full[plen] = '/';
            memcpy(full + plen + 1, ent->d_name, nlen + 1);
            entry.path = prove_string_from_cstr(full);
            free(full);
        } else {
            entry.path = prove_string_from_cstr(ent->d_name);
        }

        /* Determine type */
        struct stat st;
        char *entry_path = _to_cstr(entry.path);
        if (entry_path && stat(entry_path, &st) == 0 && S_ISDIR(st.st_mode)) {
            entry.tag = 1;  /* Directory */
        } else {
            entry.tag = 0;  /* File */
        }
        free(entry_path);

        prove_list_push(&list, &entry);
    }
    closedir(d);
    free(cpath);
    return list;
}

Prove_Result prove_io_dir_outputs(Prove_String *path) {
    char *cpath = _to_cstr(path);
    if (!cpath) return prove_result_err(prove_string_from_cstr("out of memory"));

    if (mkdir(cpath, 0755) != 0 && errno != EEXIST) {
        Prove_String *msg = prove_string_from_cstr(strerror(errno));
        free(cpath);
        return prove_result_err(msg);
    }
    free(cpath);
    return prove_result_ok();
}

bool prove_io_dir_validates(Prove_String *path) {
    char *cpath = _to_cstr(path);
    if (!cpath) return false;

    struct stat st;
    bool ok = (stat(cpath, &st) == 0 && S_ISDIR(st.st_mode));
    free(cpath);
    return ok;
}

/* ── Process channel (argv) ──────────────────────────────────── */

static int    _prove_argc = 0;
static char **_prove_argv = NULL;

void prove_io_init_args(int argc, char **argv) {
    _prove_argc = argc;
    _prove_argv = argv;
}

Prove_List *prove_io_process_inputs(void) {
    Prove_List *list = prove_list_new(sizeof(Prove_String *), _prove_argc > 0 ? _prove_argc : 4);
    for (int i = 0; i < _prove_argc; i++) {
        Prove_String *s = prove_string_from_cstr(_prove_argv[i]);
        prove_list_push(&list, &s);
    }
    return list;
}

bool prove_io_process_validates(Prove_String *value) {
    char *cval = _to_cstr(value);
    if (!cval) return false;

    for (int i = 0; i < _prove_argc; i++) {
        if (strcmp(_prove_argv[i], cval) == 0) {
            free(cval);
            return true;
        }
    }
    free(cval);
    return false;
}
