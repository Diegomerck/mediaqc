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
    if args.get(1).is_some_and(|argument| {
        argument == "--inspect"
            || argument == "--jobs"
            || argument == "--audio"
            || argument == "--video"
    }) {
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
        if args[1] == "--video" {
            assert_eq!(inspected["streams"][0]["stream_type"], "video");
        } else {
            assert_eq!(inspected["streams"][0]["sample_rate_hz"], 48000);
        }
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
        if args[1] == "--jobs" || args[1] == "--audio" || args[1] == "--video" {
            let version = if args[1] == "--video" {
                "1.2.0"
            } else if args[1] == "--audio" {
                "1.1.0"
            } else {
                "1.0.0"
            };
            let started = controller.request("analysis.start".into(), serde_json::json!({"project_id":project["id"], "media_asset_id":inspected["media_asset_id"], "profile_key":"general_technical_qc", "profile_version":version, "ai_mode":"OFF"})).expect("start job");
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
            assert_eq!(failed["status"], "COMPLETED");
            assert!(
                failed["detector_states"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .all(|detector| {
                        let applicable = detector["detector_id"].as_str().unwrap().starts_with(
                            if args[1] == "--video" {
                                "video."
                            } else {
                                "audio."
                            },
                        );
                        detector["status"] == if applicable { "COMPLETED" } else { "SKIPPED" }
                    })
            );
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
            if args[1] == "--video" {
                assert_eq!(failed["overall_result"], "WARN");
                let listed = controller.request("finding.list".into(), serde_json::json!({"analysis_run_id":retry["analysis_run_id"],"detector_id":"video.black_frame"})).expect("list video findings");
                let issue = &listed["findings"][0];
                assert!((issue["start_time_seconds"].as_f64().unwrap() - 1.0).abs() <= 0.05);
                assert!((issue["end_time_seconds"].as_f64().unwrap() - 2.0).abs() <= 0.05);
                let detail = controller
                    .request(
                        "finding.get".into(),
                        serde_json::json!({"finding_id":issue["id"]}),
                    )
                    .unwrap();
                assert_eq!(detail["evidence"][0]["evidence_type"], "METRICS_JSON");
                let relative = detail["evidence"][0]["relative_path"].as_str().unwrap();
                assert!(relative.starts_with("evidence/video/"));
                assert!(PathBuf::from(&args[2]).join(relative).is_file());
                evidence_review(
                    &controller,
                    &detail,
                    &project,
                    &["VIDEO_FRAME_BEFORE", "VIDEO_FRAME", "VIDEO_FRAME_AFTER"],
                );
                assert!(
                    events
                        .lock()
                        .unwrap()
                        .iter()
                        .any(|event| event["event"] == "analysis.finding_created")
                );
                println!(
                    "PASS: Phase 5 packaged video detectors, timing, persistence/evidence, cancel/retry, restart"
                );
            }
            if args[1] == "--audio" {
                assert_eq!(failed["overall_result"], "FAIL");
                let listed = controller.request("finding.list".into(), serde_json::json!({"analysis_run_id":retry["analysis_run_id"],"detector_id":"audio.clipping"})).expect("list persisted audio findings");
                let issue = &listed["findings"][0];
                assert_eq!(issue["severity"], "FAIL");
                let detail = controller
                    .request(
                        "finding.get".into(),
                        serde_json::json!({"finding_id":issue["id"]}),
                    )
                    .expect("read audio evidence");
                assert_eq!(detail["measurements"]["clipped_sample_count"], 4800);
                assert_eq!(detail["evidence"][0]["evidence_type"], "METRICS_JSON");
                evidence_review(
                    &controller,
                    &detail,
                    &project,
                    &["AUDIO_WAVEFORM", "AUDIO_SPECTROGRAM"],
                );
                assert!(
                    events
                        .lock()
                        .unwrap()
                        .iter()
                        .any(|event| event["event"] == "analysis.finding_created")
                );
                println!(
                    "PASS: Phase 4 packaged audio detectors, FAIL aggregation, finding IPC, evidence, restart and legacy integration"
                );
            }
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
                "PASS: Phase 3 queued start, cancellation, events, retry, persisted history, production audio QC"
            );
        }
    }
    if std::env::args().any(|arg| arg == "--hold") {
        std::thread::sleep(Duration::from_secs(60));
    }
    println!("shutdown: {}", controller.quit().expect("clean shutdown"));
}

fn wait_run(controller: &Controller, id: &serde_json::Value) -> serde_json::Value {
    let deadline = Instant::now() + Duration::from_secs(30);
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

fn evidence_review(
    controller: &Controller,
    finding: &serde_json::Value,
    project: &serde_json::Value,
    kinds: &[&str],
) {
    for kind in kinds {
        let artifact = finding["evidence"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["evidence_type"] == *kind)
            .expect("visual evidence exists");
        let loaded = controller
            .request(
                "evidence.read".into(),
                serde_json::json!({"evidence_id": artifact["id"]}),
            )
            .expect("read bounded visual evidence");
        assert!(
            loaded["data_url"]
                .as_str()
                .unwrap()
                .starts_with("data:image/png;base64,")
        );
    }
    for disposition in ["CONFIRMED", "FALSE_POSITIVE", "IGNORED"] {
        let updated = controller.request("finding.set_disposition".into(), serde_json::json!({"finding_id":finding["id"], "disposition":disposition, "note":"Operator review é"})).unwrap();
        assert_eq!(updated["disposition"], disposition);
    }
    controller.stop().unwrap();
    controller.start().unwrap();
    controller
        .request(
            "project.open".into(),
            serde_json::json!({"project_file":project["project_file"]}),
        )
        .unwrap();
    let reopened = controller
        .request(
            "finding.get".into(),
            serde_json::json!({"finding_id":finding["id"]}),
        )
        .unwrap();
    assert_eq!(reopened["disposition"], "IGNORED");
    assert_eq!(
        reopened["feedback"].as_array().unwrap().last().unwrap()["note"],
        "Operator review é"
    );
    controller
        .request(
            "finding.set_disposition".into(),
            serde_json::json!({"finding_id":finding["id"], "disposition":"OPEN"}),
        )
        .unwrap();
    println!(
        "PASS: Phase 6 visual evidence read, dispositions and notes persisted across engine restart"
    );
}
