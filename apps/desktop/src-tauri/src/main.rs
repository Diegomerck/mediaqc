#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use mediaqc_desktop::engine::{Config, Controller, Failure, Snapshot};
use serde_json::Value;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use tauri::{Emitter, Manager, State};

async fn dispatch(
    controller: Controller,
    action: fn(&Controller) -> Result<Value, Failure>,
) -> Result<Value, Failure> {
    tauri::async_runtime::spawn_blocking(move || action(&controller))
        .await
        .map_err(|error| Failure::new("ENGINE_CONTROLLER_ERROR", &error.to_string()))?
}

#[tauri::command]
async fn engine_start(controller: State<'_, Controller>) -> Result<Value, Failure> {
    dispatch(controller.inner().clone(), Controller::start).await
}

#[tauri::command]
async fn engine_ping(controller: State<'_, Controller>) -> Result<Value, Failure> {
    dispatch(controller.inner().clone(), Controller::ping).await
}

#[tauri::command]
async fn engine_stop(controller: State<'_, Controller>) -> Result<Value, Failure> {
    dispatch(controller.inner().clone(), Controller::stop).await
}

#[tauri::command]
fn engine_status(controller: State<'_, Controller>) -> Snapshot {
    controller.snapshot()
}

#[tauri::command]
async fn engine_request(
    controller: State<'_, Controller>,
    method: String,
    params: Value,
) -> Result<Value, Failure> {
    let controller = controller.inner().clone();
    tauri::async_runtime::spawn_blocking(move || controller.request(method, params))
        .await
        .map_err(|error| Failure::new("ENGINE_CONTROLLER_ERROR", &error.to_string()))?
}

#[tauri::command]
async fn pick_path(kind: String) -> Result<Option<String>, Failure> {
    tauri::async_runtime::spawn_blocking(move || {
        let dialog = rfd::FileDialog::new();
        let selected = match kind.as_str() {
            "directory" => dialog
                .set_title("Choose an empty project directory")
                .pick_folder(),
            "project" => dialog
                .add_filter("MediaQC project", &["sqlite"])
                .pick_file(),
            "media" => dialog.set_title("Select local source media").pick_file(),
            "media_directory" => dialog.set_title("Select source media folder").pick_folder(),
            _ => return Err(Failure::new("INVALID_REQUEST", "Unknown file picker kind")),
        };
        Ok(selected.map(|path| path.to_string_lossy().into_owned()))
    })
    .await
    .map_err(|error| Failure::new("DESKTOP_DIALOG_FAILED", &error.to_string()))?
}

fn main() {
    let exiting = Arc::new(AtomicBool::new(false));
    let app = tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            let controller = Controller::with_events(
                Config::packaged(app.path().resource_dir()?, app.path().app_log_dir()?),
                Arc::new(move |event| {
                    let _ = handle.emit("engine-event", event);
                }),
            );
            app.manage(controller);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine_start,
            engine_ping,
            engine_stop,
            engine_status,
            engine_request,
            pick_path
        ])
        .build(tauri::generate_context!())
        .expect("failed to build the MediaQC desktop shell");
    app.run(move |app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event
            && !exiting.swap(true, Ordering::SeqCst)
        {
            api.prevent_exit();
            let controller = app.state::<Controller>().inner().clone();
            let app = app.clone();
            std::thread::spawn(move || {
                let _ = controller.quit();
                app.exit(0);
            });
        }
    });
}
