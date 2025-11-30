fn heavy(n: u64) -> u64 {
    let mut s = 0;
    for i in 0..n {
        s += i;
    }
    s
}

fn main() {
    let mut x = 0;
    for _ in 0..5_000_000 {
        x += 1;
    }
    println!("{}", heavy(x));
}

