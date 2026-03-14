use serde::Deserialize;
use std::fs;
use std::io::Write;
use std::net::TcpStream;

#[derive(Deserialize)]
struct Coordinate {
    x: f64,
    y: f64,
    z: f64,
}

#[derive(Deserialize)]
struct Root {
    coordinates: Vec<Coordinate>,
}

fn notify(msg: &str) {
    if let Ok(mut s) = TcpStream::connect("localhost:9001") {
        let _ = s.write_all(msg.as_bytes());
    }
}

fn calc(text: &str) -> (f64, f64, f64) {
    let root: Root = serde_json::from_str(text).unwrap();
    let len = root.coordinates.len() as f64;
    let mut x = 0.0_f64;
    let mut y = 0.0_f64;
    let mut z = 0.0_f64;
    for coord in &root.coordinates {
        x += coord.x;
        y += coord.y;
        z += coord.z;
    }
    (x / len, y / len, z / len)
}

fn main() {
    // Verify
    let right = (2.0, 0.5, 0.25);
    for v in [
        r#"{"coordinates":[{"x":2.0,"y":0.5,"z":0.25}]}"#,
        r#"{"coordinates":[{"y":0.5,"x":2.0,"z":0.25}]}"#,
    ] {
        let left = calc(v);
        assert_eq!(left, right, "Verify: FAILED: {:?} != {:?}", left, right);
    }

    let text = fs::read_to_string("/tmp/1.json").expect("Cannot read /tmp/1.json");

    notify(&format!("Rust\t{}", std::process::id()));
    let (x, y, z) = calc(&text);
    notify("stop");

    println!("{}", x);
    println!("{}", y);
    println!("{}", z);
}
