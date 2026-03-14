import sys
import os
import platform
import socket


def notify(msg):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not s.connect_ex(("localhost", 9001)):
            s.sendall(bytes(msg, "utf8"))


def matgen(n, seed):
    tmp = seed / n / n
    a = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            a[i][j] = tmp * (i - j) * (i + j)
    return a


def matmul(a, b):
    n = len(a)
    # Transpose b for cache-friendly access
    bt = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            bt[i][j] = b[j][i]

    c = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            s = 0.0
            ai = a[i]
            btj = bt[j]
            for k in range(n):
                s += ai[k] * btj[k]
            c[i][j] = s
    return c


def calc(n):
    a = matgen(n, 1.0)
    b = matgen(n, 2.0)
    c = matmul(a, b)
    return c[n // 2][n // 2]


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    notify("Python\t%d" % os.getpid())
    result = calc(n)
    notify("stop")

    print("%.6f" % result)
