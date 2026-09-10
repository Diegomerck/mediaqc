fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "engine_start",
            "engine_ping",
            "engine_stop",
            "engine_status",
        ]),
    ))
    .expect("failed to build Tauri resources and command permissions");
}
