import sys
import os
import platform
import socket
from pathlib import Path


def notify(msg):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not s.connect_ex(("localhost", 9001)):
            s.sendall(bytes(msg, "utf8"))


class Op:
    INC = 0
    DEC = 1
    RIGHT = 2
    LEFT = 3
    PRINT = 4
    LOOP_START = 5
    LOOP_END = 6


def parse(source):
    ops = []
    stack = []
    for ch in source:
        if ch == "+":
            ops.append((Op.INC, 1))
        elif ch == "-":
            ops.append((Op.DEC, 1))
        elif ch == ">":
            ops.append((Op.RIGHT, 1))
        elif ch == "<":
            ops.append((Op.LEFT, 1))
        elif ch == ".":
            ops.append((Op.PRINT, 0))
        elif ch == "[":
            stack.append(len(ops))
            ops.append((Op.LOOP_START, 0))
        elif ch == "]":
            open_idx = stack.pop()
            ops.append((Op.LOOP_END, open_idx))
            ops[open_idx] = (Op.LOOP_START, len(ops) - 1)
    return ops


def evaluate(ops):
    tape = [0] * 30000
    ptr = 0
    pc = 0
    op_count = len(ops)
    sum1 = 0
    sum2 = 0

    while pc < op_count:
        op_type, op_arg = ops[pc]
        if op_type == Op.INC:
            tape[ptr] = (tape[ptr] + op_arg) % 256
        elif op_type == Op.DEC:
            tape[ptr] = (tape[ptr] - op_arg + 256) % 256
        elif op_type == Op.RIGHT:
            ptr += op_arg
        elif op_type == Op.LEFT:
            ptr -= op_arg
        elif op_type == Op.PRINT:
            byte = tape[ptr]
            sum1 = (sum1 + byte) % 255
            sum2 = (sum2 + sum1) % 255
        elif op_type == Op.LOOP_START:
            if tape[ptr] == 0:
                pc = op_arg
        elif op_type == Op.LOOP_END:
            if tape[ptr] != 0:
                pc = op_arg
        pc += 1

    return sum2 * 256 + sum1


if __name__ == "__main__":
    source = Path("bench.b").read_text()
    ops = parse(source)

    notify("Python\t%d" % os.getpid())
    checksum = evaluate(ops)
    notify("stop")

    print("Output checksum: %d" % checksum)
