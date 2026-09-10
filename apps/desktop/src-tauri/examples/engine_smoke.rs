//! Developer-only smoke harness using the production process controller.
use mediaqc_desktop::engine::{Config, Controller};
use std::{path::PathBuf, time::Duration};

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let controller = Controller::new(Config::packaged(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/release"),
        root.join(".cache/native-smoke"),
    ));
    println!(
        "capabilities: {}",
        controller.start().expect("engine startup")
    );
    println!("ping: {}", controller.ping().expect("system.ping"));
    println!("pid: {}", controller.snapshot().pid.expect("engine pid"));
    if std::env::args().any(|arg| arg == "--hold") {
        std::thread::sleep(Duration::from_secs(60));
    }
    println!("shutdown: {}", controller.quit().expect("clean shutdown"));
}
