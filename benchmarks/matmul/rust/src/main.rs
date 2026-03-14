use std::env;
use std::io::Write;
use std::net::TcpStream;

fn matgen(n: usize, seed: f64) -> Vec<f64> {
    let tmp = seed / (n as f64) / (n as f64);
    let mut a = vec![0.0f64; n * n];
    for i in 0..n {
        for j in 0..n {
            a[i * n + j] = tmp * (i as f64 - j as f64) * (i as f64 + j as f64);
        }
    }
    a
}

fn matmul(a: &[f64], b: &[f64], n: usize) -> Vec<f64> {
    // Transpose b for cache-friendly access
    let mut bt = vec![0.0f64; n * n];
    for i in 0..n {
        for j in 0..n {
            bt[i * n + j] = b[j * n + i];
        }
    }

    let mut c = vec![0.0f64; n * n];
    for i in 0..n {
        for j in 0..n {
            let mut s = 0.0f64;
            let ai = i * n;
            let btj = j * n;
            for k in 0..n {
                s += a[ai + k] * bt[btj + k];
            }
            c[i * n + j] = s;
        }
    }
    c
}

fn calc(n: usize) -> f64 {
    let a = matgen(n, 1.0);
    let b = matgen(n, 2.0);
    let c = matmul(&a, &b, n);
    c[n / 2 * n + n / 2]
}

fn notify(msg: &str) {
    if let Ok(mut s) = TcpStream::connect("localhost:9001") {
        let _ = s.write_all(msg.as_bytes());
    }
}

fn main() {
    let n: usize = env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(100);

    notify(&format!("Rust\t{}", std::process::id()));
    let result = calc(n);
    notify("stop");

    println!("{:.6}", result);
}
