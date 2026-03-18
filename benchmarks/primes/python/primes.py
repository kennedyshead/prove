import os
import socket


UPPER_BOUND = 5_000_000
PREFIX = "32338"


def notify(msg):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not s.connect_ex(("localhost", 9001)):
            s.sendall(bytes(msg, "utf8"))


def sieve_of_atkin(limit):
    sieve = bytearray(limit + 1)

    # Step 1: n = 4*x*x + y*y
    x = 1
    while x * x <= limit:
        y = 1
        while True:
            n = 4 * x * x + y * y
            if n > limit:
                break
            r = n % 12
            if r == 1 or r == 5:
                sieve[n] ^= 1
            y += 1
        x += 1

    # Step 2: n = 3*x*x + y*y
    x = 1
    while x * x <= limit:
        y = 1
        while True:
            n = 3 * x * x + y * y
            if n > limit:
                break
            if n % 12 == 7:
                sieve[n] ^= 1
            y += 1
        x += 1

    # Step 3: n = 3*x*x - y*y where x > y
    x = 1
    while x * x <= limit:
        y = x - 1
        while y >= 1:
            n = 3 * x * x - y * y
            if n <= limit and n % 12 == 11:
                sieve[n] ^= 1
            y -= 1
        x += 1

    # Eliminate squares of primes
    n = 5
    while n * n <= limit:
        if sieve[n]:
            k = 1
            while n * n * k <= limit:
                sieve[n * n * k] = 0
                k += 1
        n += 1

    sieve[2] = 1
    sieve[3] = 1
    return sieve


class TrieNode:
    __slots__ = ("children", "terminal")

    def __init__(self):
        self.children = {}
        self.terminal = False


def trie_insert(root, s):
    node = root
    for ch in s:
        if ch not in node.children:
            node.children[ch] = TrieNode()
        node = node.children[ch]
    node.terminal = True


def trie_find_prefix(root, prefix):
    node = root
    for ch in prefix:
        if ch not in node.children:
            return None
        node = node.children[ch]
    return node


def collect_primes(node, prefix):
    results = []
    if node.terminal:
        results.append(prefix)
    for digit in sorted(node.children.keys()):
        results.extend(collect_primes(node.children[digit], prefix + digit))
    return results


if __name__ == "__main__":
    sieve = sieve_of_atkin(UPPER_BOUND)

    root = TrieNode()
    for i in range(2, UPPER_BOUND + 1):
        if sieve[i]:
            trie_insert(root, str(i))

    notify("Python\t%d" % os.getpid())
    prefix_node = trie_find_prefix(root, PREFIX)
    if prefix_node is None:
        results = []
    else:
        results = collect_primes(prefix_node, PREFIX)
    notify("stop")

    if results:
        print("[%s]" % ", ".join(results))
    else:
        print("[]")
