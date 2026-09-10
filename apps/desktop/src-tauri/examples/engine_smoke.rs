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
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).is_some_and(|argument| argument == "--inspect") {
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
    }
    if std::env::args().any(|arg| arg == "--hold") {
        std::thread::sleep(Duration::from_secs(60));
    }
    println!("shutdown: {}", controller.quit().expect("clean shutdown"));
}
