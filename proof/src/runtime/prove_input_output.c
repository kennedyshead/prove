/* Prove InputOutput runtime — file, system, dir, process channels. */

#include "prove_input_output.h"
#include "prove_text.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <dirent.h>
#include <poll.h>

/* ── File I/O ────────────────────────────────────────────────── */

Prove_Result prove_file_read(Prove_String *path) {
    /* Prove_String.data is already null-terminated */
    FILE *f = fopen(path->data, "rb");
    if (!f) {
        Prove_String *msg = prove_string_from_cstr(strerror(errno));
        return prove_result_err(msg);
    }

    /* Read entire file */
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size < 0) {
        fclose(f);
        return prove_result_err(prove_string_from_cstr("failed to determine file size"));
    }

    /* Allocate Prove_String directly and fread into it — no intermediate copy */
    Prove_String *content = (Prove_String *)prove_alloc(sizeof(Prove_String) + (size_t)size + 1);
    if (!content) {
        fclose(f);
        return prove_result_err(prove_string_from_cstr("out of memory"));
    }

    size_t read_bytes = fread(content->data, 1, (size_t)size, f);
    fclose(f);

    content->length = (int64_t)read_bytes;
    content->data[read_bytes] = '\0';
    return prove_result_ok_ptr(content);
}

Prove_Result prove_file_write(Prove_String *path, Prove_String *content) {
    FILE *f = fopen(path->data, "wb");
    if (!f) {
        Prove_String *msg = prove_string_from_cstr(strerror(errno));
        return prove_result_err(msg);
    }

    size_t written = fwrite(content->data, 1, (size_t)content->length, f);
    fclose(f);

    if ((int64_t)written != content->length) {
        return prove_result_err(prove_string_from_cstr("incomplete write"));
    }
    return prove_result_ok();
}

/* ── Console channel ─────────────────────────────────────────── */

bool prove_io_console_validates(void) {
    return !feof(stdin);
}

Prove_ByteArray *prove_readexactly(int64_t n) {
    int64_t len = n > 0 ? n : 0;
    Prove_ByteArray *ba = (Prove_ByteArray *)prove_alloc(sizeof(Prove_ByteArray) + (size_t)len);
    ba->length = len > 0 ? (int64_t)fread(ba->data, 1, (size_t)len, stdin) : 0;
    return ba;
}

/* ── File validates ──────────────────────────────────────────── */

bool prove_io_file_validates(Prove_String *path) {
    return access(path->data, F_OK) == 0;
}

/* ── System channel ──────────────────────────────────────────── */

Prove_ProcessResult prove_io_system_inputs(Prove_String *cmd, Prove_List *args) {
    Prove_ProcessResult result;
    result.exit_code = -1;
    result.standard_output = prove_string_from_cstr("");
    result.standard_error = prove_string_from_cstr("");

    /* Build argv array using s->data directly (already null-terminated) */
    int64_t nargs = args ? prove_list_len(args) : 0;
    char **argv = (char **)calloc((size_t)(nargs + 2), sizeof(char *));
    if (!argv) return result;

    argv[0] = cmd->data;
    for (int64_t i = 0; i < nargs; i++) {
        Prove_String *arg = (Prove_String *)prove_list_get(args, i);
        argv[i + 1] = arg->data;
    }
    argv[nargs + 1] = NULL;

    /* Create pipes for stdout and stderr */
    int out_pipe[2], err_pipe[2];
    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0) {
        free(argv);
        return result;
    }

    pid_t pid = fork();
    if (pid < 0) {
        /* Fork failed */
        close(out_pipe[0]); close(out_pipe[1]);
        close(err_pipe[0]); close(err_pipe[1]);
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
        execvp(cmd->data, argv);
        _exit(127);  /* exec failed */
    }

    /* Parent process */
    close(out_pipe[1]);
    close(err_pipe[1]);

    /* Read stdout and stderr concurrently using poll() to avoid deadlock
       when the child fills one pipe buffer while we block reading the other.
       Also use prove_string_new + prove_text_write to handle embedded NUL bytes. */
    char buf[4096];
    ssize_t n;
    Prove_Builder *ob = prove_text_builder();
    Prove_Builder *eb = prove_text_builder();

    struct pollfd fds[2];
    fds[0].fd = out_pipe[0];
    fds[0].events = POLLIN;
    fds[1].fd = err_pipe[0];
    fds[1].events = POLLIN;
    int open_fds = 2;

    while (open_fds > 0) {
        int ret = poll(fds, 2, -1);
        if (ret < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (fds[0].revents & (POLLIN | POLLHUP)) {
            n = read(out_pipe[0], buf, sizeof(buf));
            if (n > 0) {
                ob = prove_text_write_bytes(ob, buf, (int64_t)n);
            } else {
                fds[0].fd = -1;
                close(out_pipe[0]);
                open_fds--;
            }
        }
        if (fds[1].revents & (POLLIN | POLLHUP)) {
            n = read(err_pipe[0], buf, sizeof(buf));
            if (n > 0) {
                eb = prove_text_write_bytes(eb, buf, (int64_t)n);
            } else {
                fds[1].fd = -1;
                close(err_pipe[0]);
                open_fds--;
            }
        }
    }

    /* Wait for child */
    int status;
    waitpid(pid, &status, 0);

    result.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    result.standard_output = prove_text_build(ob);
    result.standard_error = prove_text_build(eb);

    free(ob);
    free(eb);
    free(argv);
    return result;
}

void prove_io_system_outputs(int64_t code) {
    exit((int)code);
}

bool prove_io_system_validates(Prove_String *cmd) {
    /* Check if command contains a path separator */
    if (strchr(cmd->data, '/')) {
        return access(cmd->data, X_OK) == 0;
    }

    /* Search PATH */
    const char *path_env = getenv("PATH");
    if (!path_env) return false;

    char *path_copy = strdup(path_env);
    if (!path_copy) return false;

    char *dir = strtok(path_copy, ":");
    while (dir) {
        char full[4096];
        snprintf(full, sizeof(full), "%s/%s", dir, cmd->data);
        if (access(full, X_OK) == 0) {
            free(path_copy);
            return true;
        }
        dir = strtok(NULL, ":");
    }
    free(path_copy);
    return false;
}

/* ── Dir channel ─────────────────────────────────────────────── */

Prove_List *prove_io_dir_inputs(Prove_String *path) {
    DIR *d = opendir(path->data);
    if (!d) {
        return prove_list_new(4);
    }

    Prove_List *list = prove_list_new(16);
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
        size_t plen = (size_t)path->length;
        size_t nlen = strlen(ent->d_name);
        int has_sep = (plen > 0 && path->data[plen - 1] == '/');
        size_t sep = has_sep ? 0 : 1;
        char *full = (char *)malloc(plen + sep + nlen + 1);
        if (full) {
            memcpy(full, path->data, plen);
            if (!has_sep) full[plen] = '/';
            memcpy(full + plen + sep, ent->d_name, nlen + 1);
            entry.path = prove_string_from_cstr(full);
            free(full);
        } else {
            entry.path = prove_string_from_cstr(ent->d_name);
        }

        /* Determine type */
        struct stat st;
        if (stat(entry.path->data, &st) == 0 && S_ISDIR(st.st_mode)) {
            entry.tag = 1;  /* Directory */
        } else {
            entry.tag = 0;  /* File */
        }

        /* Heap-allocate entry so list stores a pointer */
        Prove_DirEntry *ep = malloc(sizeof(Prove_DirEntry));
        *ep = entry;
        prove_list_push(list, ep);
    }
    closedir(d);
    return list;
}

Prove_Result prove_io_dir_outputs(Prove_String *path) {
    char buf[4096];
    size_t len = (size_t)path->length;
    if (len >= sizeof(buf)) {
        return prove_result_err(prove_string_from_cstr("path too long"));
    }
    memcpy(buf, path->data, len);
    buf[len] = '\0';
    for (size_t i = 1; i <= len; i++) {
        if (i == len || buf[i] == '/') {
            char saved = buf[i];
            buf[i] = '\0';
            if (mkdir(buf, 0755) != 0 && errno != EEXIST) {
                Prove_String *msg = prove_string_from_cstr(strerror(errno));
                return prove_result_err(msg);
            }
            buf[i] = saved;
        }
    }
    return prove_result_ok();
}

bool prove_io_dir_validates(Prove_String *path) {
    struct stat st;
    return (stat(path->data, &st) == 0 && S_ISDIR(st.st_mode));
}

/* ── Process channel (argv) ──────────────────────────────────── */

static int    _prove_argc = 0;
static char **_prove_argv = NULL;

void prove_io_init_args(int argc, char **argv) {
    _prove_argc = argc;
    _prove_argv = argv;
}

Prove_List *prove_io_process_inputs(void) {
    Prove_List *list = prove_list_new(_prove_argc > 0 ? _prove_argc : 4);
    for (int i = 0; i < _prove_argc; i++) {
        Prove_String *s = prove_string_from_cstr(_prove_argv[i]);
        prove_list_push(list, s);
    }
    return list;
}

bool prove_io_process_validates(Prove_String *value) {
    for (int i = 0; i < _prove_argc; i++) {
        if (strcmp(_prove_argv[i], value->data) == 0) {
            return true;
        }
    }
    return false;
}

Prove_String *prove_io_process_cwd(void) {
    char buf[4096];
    if (getcwd(buf, sizeof(buf)) == NULL) {
        return prove_string_from_cstr("");
    }
    return prove_string_from_cstr(buf);
}

/* ── File handle streaming ───────────────────────────────────── */

Prove_Result prove_file_open_read(Prove_String *path) {
    FILE *fp = fopen(path->data, "r");
    if (!fp) return prove_result_err(prove_string_from_cstr(strerror(errno)));
    Prove_File *f = (Prove_File *)prove_alloc(sizeof(Prove_File));
    f->fp = fp;
    return prove_result_ok_ptr(f);
}

Prove_String *prove_file_readline_handle(Prove_File *handle) {
    if (!handle || !handle->fp || feof(handle->fp)) return NULL;
    char buf[4096];
    if (!fgets(buf, sizeof(buf), handle->fp)) return NULL;
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') buf[--len] = '\0';
    if (len > 0 && buf[len - 1] == '\r') buf[--len] = '\0';
    return prove_string_new(buf, (int64_t)len);
}

void prove_file_close_handle(Prove_File *handle) {
    if (!handle) return;
    if (handle->fp) { fclose(handle->fp); handle->fp = NULL; }
}

Prove_Result prove_file_open_append(Prove_String *path) {
    FILE *fp = fopen(path->data, "a");
    if (!fp) return prove_result_err(prove_string_from_cstr(strerror(errno)));
    Prove_File *f = (Prove_File *)prove_alloc(sizeof(Prove_File));
    f->fp = fp;
    return prove_result_ok_ptr(f);
}

void prove_file_writeln_handle(Prove_File *handle, Prove_String *line) {
    if (!handle || !handle->fp) return;
    fwrite(line->data, 1, (size_t)line->length, handle->fp);
    fputc('\n', handle->fp);
    fflush(handle->fp);
}
