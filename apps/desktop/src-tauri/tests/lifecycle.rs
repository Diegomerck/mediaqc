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

#[test]
fn application_errors_preserve_engine_session() {
    let controller = Controller::new(config("normal"));
    controller.start().unwrap();
    let pid = controller.snapshot().pid;
    let failure = controller
        .request("project.get".into(), json!({}))
        .unwrap_err();
    assert_eq!(failure.code, "PROJECT_NOT_FOUND");
    assert!(failure.recoverable);
    assert_eq!(controller.snapshot().pid, pid);
    assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
    controller.quit().unwrap();
}

#[test]
fn stopping_interrupts_an_active_inspection() {
    let setup = config("inspection_timeout");
    let log = setup.log_path.clone();
    let controller = Controller::new(setup);
    controller.start().unwrap();
    let inspecting = controller.clone();
    let worker = thread::spawn(move || inspecting.request("media.inspect".into(), json!({})));
    let deadline = Instant::now() + Duration::from_secs(3);
    while !std::fs::read_to_string(&log)
        .unwrap_or_default()
        .contains("inspection-active")
    {
        assert!(Instant::now() < deadline);
        thread::sleep(Duration::from_millis(20));
    }
    let start = Instant::now();
    controller.stop().unwrap();
    assert!(start.elapsed() < Duration::from_secs(4));
    assert_eq!(
        worker.join().unwrap().unwrap_err().code,
        "ENGINE_INSPECTION_INTERRUPTED"
    );
    assert_eq!(controller.snapshot().phase, "stopped");
    controller.quit().unwrap();
}

#[test]
fn analysis_events_interleave_with_responses_and_idle_health_checks() {
    let (sender, receiver) = std::sync::mpsc::channel();
    let controller = Controller::with_events(
        config("events"),
        std::sync::Arc::new(move |event| {
            sender.send(event).unwrap();
        }),
    );
    controller.start().unwrap();
    assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
    assert_eq!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap()["event"],
        "analysis.progress"
    );
    assert_eq!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap()["event"],
        "analysis.cancelled"
    );
    assert_eq!(controller.snapshot().phase, "ready");
    controller.quit().unwrap();
}

#[test]
fn invalid_analysis_event_is_a_protocol_error() {
    let controller = Controller::new(config("bad_event"));
    controller.start().unwrap();
    assert_eq!(controller.ping().unwrap_err().code, "ENGINE_PROTOCOL_ERROR");
    controller.quit().unwrap();
}

#[test]
#[cfg(windows)]
fn active_ffmpeg_is_reaped_on_cancel_shutdown_and_engine_crash() {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{OpenProcess, WaitForSingleObject},
    };
    for action in ["cancel", "shutdown", "crash"] {
        let mut setup = config("jobs");
        let directory = setup.log_path.parent().unwrap().to_path_buf();
        std::fs::create_dir_all(&directory).unwrap();
        setup
            .args
            .push(directory.join("recovery").to_string_lossy().into_owned());
        let log = setup.log_path.clone();
        let source = directory.join("source.wav");
        let mut wave = b"RIFF".to_vec();
        wave.extend_from_slice(&96036u32.to_le_bytes());
        wave.extend_from_slice(b"WAVEfmt ");
        wave.extend_from_slice(&16u32.to_le_bytes());
        wave.extend_from_slice(&1u16.to_le_bytes());
        wave.extend_from_slice(&1u16.to_le_bytes());
        wave.extend_from_slice(&48000u32.to_le_bytes());
        wave.extend_from_slice(&96000u32.to_le_bytes());
        wave.extend_from_slice(&2u16.to_le_bytes());
        wave.extend_from_slice(&16u16.to_le_bytes());
        wave.extend_from_slice(b"data");
        wave.extend_from_slice(&96000u32.to_le_bytes());
        wave.resize(96044, 0);
        std::fs::write(&source, &wave).unwrap();
        let controller = Controller::new(setup);
        controller.start().unwrap();
        let project = controller
            .request(
                "project.create".into(),
                json!({"directory":directory.join("project"), "name":"Native job"}),
            )
            .unwrap();
        let media = controller
            .request(
                "media.inspect".into(),
                json!({"project_id":project["id"], "absolute_path":source}),
            )
            .unwrap();
        let run = controller.request("analysis.start".into(), json!({"project_id":project["id"], "media_asset_id":media["media_asset_id"], "profile_key":"general_technical_qc", "profile_version":"1.0.0", "ai_mode":"OFF"})).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let pid = loop {
            let content = std::fs::read_to_string(&log).unwrap_or_default();
            if let Some(value) = content
                .lines()
                .find_map(|line| line.strip_prefix("owned-ffmpeg-pid:"))
            {
                break value.parse::<u32>().unwrap();
            }
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(10));
        };
        // SAFETY: observe the exact test-owned FFmpeg process handle, close it once.
        let handle = unsafe { OpenProcess(0x00100000, 0, pid) }; // SYNCHRONIZE access
        assert!(!handle.is_null());
        if action == "cancel" {
            controller
                .request(
                    "analysis.cancel".into(),
                    json!({"analysis_run_id":run["analysis_run_id"]}),
                )
                .unwrap();
        } else if action == "shutdown" {
            assert_eq!(controller.stop().unwrap()["forced"], false);
        } else {
            terminate(controller.snapshot().pid.unwrap());
            let deadline = Instant::now() + Duration::from_secs(3);
            while controller.snapshot().phase != "error" {
                assert!(Instant::now() < deadline);
                thread::sleep(Duration::from_millis(10));
            }
        }
        assert_eq!(
            unsafe { WaitForSingleObject(handle, 5000) },
            0,
            "FFmpeg survived {action}"
        );
        unsafe {
            CloseHandle(handle);
        }
        if action != "cancel" {
            controller.start().unwrap();
            controller
                .request(
                    "project.open".into(),
                    json!({"project_file":project["project_file"]}),
                )
                .unwrap();
        }
        let deadline = Instant::now() + Duration::from_secs(3);
        let result = loop {
            let result = controller
                .request(
                    "analysis.get".into(),
                    json!({"analysis_run_id":run["analysis_run_id"]}),
                )
                .unwrap();
            if matches!(result["status"].as_str(), Some("CANCELLED" | "FAILED")) {
                break result;
            }
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(10));
        };
        assert_eq!(
            result["status"],
            if action == "crash" {
                "FAILED"
            } else {
                "CANCELLED"
            }
        );
        if action == "crash" {
            assert_eq!(result["error_code"], "ENGINE_INTERRUPTED");
        }
        assert_eq!(controller.ping().unwrap(), json!({"pong":true}));
        controller.quit().unwrap();
        assert_eq!(std::fs::read(&source).unwrap(), wave);
    }
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
