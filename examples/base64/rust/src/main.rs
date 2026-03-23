use base64::{engine::general_purpose::STANDARD, Engine};
use std::io::Write;
use std::net::TcpStream;

const STR_SIZE: usize = 131072;
const ITERATIONS: usize = 8192;

fn notify(msg: &str) {
    if let Ok(mut s) = TcpStream::connect("localhost:9001") {
        let _ = s.write_all(msg.as_bytes());
    }
}

fn main() {
    let data = vec![b'a'; STR_SIZE];

    // Verify roundtrip
    let encoded_check = STANDARD.encode(&data);
    let decoded_check = STANDARD.decode(&encoded_check).unwrap();
    assert_eq!(decoded_check, data, "Verify: FAILED");
    println!("Verify: ok");

    let encoded = STANDARD.encode(&data);

    notify(&format!("Rust\t{}", std::process::id()));

    // Encode loop
    let mut total_encoded: usize = 0;
    for _ in 0..ITERATIONS {
        let e = STANDARD.encode(&data);
        total_encoded += e.len();
    }
    println!("Encode: {} bytes", total_encoded);

    // Decode loop
    let mut total_decoded: usize = 0;
    for _ in 0..ITERATIONS {
        let _ = STANDARD.decode(&encoded).unwrap();
        total_decoded += 1;
    }
    println!("Decode: {} iterations", total_decoded);

    notify("stop");
}
