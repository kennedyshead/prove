"""Tests for the prove_event C runtime (event queue for listens dispatcher)."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestEventQueue:
    def test_new_and_free(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_event.h"
            #include <stdio.h>

            int main(void) {
                Prove_EventNodeQueue *q = prove_event_queue_new();
                if (!q) return 1;
                if (q->count != 0) return 2;
                if (q->closed) return 3;
                prove_event_queue_free(q);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="event_new")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_send_and_count(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_event.h"
            #include <stdio.h>

            int main(void) {
                Prove_EventNodeQueue *q = prove_event_queue_new();
                prove_event_queue_send(q, 0, NULL);
                if (q->count != 1) return 1;
                prove_event_queue_send(q, 1, NULL);
                if (q->count != 2) return 2;
                prove_event_queue_free(q);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="event_send")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_fifo_order(self, tmp_path, runtime_dir):
        """Events are dequeued in FIFO order (tag 10, 20, 30)."""
        code = textwrap.dedent("""\
            #include "prove_event.h"
            #include <stdio.h>
            #include <stdlib.h>

            int main(void) {
                Prove_EventNodeQueue *q = prove_event_queue_new();
                prove_event_queue_send(q, 10, NULL);
                prove_event_queue_send(q, 20, NULL);
                prove_event_queue_send(q, 30, NULL);

                /* Recv without coro — queue is non-empty so no yield needed */
                Prove_EventNode *e1 = q->head;
                q->head = e1->next;
                if (!q->head) q->tail = NULL;
                q->count--;

                Prove_EventNode *e2 = q->head;
                q->head = e2->next;
                if (!q->head) q->tail = NULL;
                q->count--;

                Prove_EventNode *e3 = q->head;
                q->head = e3->next;
                if (!q->head) q->tail = NULL;
                q->count--;

                if (e1->tag != 10) return 1;
                if (e2->tag != 20) return 2;
                if (e3->tag != 30) return 3;
                if (q->count != 0) return 4;

                free(e1); free(e2); free(e3);
                prove_event_queue_free(q);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="event_fifo")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_close(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_event.h"
            #include <stdio.h>

            int main(void) {
                Prove_EventNodeQueue *q = prove_event_queue_new();
                if (q->closed) return 1;
                prove_event_queue_close(q);
                if (!q->closed) return 2;
                prove_event_queue_free(q);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="event_close")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_payload(self, tmp_path, runtime_dir):
        """Events carry a void* payload."""
        code = textwrap.dedent("""\
            #include "prove_event.h"
            #include <stdio.h>
            #include <stdlib.h>

            int main(void) {
                Prove_EventNodeQueue *q = prove_event_queue_new();
                int *val = malloc(sizeof(int));
                *val = 42;
                prove_event_queue_send(q, 1, val);

                Prove_EventNode *ev = q->head;
                q->head = ev->next;
                if (!q->head) q->tail = NULL;
                q->count--;

                int *got = (int *)ev->payload;
                if (*got != 42) return 1;

                free(val);
                free(ev);
                prove_event_queue_free(q);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="event_payload")
        assert result.returncode == 0
        assert "OK" in result.stdout
