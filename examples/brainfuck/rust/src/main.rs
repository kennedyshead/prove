use std::fs;
use std::io::{self, Write};
use std::net::TcpStream;

const TAPE_SIZE: usize = 30000;

#[derive(Clone, Copy)]
enum Op {
    Inc(u8),
    Dec(u8),
    Right(usize),
    Left(usize),
    Print,
    LoopStart(usize),
    LoopEnd(usize),
}

fn parse(source: &[u8]) -> Vec<Op> {
    let mut ops = Vec::new();
    let mut stack = Vec::new();
    for &ch in source {
        match ch {
            b'+' => ops.push(Op::Inc(1)),
            b'-' => ops.push(Op::Dec(1)),
            b'>' => ops.push(Op::Right(1)),
            b'<' => ops.push(Op::Left(1)),
            b'.' => ops.push(Op::Print),
            b'[' => {
                stack.push(ops.len());
                ops.push(Op::LoopStart(0));
            }
            b']' => {
                let open = stack.pop().unwrap();
                let close = ops.len();
                ops.push(Op::LoopEnd(open));
                ops[open] = Op::LoopStart(close);
            }
            _ => {}
        }
    }
    ops
}

fn evaluate(ops: &[Op]) -> u32 {
    let mut tape = vec![0u8; TAPE_SIZE];
    let mut ptr: usize = 0;
    let mut pc: usize = 0;
    let mut sum1: u32 = 0;
    let mut sum2: u32 = 0;

    while pc < ops.len() {
        match ops[pc] {
            Op::Inc(v) => tape[ptr] = tape[ptr].wrapping_add(v),
            Op::Dec(v) => tape[ptr] = tape[ptr].wrapping_sub(v),
            Op::Right(v) => ptr += v,
            Op::Left(v) => ptr -= v,
            Op::Print => {
                let byte = tape[ptr] as u32;
                sum1 = (sum1 + byte) % 255;
                sum2 = (sum2 + sum1) % 255;
            }
            Op::LoopStart(target) => {
                if tape[ptr] == 0 {
                    pc = target;
                }
            }
            Op::LoopEnd(target) => {
                if tape[ptr] != 0 {
                    pc = target;
                }
            }
        }
        pc += 1;
    }

    sum2 * 256 + sum1
}

fn notify(msg: &str) {
    if let Ok(mut s) = TcpStream::connect("localhost:9001") {
        let _ = s.write_all(msg.as_bytes());
    }
}

fn main() {
    let source = fs::read("bench.b").expect("Could not read bench.b");
    let ops = parse(&source);

    notify(&format!("Rust\t{}", std::process::id()));
    let checksum = evaluate(&ops);
    notify("stop");

    println!("Output checksum: {}", checksum);
}
