//! Developer-only smoke harness using the production process controller.
use mediaqc_desktop::engine::{Config, Controller};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let events = Arc::new(Mutex::new(Vec::new()));
    let sink = events.clone();
    let controller = Controller::with_events(
        Config::packaged(
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/release"),
            root.join(".cache/native-smoke"),
        ),
        Arc::new(move |event| {
            sink.lock().unwrap().push(event);
        }),
    );
    println!(
        "capabilities: {}",
        controller.start().expect("engine startup")
    );
    println!("ping: {}", controller.ping().expect("system.ping"));
    println!("pid: {}", controller.snapshot().pid.expect("engine pid"));
    let args: Vec<String> = std::env::args().collect();
    if args
        .get(1)
        .is_some_and(|argument| argument == "--inspect" || argument == "--jobs")
    {
        let project = controller
            .request(
                "project.create".into(),
                serde_json::json!({"directory": args[2], "name":"Packaged Phase 2"}),
            )
            .expect("project create");
        let inspected = controller
            .request(
                "media.inspect".into(),
                serde_json::json!({"project_id":project["id"], "absolute_path":args[3]}),
            )
            .expect("media inspect");
        assert_eq!(inspected["inspection_status"], "COMPLETED");
        assert_eq!(inspected["streams"][0]["sample_rate_hz"], 48000);
        controller.stop().expect("stop before reopen");
        controller.start().expect("restart engine");
        let reopened = controller
            .request(
                "project.open".into(),
                serde_json::json!({"project_file":project["project_file"]}),
            )
            .expect("project reopen");
        assert_eq!(
            reopened["media_assets"][0]["id"],
            inspected["media_asset_id"]
        );
        let failed = controller.request("media.inspect".into(), serde_json::json!({"project_id":project["id"], "absolute_path":format!("{}.missing", args[3])})).expect_err("missing media error");
        assert_eq!(failed.code, "MEDIA_NOT_FOUND");
        assert_eq!(
            controller.ping().expect("engine survives bad media"),
            serde_json::json!({"pong":true})
        );
        println!("PASS: Phase 2 inspect, restart, reopen, missing media, ping");
        if args[1] == "--jobs" {
            let started = controller.request("analysis.start".into(), serde_json::json!({"project_id":project["id"], "media_asset_id":inspected["media_asset_id"], "profile_key":"general_technical_qc", "profile_version":"1.0.0", "ai_mode":"OFF"})).expect("start job");
            assert_eq!(started["status"], "QUEUED");
            let id = &started["analysis_run_id"];
            controller
                .request(
                    "analysis.cancel".into(),
                    serde_json::json!({"analysis_run_id":id}),
                )
                .expect("cancel job");
            let cancelled = wait_run(&controller, id);
            assert_eq!(cancelled["status"], "CANCELLED");
            assert_eq!(controller.ping().unwrap(), serde_json::json!({"pong":true}));
            let retry = controller
                .request(
                    "analysis.retry".into(),
                    serde_json::json!({"analysis_run_id":id}),
                )
                .expect("retry job");
            assert_ne!(retry["analysis_run_id"], *id);
            let failed = wait_run(&controller, &retry["analysis_run_id"]);
            assert_eq!(failed["status"], "FAILED");
            assert_eq!(failed["error_code"], "RUN_START_FAILED");
            assert_eq!(
                failed["qc_profile_snapshot_json"],
                cancelled["qc_profile_snapshot_json"]
            );
            controller.stop().unwrap();
            controller.start().unwrap();
            let saved = controller
                .request(
                    "project.open".into(),
                    serde_json::json!({"project_file":project["project_file"]}),
                )
                .unwrap();
            assert_eq!(saved["analysis_runs"].as_array().unwrap().len(), 2);
            assert!(
                events
                    .lock()
                    .unwrap()
                    .iter()
                    .any(|event| event["event"] == "analysis.cancelled")
            );
            assert!(
                events
                    .lock()
                    .unwrap()
                    .iter()
                    .any(|event| event["event"] == "analysis.progress")
            );
            println!(
                "PASS: Phase 3 queued start, cancellation, events, retry, persisted history, no false QC pass"
            );
        }
    }
    if std::env::args().any(|arg| arg == "--hold") {
        std::thread::sleep(Duration::from_secs(60));
    }
    println!("shutdown: {}", controller.quit().expect("clean shutdown"));
}

fn wait_run(controller: &Controller, id: &serde_json::Value) -> serde_json::Value {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        let result = controller
            .request(
                "analysis.get".into(),
                serde_json::json!({"analysis_run_id":id}),
            )
            .unwrap();
        if matches!(
            result["status"].as_str(),
            Some("COMPLETED" | "FAILED" | "CANCELLED")
        ) {
            return result;
        }
        assert!(
            Instant::now() < deadline,
            "job did not reach terminal state"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
}
