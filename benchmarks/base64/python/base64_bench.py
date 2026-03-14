import base64
import sys
import os
import platform
import socket


STR_SIZE = 131072
ITERATIONS = 8192


def notify(msg):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not s.connect_ex(("localhost", 9001)):
            s.sendall(bytes(msg, "utf8"))


if __name__ == "__main__":
    data = b"a" * STR_SIZE

    # Verify roundtrip
    encoded_check = base64.b64encode(data)
    decoded_check = base64.b64decode(encoded_check)
    if decoded_check != data:
        print("Verify: FAILED", file=sys.stderr)
        sys.exit(1)
    print("Verify: ok")

    encoded = base64.b64encode(data)

    notify("Python\t%d" % os.getpid())

    # Encode loop
    total_encoded = 0
    for _ in range(ITERATIONS):
        e = base64.b64encode(data)
        total_encoded += len(e)
    print("Encode: %d bytes" % total_encoded)

    # Decode loop
    total_decoded = 0
    for _ in range(ITERATIONS):
        base64.b64decode(encoded)
        total_decoded += 1
    print("Decode: %d iterations" % total_decoded)

    notify("stop")
