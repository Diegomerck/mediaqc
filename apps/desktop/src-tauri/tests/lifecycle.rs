use mediaqc_desktop::engine::{Config, Controller};
use serde_json::json;
use std::{
    path::PathBuf,
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

fn config(mode: &str) -> Config {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    Config {
        executable: root.join(".venv/Scripts/python.exe"),
        args: vec![
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/engine_stub.py")
                .to_string_lossy()
                .into_owned(),
            mode.into(),
        ],
        log_path: root
            .join(".cache/native-tests")
            .join(Uuid::new_v4().to_string())
            .join("音楽 O'Brien & Sons/engine.log"),
        timeout: Duration::from_secs(2),
        shutdown_timeout: Duration::from_millis(250),
    }
}

#[test]
fn handshake_ping_shutdown_restart_and_single_process() {
    let controller = Controller::new(config("normal"));
    assert_eq!(controller.start().unwrap()["protocol_version"], "1.0");
    let pid = controller.snapshot().pid;
    assert!(pid.is_some());
    controller.start().unwrap();
    assert_eq!(controller.snapshot().pid, pid);
    assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
    assert_eq!(controller.stop().unwrap(), json!({"forced":false}));
    assert_eq!(controller.snapshot().phase, "stopped");
    assert_eq!(controller.snapshot().pid, None);
    controller.start().unwrap();
    assert_ne!(controller.snapshot().pid, pid);
    controller.quit().unwrap();
}

#[test]
fn spawn_failure_is_recoverable() {
    let mut setup = config("normal");
    setup.executable = setup.executable.with_file_name("missing-engine.exe");
    let controller = Controller::new(setup);
    for _ in 0..2 {
        assert_eq!(controller.start().unwrap_err().code, "ENGINE_START_FAILED");
        assert_eq!(controller.snapshot().phase, "error");
    }
    controller.quit().unwrap();
}

#[test]
fn startup_failures_are_bounded_and_reaped() {
    for (mode, code) in [
        ("exit_before_ready", "ENGINE_EXITED"),
        ("silent", "ENGINE_TIMEOUT"),
        ("bad_version", "PROTOCOL_VERSION_UNSUPPORTED"),
        ("bad_capabilities", "PROTOCOL_VERSION_UNSUPPORTED"),
        ("invalid_json", "ENGINE_PROTOCOL_ERROR"),
        ("oversized", "ENGINE_PROTOCOL_ERROR"),
        ("partial", "ENGINE_PROTOCOL_ERROR"),
    ] {
        let controller = Controller::new(config(mode));
        let start = Instant::now();
        assert_eq!(controller.start().unwrap_err().code, code, "{mode}");
        assert!(start.elapsed() < Duration::from_secs(8));
        assert_eq!(controller.snapshot().phase, "error");
        assert_eq!(controller.snapshot().pid, None);
        controller.quit().unwrap();
    }
}

#[test]
fn runtime_crash_timeout_and_wrong_correlation_are_errors() {
    for (mode, code) in [
        ("crash", "ENGINE_EXITED"),
        ("ping_timeout", "ENGINE_TIMEOUT"),
        ("wrong_id", "ENGINE_PROTOCOL_ERROR"),
    ] {
        let controller = Controller::new(config(mode));
        controller.start().unwrap();
        assert_eq!(controller.ping().unwrap_err().code, code);
        assert_eq!(controller.snapshot().phase, "error");
        assert_eq!(controller.snapshot().pid, None);
        controller.quit().unwrap();
    }
}

#[test]
fn stderr_noise_is_separate_and_logged() {
    let setup = config("stderr");
    let path = setup.log_path.clone();
    let controller = Controller::new(setup);
    controller.start().unwrap();
    for _ in 0..12 {
        assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
    }
    controller.stop().unwrap();
    let log = std::fs::read(&path).unwrap();
    assert!(!log.is_empty());
    assert!(log.len() <= 1024 * 1024);
    assert!(String::from_utf8_lossy(&log).contains("diagnostic noise"));
    controller.quit().unwrap();
}

#[test]
fn unresponsive_shutdown_is_forced_and_reaped() {
    let controller = Controller::new(config("ignore_shutdown"));
    controller.start().unwrap();
    let start = Instant::now();
    assert_eq!(controller.stop().unwrap(), json!({"forced":true}));
    assert!(start.elapsed() < Duration::from_secs(3));
    assert_eq!(controller.snapshot().pid, None);
    controller.quit().unwrap();
}

#[cfg(windows)]
fn terminate(pid: u32) {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{OpenProcess, PROCESS_TERMINATE, TerminateProcess},
    };
    // SAFETY: handle is opened only for the test-owned process, then closed once.
    unsafe {
        let handle = OpenProcess(PROCESS_TERMINATE, 0, pid);
        assert!(!handle.is_null());
        assert_ne!(TerminateProcess(handle, 23), 0);
        CloseHandle(handle);
    }
}

#[test]
#[cfg(windows)]
fn idle_crash_is_detected_without_a_request_and_allows_restart() {
    let controller = Controller::new(config("normal"));
    controller.start().unwrap();
    terminate(controller.snapshot().pid.unwrap());
    let deadline = Instant::now() + Duration::from_secs(3);
    while controller.snapshot().phase != "error" && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(controller.snapshot().error.unwrap().code, "ENGINE_EXITED");
    controller.start().unwrap();
    assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
    controller.quit().unwrap();
}
