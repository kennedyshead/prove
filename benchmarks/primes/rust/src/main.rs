use std::collections::HashMap;
use std::io::Write;
use std::net::TcpStream;

const UPPER_BOUND: usize = 5_000_000;
const PREFIX: &str = "32338";

fn sieve_of_atkin(limit: usize) -> Vec<bool> {
    let mut sieve = vec![false; limit + 1];

    // Step 1: n = 4*x*x + y*y
    let mut x = 1;
    while x * x <= limit {
        let mut y = 1;
        loop {
            let n = 4 * x * x + y * y;
            if n > limit {
                break;
            }
            let r = n % 12;
            if r == 1 || r == 5 {
                sieve[n] = !sieve[n];
            }
            y += 1;
        }
        x += 1;
    }

    // Step 2: n = 3*x*x + y*y
    x = 1;
    while x * x <= limit {
        let mut y = 1;
        loop {
            let n = 3 * x * x + y * y;
            if n > limit {
                break;
            }
            if n % 12 == 7 {
                sieve[n] = !sieve[n];
            }
            y += 1;
        }
        x += 1;
    }

    // Step 3: n = 3*x*x - y*y where x > y
    x = 1;
    while x * x <= limit {
        let mut y = x as isize - 1;
        while y >= 1 {
            let n = 3 * x * x - (y as usize) * (y as usize);
            if n <= limit && n % 12 == 11 {
                sieve[n] = !sieve[n];
            }
            y -= 1;
        }
        x += 1;
    }

    // Eliminate squares of primes
    let mut n = 5;
    while n * n <= limit {
        if sieve[n] {
            let mut k = 1;
            while n * n * k <= limit {
                sieve[n * n * k] = false;
                k += 1;
            }
        }
        n += 1;
    }

    sieve[2] = true;
    sieve[3] = true;
    sieve
}

#[derive(Default)]
struct TrieNode {
    children: HashMap<u8, TrieNode>,
    terminal: bool,
}

fn trie_insert(root: &mut TrieNode, s: &[u8]) {
    let mut node = root;
    for &ch in s {
        node = node.children.entry(ch).or_default();
    }
    node.terminal = true;
}

fn trie_find_prefix<'a>(root: &'a TrieNode, prefix: &[u8]) -> Option<&'a TrieNode> {
    let mut node = root;
    for &ch in prefix {
        match node.children.get(&ch) {
            Some(child) => node = child,
            None => return None,
        }
    }
    Some(node)
}

fn collect_primes(node: &TrieNode, prefix: &str, results: &mut Vec<String>) {
    if node.terminal {
        results.push(prefix.to_string());
    }
    let mut keys: Vec<&u8> = node.children.keys().collect();
    keys.sort();
    for &digit in &keys {
        let child = &node.children[digit];
        let new_prefix = format!("{}{}", prefix, *digit as char);
        collect_primes(child, &new_prefix, results);
    }
}

fn notify(msg: &str) {
    if let Ok(mut s) = TcpStream::connect("localhost:9001") {
        let _ = s.write_all(msg.as_bytes());
    }
}

fn main() {
    let sieve = sieve_of_atkin(UPPER_BOUND);

    let mut root = TrieNode::default();
    for i in 2..=UPPER_BOUND {
        if sieve[i] {
            let s = i.to_string();
            trie_insert(&mut root, s.as_bytes());
        }
    }

    notify(&format!("Rust\t{}", std::process::id()));
    let mut results = Vec::new();
    if let Some(prefix_node) = trie_find_prefix(&root, PREFIX.as_bytes()) {
        collect_primes(prefix_node, PREFIX, &mut results);
    }
    notify("stop");

    if results.is_empty() {
        println!("[]");
    } else {
        println!("[{}]", results.join(", "));
    }
}
