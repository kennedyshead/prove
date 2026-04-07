#!/usr/bin/env python3
"""Test harness for the native Prove LSP server.

Launches `proof lsp` as a subprocess, sends JSON-RPC messages over stdio,
and validates the responses.

Usage:
    python scripts/test_lsp.py [path/to/proof]
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def encode_message(obj: dict) -> bytes:
    """Encode a JSON-RPC message with Content-Length framing."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def _reader_thread(stdout, msg_queue: queue.Queue, noise_lines: list):
    """Background thread that reads Content-Length framed messages from stdout.

    Lines that aren't part of the LSP framing (e.g. [INFO] log lines) are
    collected into noise_lines for later reporting.
    """
    try:
        while True:
            # Read lines until we find Content-Length
            content_length = None
            while True:
                line = stdout.readline()
                if not line:
                    return  # EOF
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str.startswith("Content-Length:"):
                    content_length = int(line_str.split(":")[1].strip())
                elif line_str == "" and content_length is not None:
                    break  # blank line after header — body follows
                elif line_str == "":
                    continue  # stray blank line
                else:
                    # Non-LSP output on stdout (e.g. [INFO] lines)
                    noise_lines.append(line_str)
                    continue

            body = stdout.read(content_length)
            if not body:
                return
            msg = json.loads(body.decode("utf-8"))
            msg_queue.put(msg)
    except Exception:
        return


def _stderr_thread(stderr, lines: list):
    """Background thread that collects stderr output."""
    try:
        for line in stderr:
            lines.append(line.decode("utf-8", errors="replace").rstrip())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class LSPTestRunner:
    def __init__(self, proof_path: str):
        self.proof_path = proof_path
        self.proc: subprocess.Popen | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.stderr_lines: list[str] = []
        self.stdout_noise: list[str] = []
        self.msg_id = 0
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    def start(self):
        self.proc = subprocess.Popen(
            [self.proof_path, "lsp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Start background threads to read stdout and stderr
        t1 = threading.Thread(
            target=_reader_thread,
            args=(self.proc.stdout, self.msg_queue, self.stdout_noise),
            daemon=True,
        )
        t2 = threading.Thread(
            target=_stderr_thread,
            args=(self.proc.stderr, self.stderr_lines),
            daemon=True,
        )
        t1.start()
        t2.start()

    def stop(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
            self.proc = None

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def send(self, msg: dict):
        assert self.proc and self.proc.stdin
        data = encode_message(msg)
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except BrokenPipeError:
            pass  # Server already exited — tests will detect via missing responses

    def send_request(self, method: str, params: dict | None = None) -> int:
        rid = self.next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        return rid

    def send_notification(self, method: str, params: dict | None = None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def wait_for_message(self, timeout: float = 10.0) -> dict | None:
        try:
            return self.msg_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def collect_messages(self, timeout: float = 3.0) -> list[dict]:
        """Collect all messages that arrive within timeout."""
        messages = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                msg = self.msg_queue.get(timeout=min(remaining, 0.5))
                messages.append(msg)
            except queue.Empty:
                if messages:
                    break  # Got some messages, no more coming
        return messages

    def check(self, name: str, condition: bool, detail: str = ""):
        if condition:
            self.passed += 1
            print(f"  PASS: {name}")
        else:
            self.failed += 1
            info = f"  FAIL: {name}"
            if detail:
                info += f" — {detail}"
            print(info)
            self.errors.append(info)

    # -- Individual tests --------------------------------------------------

    def test_initialize(self):
        print("\n--- test_initialize ---")
        rid = self.send_request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": "file:///tmp/test",
                "capabilities": {},
            },
        )
        resp = self.wait_for_message()
        self.check(
            "got response",
            resp is not None,
            "event loop may have exited after processing one worker "
            "(for loop over workers list exhausted)",
        )
        if resp is None:
            return

        self.check("jsonrpc is 2.0", resp.get("jsonrpc") == "2.0")
        self.check(
            "id matches", resp.get("id") == rid, f"expected {rid}, got {resp.get('id')}"
        )
        self.check("has result", "result" in resp)

        result = resp.get("result", {})
        caps = result.get("capabilities", {})
        self.check(
            "has textDocumentSync", "textDocumentSync" in caps, f"capabilities: {caps}"
        )

    def test_initialized(self):
        print("\n--- test_initialized ---")
        # initialized is a notification — no response expected
        self.send_notification("initialized", {})
        # Just check the server doesn't crash
        msg = self.wait_for_message(timeout=1.0)
        self.check("no unexpected response", msg is None, f"got: {msg}")

    def test_did_open_valid(self):
        print("\n--- test_didOpen (valid source) ---")
        self.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": "file:///tmp/test/hello.prv",
                    "languageId": "prove",
                    "version": 1,
                    "text": 'module Hello\n  narrative: """\n  A simple test.\n  """\n',
                }
            },
        )
        # Server processes the document (check stderr) but diagnostics
        # notifications require the .prv code to route OnSend events from
        # lsp_on_document back through the event loop.
        messages = self.collect_messages(timeout=5.0)
        diag_msgs = [
            m for m in messages if m.get("method") == "textDocument/publishDiagnostics"
        ]
        self.check(
            "got diagnostics notification",
            len(diag_msgs) >= 1,
            f"got {len(diag_msgs)} diag messages out of {len(messages)} total"
            " (lsp.prv: lsp_on_document returns OnSend but dispatches"
            " message discards it)",
        )
        if diag_msgs:
            params = diag_msgs[0].get("params", {})
            self.check(
                "uri matches",
                "hello.prv" in params.get("uri", ""),
                f"uri: {params.get('uri')}",
            )
            diags = params.get("diagnostics", [])
            self.check(
                "no errors for valid source",
                len(diags) == 0,
                f"diagnostics: {json.dumps(diags, indent=2)}",
            )

    def test_did_open_invalid(self):
        print("\n--- test_didOpen (invalid source) ---")
        self.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": "file:///tmp/test/bad.prv",
                    "languageId": "prove",
                    "version": 1,
                    "text": "this is not valid prove {{{{",
                }
            },
        )
        messages = self.collect_messages(timeout=5.0)
        diag_msgs = [
            m for m in messages if m.get("method") == "textDocument/publishDiagnostics"
        ]
        self.check(
            "got diagnostics notification",
            len(diag_msgs) >= 1,
            f"got {len(diag_msgs)} diag messages",
        )
        if diag_msgs:
            params = diag_msgs[0].get("params", {})
            diags = params.get("diagnostics", [])
            self.check(
                "has error diagnostics",
                len(diags) > 0,
                "expected at least one diagnostic for invalid source"
                " (collect_errors is __attribute__((pure)) but mutates"
                " diagnostics list — compiler may optimize away the call)",
            )
            if diags:
                self.check(
                    "diagnostic has message", "message" in diags[0], f"diag: {diags[0]}"
                )

    def test_did_change(self):
        print("\n--- test_didChange ---")
        self.send_notification(
            "textDocument/didChange",
            {
                "textDocument": {
                    "uri": "file:///tmp/test/hello.prv",
                    "version": 2,
                },
                "contentChanges": [
                    {"text": 'module Hello\n  narrative: """\n  Updated.\n  """\n'}
                ],
            },
        )
        messages = self.collect_messages(timeout=5.0)
        diag_msgs = [
            m for m in messages if m.get("method") == "textDocument/publishDiagnostics"
        ]
        self.check(
            "got diagnostics after change",
            len(diag_msgs) >= 1,
            f"got {len(diag_msgs)} messages",
        )

    def test_did_save(self):
        print("\n--- test_didSave ---")
        self.send_notification(
            "textDocument/didSave",
            {
                "textDocument": {
                    "uri": "file:///tmp/test/hello.prv",
                },
                "text": 'module Hello\n  narrative: """\n  Saved.\n  """\n',
            },
        )
        messages = self.collect_messages(timeout=5.0)
        diag_msgs = [
            m for m in messages if m.get("method") == "textDocument/publishDiagnostics"
        ]
        self.check(
            "got diagnostics after save",
            len(diag_msgs) >= 1,
            f"got {len(diag_msgs)} messages",
        )

    def test_unhandled_method(self):
        print("\n--- test_unhandled_method ---")
        self.send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": "file:///tmp/test/hello.prv"},
                "position": {"line": 0, "character": 0},
            },
        )
        # Server logs "Unhandled: ..." but doesn't send a response
        msg = self.wait_for_message(timeout=2.0)
        self.check("no response for unhandled method", msg is None, f"got: {msg}")

    def test_shutdown_exit(self):
        print("\n--- test_shutdown_exit ---")
        if self.is_alive():
            rid = self.send_request("shutdown")
            resp = self.wait_for_message(timeout=5.0)
            self.check("got shutdown response", resp is not None)
            if resp:
                self.check(
                    "shutdown result is null",
                    resp.get("result") is None,
                    f"result: {resp.get('result')}",
                )
                self.check(
                    "shutdown id matches",
                    resp.get("id") == rid,
                    f"expected {rid}, got {resp.get('id')}",
                )
            self.send_notification("exit")
        else:
            self.check(
                "got shutdown response", False, "server already exited before shutdown"
            )

        # Wait for process to terminate
        if self.proc:
            try:
                self.proc.wait(timeout=5)
                self.check("process exited", True)
                self.check(
                    "exit code is 0",
                    self.proc.returncode == 0,
                    f"exit code: {self.proc.returncode}",
                )
            except subprocess.TimeoutExpired:
                self.check("process exited", False, "process did not exit in time")
                self.proc.kill()
            self.proc = None

    # -- Run all tests -----------------------------------------------------

    def run(self):
        print(f"Using: {self.proof_path}")
        self.start()

        tests = [
            self.test_initialize,
            self.test_initialized,
            self.test_did_open_valid,
            self.test_did_open_invalid,
            self.test_did_change,
            self.test_did_save,
            self.test_unhandled_method,
            self.test_shutdown_exit,
        ]

        try:
            for test in tests:
                if not self.is_alive() and test != self.test_shutdown_exit:
                    name = test.__name__
                    print(f"\n--- {name} ---")
                    self.check(
                        "server still running", False, "server exited prematurely"
                    )
                    continue
                test()
        except Exception as exc:
            print(f"\nFATAL: {exc}")
            self.failed += 1
            self.errors.append(f"FATAL: {exc}")
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()

        # Give stderr thread a moment to flush
        time.sleep(0.2)

        # Summary
        print(f"\n{'=' * 50}")
        print(f"Results: {self.passed} passed, {self.failed} failed")
        if self.errors:
            print("Failures:")
            for e in self.errors:
                print(f"  {e}")
        if self.stdout_noise:
            print("\nNon-LSP output on stdout (BUG — corrupts protocol):")
            for line in self.stdout_noise:
                print(f"  {line}")
        if self.stderr_lines:
            print("\nServer stderr:")
            for line in self.stderr_lines:
                print(f"  {line}")
        print(f"{'=' * 50}")
        return self.failed == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    # Default to the built proof binary
    default_path = os.path.join(
        os.path.dirname(__file__), "..", "proof", "build", "proof"
    )
    proof_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    proof_path = os.path.abspath(proof_path)

    if not os.path.isfile(proof_path):
        print(f"Error: proof binary not found at {proof_path}")
        print("Usage: python scripts/test_lsp.py [path/to/proof]")
        sys.exit(1)

    runner = LSPTestRunner(proof_path)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
