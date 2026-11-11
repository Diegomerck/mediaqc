//! One actor owns the engine and its pipes. No child I/O blocks the UI thread.

use std::{
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use serde::Serialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::{
    ownership::{self, Ownership},
    protocol::{self, Message},
};

#[derive(Clone, Debug, Serialize)]
pub struct Failure {
    pub code: String,
    pub message: String,
    pub details: Value,
    #[serde(skip)]
    pub recoverable: bool,
}

impl Failure {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            details: json!({}),
            recoverable: false,
        }
    }
    fn io(error: std::io::Error) -> Self {
        Self::new("ENGINE_IO_ERROR", &error.to_string())
    }
}

#[derive(Clone, Serialize)]
pub struct Snapshot {
    pub phase: String,
    pub pid: Option<u32>,
    pub capabilities: Option<Value>,
    pub error: Option<Failure>,
    pub log_path: String,
    pub desktop_version: String,
}

#[derive(Clone)]
pub struct Config {
    pub executable: PathBuf,
    pub args: Vec<String>,
    pub log_path: PathBuf,
    pub timeout: Duration,
    pub shutdown_timeout: Duration,
}

impl Config {
    pub fn packaged(resources: PathBuf, logs: PathBuf) -> Self {
        #[cfg(windows)]
        let exe = "mediaqc-engine.exe";
        #[cfg(not(windows))]
        let exe = "mediaqc-engine";

        Self {
            executable: resources.join("resources/engine").join(exe),
            args: vec![
                "--state-directory".into(),
                logs.join("recovery").to_string_lossy().into_owned(),
            ],
            log_path: logs.join("engine.log"),
            timeout: Duration::from_secs(5),
            shutdown_timeout: Duration::from_secs(2),
        }
    }
}

enum Action {
    Start,
    Ping,
    Stop,
    Quit,
    Request { method: String, params: Value },
}
struct Call {
    action: Action,
    reply: mpsc::Sender<Result<Value, Failure>>,
}

#[derive(Clone)]
pub struct Controller {
    sender: mpsc::Sender<Call>,
    snapshot: Arc<Mutex<Snapshot>>,
    interrupt: Arc<AtomicBool>,
}

impl Controller {
    pub fn new(config: Config) -> Self {
        Self::with_events(config, Arc::new(|_| {}))
    }

    pub fn with_events(config: Config, events: EventSink) -> Self {
        let (sender, receiver) = mpsc::channel();
        let snapshot = Arc::new(Mutex::new(Snapshot {
            phase: "stopped".into(),
            pid: None,
            capabilities: None,
            error: None,
            log_path: config.log_path.to_string_lossy().into_owned(),
            desktop_version: env!("CARGO_PKG_VERSION").into(),
        }));
        let actor_snapshot = snapshot.clone();
        let interrupt = Arc::new(AtomicBool::new(false));
        let actor_interrupt = interrupt.clone();
        thread::spawn(move || run_actor(config, receiver, actor_snapshot, actor_interrupt, events));
        Self {
            sender,
            snapshot,
            interrupt,
        }
    }

    pub fn snapshot(&self) -> Snapshot {
        self.snapshot
            .lock()
            .expect("snapshot lock poisoned")
            .clone()
    }

    fn call(&self, action: Action) -> Result<Value, Failure> {
        if matches!(action, Action::Stop | Action::Quit) {
            self.interrupt.store(true, Ordering::SeqCst);
        }
        let (reply, receiver) = mpsc::channel();
        self.sender.send(Call { action, reply }).map_err(|_| {
            Failure::new(
                "ENGINE_CONTROLLER_STOPPED",
                "Desktop engine controller has stopped",
            )
        })?;
        receiver.recv().map_err(|_| {
            Failure::new(
                "ENGINE_CONTROLLER_STOPPED",
                "Desktop engine controller has stopped",
            )
        })?
    }

    pub fn start(&self) -> Result<Value, Failure> {
        self.call(Action::Start)
    }
    pub fn ping(&self) -> Result<Value, Failure> {
        self.call(Action::Ping)
    }
    pub fn stop(&self) -> Result<Value, Failure> {
        self.call(Action::Stop)
    }
    pub fn quit(&self) -> Result<Value, Failure> {
        self.call(Action::Quit)
    }

    pub fn request(&self, method: String, params: Value) -> Result<Value, Failure> {
        if !matches!(
            method.as_str(),
            "project.create"
                | "project.open"
                | "project.get"
                | "media.inspect"
                | "profile.list"
                | "profile.get"
                | "analysis.start"
                | "analysis.cancel"
                | "analysis.retry"
                | "analysis.get"
                | "analysis.list"
                | "batch.create"
                | "batch.list"
                | "batch.get"
                | "batch.items"
                | "batch.start"
                | "batch.pause"
                | "batch.resume"
                | "batch.stop"
                | "batch.retry"
                | "batch.report.generate"
                | "finding.list"
                | "finding.get"
                | "finding.set_disposition"
                | "evidence.read"
                | "report.generate"
                | "system.capabilities"
        ) || !params.is_object()
        {
            return Err(Failure::new(
                "INVALID_REQUEST",
                "Unsupported desktop request",
            ));
        }
        self.call(Action::Request { method, params })
    }
}

fn update(
    snapshot: &Mutex<Snapshot>,
    phase: &str,
    session: Option<&Session>,
    error: Option<Failure>,
) {
    let mut state = snapshot.lock().expect("snapshot lock poisoned");
    state.phase = phase.into();
    state.pid = session.map(|session| session.child.id());
    state.capabilities = session.map(|session| session.capabilities.clone());
    state.error = error;
}

fn run_actor(
    config: Config,
    receiver: mpsc::Receiver<Call>,
    snapshot: Arc<Mutex<Snapshot>>,
    interrupt: Arc<AtomicBool>,
    events: EventSink,
) {
    let mut session: Option<Session> = None;
    loop {
        match receiver.recv_timeout(Duration::from_millis(50)) {
            Ok(call) => {
                let quit = matches!(call.action, Action::Quit);
                let result = match call.action {
                    Action::Request { method, params } => match session.as_mut() {
                        Some(active) => active.request_params(
                            &method,
                            params,
                            Instant::now() + Duration::from_secs(35),
                        ),
                        None => Err(Failure::new(
                            "ENGINE_NOT_RUNNING",
                            "Start the local engine first",
                        )),
                    },
                    Action::Start => {
                        if let Some(active) = session.as_ref() {
                            Ok(active.capabilities.clone())
                        } else {
                            update(&snapshot, "starting", None, None);
                            interrupt.store(false, Ordering::SeqCst);
                            match Session::start(&config, interrupt.clone(), events.clone()) {
                                Ok(started) => {
                                    let capabilities = started.capabilities.clone();
                                    session = Some(started);
                                    update(&snapshot, "ready", session.as_ref(), None);
                                    Ok(capabilities)
                                }
                                Err(error) => Err(error),
                            }
                        }
                    }
                    Action::Ping => match session.as_mut() {
                        Some(active) => active
                            .request("system.ping", Instant::now() + config.timeout)
                            .and_then(|result| {
                                if result == json!({"pong":true}) {
                                    Ok(result)
                                } else {
                                    Err(Failure::new(
                                        "ENGINE_PROTOCOL_ERROR",
                                        "Engine returned an invalid ping result",
                                    ))
                                }
                            }),
                        None => Err(Failure::new(
                            "ENGINE_NOT_RUNNING",
                            "Start the local engine before sending a ping",
                        )),
                    },
                    Action::Stop | Action::Quit => {
                        update(&snapshot, "stopping", session.as_ref(), None);
                        let result = session
                            .take()
                            .map_or(Ok(json!({"forced":false})), |mut active| {
                                active.shutdown(&config)
                            });
                        update(&snapshot, "stopped", None, None);
                        result
                    }
                };
                if let Err(error) = &result
                    && !error.recoverable
                {
                    // Drop terminates and reaps a failed session before offering restart.
                    session.take();
                    update(&snapshot, "error", None, Some(error.clone()));
                }
                let _ = call.reply.send(result);
                if quit {
                    return;
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                if let Some(mut active) = session.take() {
                    let _ = active.shutdown(&config);
                }
                return;
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }
        if let Some(active) = session.as_mut()
            && let Err(error) = active.check_health()
        {
            session.take();
            update(&snapshot, "error", None, Some(error));
        }
    }
}

pub type EventSink = Arc<dyn Fn(Value) + Send + Sync>;

struct Session {
    events: EventSink,
    child: Child,
    stdin: Option<ChildStdin>,
    messages: Option<mpsc::Receiver<Result<Message, Failure>>>,
    readers: Vec<thread::JoinHandle<()>>,
    ownership: Option<Ownership>,
    capabilities: Value,
    interrupt: Arc<AtomicBool>,
}

impl Session {
    fn start(
        config: &Config,
        interrupt: Arc<AtomicBool>,
        events: EventSink,
    ) -> Result<Self, Failure> {
        let log = open_log(&config.log_path).map_err(Failure::io)?;
        let ownership = Ownership::new().map_err(Failure::io)?;
        let mut command = Command::new(&config.executable);
        command
            .args(&config.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        ownership::configure(&mut command);
        let mut child = command.spawn().map_err(|error| {
            Failure::new(
                "ENGINE_START_FAILED",
                &format!(
                    "Could not launch the bundled engine: {error}. Rebuild or reinstall MediaQC."
                ),
            )
        })?;
        if let Err(error) = ownership.attach(&child) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Failure::new("ENGINE_OWNERSHIP_FAILED", &error.to_string()));
        }
        let stdin = child.stdin.take();
        let stdout = child.stdout.take().expect("piped engine stdout");
        let stderr = child.stderr.take().expect("piped engine stderr");
        let (sender, messages) = mpsc::sync_channel(64);
        let stdout_reader = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let result = read_line(&mut reader).and_then(|line| protocol::parse(&line));
                let failed = result.is_err();
                if sender.send(result).is_err() || failed {
                    break;
                }
            }
        });
        let stderr_reader = thread::spawn(move || {
            let mut reader = BufReader::new(stderr);
            let mut log = log;
            let mut written = 0usize;
            // Always drain stderr; bound each chunk and the on-disk log for this session.
            let mut buffer = [0u8; 4096];
            while let Ok(count) = reader.read(&mut buffer) {
                if count == 0 {
                    break;
                }
                let keep = count.min((1024 * 1024usize).saturating_sub(written));
                if keep > 0 {
                    let _ = log.write_all(&buffer[..keep]);
                    written += keep;
                }
            }
        });
        let mut session = Self {
            events,
            interrupt,
            child,
            stdin,
            messages: Some(messages),
            readers: vec![stdout_reader, stderr_reader],
            ownership: Some(ownership),
            capabilities: Value::Null,
        };
        let startup_res = session.receive(Instant::now() + config.timeout);
        match startup_res {
            Ok(Message::Event { event, data, .. }) if event == "engine.ready" && data.is_empty() => {}
            Ok(_) => {
                return Err(Failure::new(
                    "ENGINE_PROTOCOL_ERROR",
                    "Expected engine.ready at startup",
                ));
            }
            Err(mut failure) => {
                thread::sleep(Duration::from_millis(100));
                if let Ok(content) = fs::read_to_string(&config.log_path) {
                    let trimmed = content.trim();
                    if !trimmed.is_empty() {
                        let lines: Vec<&str> = trimmed.lines().filter(|l| !l.trim().is_empty()).collect();
                        let summary = if let Some(pyi_idx) = lines.iter().rposition(|l| l.contains("Failed to execute script")) {
                            if pyi_idx > 0 {
                                let start = pyi_idx.saturating_sub(4);
                                lines[start..pyi_idx].join("\n")
                            } else {
                                lines[pyi_idx].to_string()
                            }
                        } else {
                            lines.last().copied().unwrap_or("").to_string()
                        };
                        failure.message = format!("{}:\n{}", failure.message, summary);
                        failure.details = json!({ "stderr": trimmed });
                    }
                }
                return Err(failure);
            }
        }
        session.capabilities =
            session.request("system.capabilities", Instant::now() + config.timeout)?;
        protocol::validate_capabilities(&session.capabilities)?;
        Ok(session)
    }

    fn receive(&self, deadline: Instant) -> Result<Message, Failure> {
        self.messages
            .as_ref()
            .expect("active stdout receiver")
            .recv_timeout(deadline.saturating_duration_since(Instant::now()))
            .map_err(|error| match error {
                mpsc::RecvTimeoutError::Timeout => Failure::new(
                    "ENGINE_TIMEOUT",
                    "Engine did not respond before the deadline; restart it",
                ),
                mpsc::RecvTimeoutError::Disconnected => Failure::new(
                    "ENGINE_EXITED",
                    "Engine closed its output unexpectedly; restart it",
                ),
            })?
    }

    fn request(&mut self, method: &str, deadline: Instant) -> Result<Value, Failure> {
        self.request_params(method, json!({}), deadline)
    }

    fn request_params(
        &mut self,
        method: &str,
        params: Value,
        deadline: Instant,
    ) -> Result<Value, Failure> {
        let id = Uuid::new_v4().to_string();
        let mut request = protocol::request(method, &id);
        request["params"] = params;
        let mut bytes = serde_json::to_vec(&request).expect("serializable request");
        bytes.push(b'\n');
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| Failure::new("ENGINE_EXITED", "Engine input is closed"))?;
        stdin
            .write_all(&bytes)
            .and_then(|()| stdin.flush())
            .map_err(Failure::io)?;
        loop {
            if method == "media.inspect" && self.interrupt.load(Ordering::SeqCst) {
                return self.interrupt_inspection();
            }
            let tick = (Instant::now() + Duration::from_millis(50)).min(deadline);
            match self.receive(tick) {
                Err(error) if error.code == "ENGINE_TIMEOUT" && Instant::now() < deadline => {
                    continue;
                }
                Ok(message @ Message::Event { .. }) => self.event(message)?,
                result => return protocol::response(result?, &id),
            }
        }
    }

    fn interrupt_inspection(&mut self) -> Result<Value, Failure> {
        let id = Uuid::new_v4().to_string();
        let mut bytes = serde_json::to_vec(&protocol::request("system.shutdown", &id))
            .expect("shutdown request");
        bytes.push(b'\n');
        if let Some(input) = self.stdin.as_mut() {
            let _ = input.write_all(&bytes);
            let _ = input.flush();
        }
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            match self.receive(deadline) {
                Ok(Message::Response { request_id, .. }) if request_id == id => break,
                Ok(_) => continue,
                Err(_) => break,
            }
        }
        self.stdin.take();
        while Instant::now() < deadline {
            if self.child.try_wait().map_err(Failure::io)?.is_some() {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        Err(Failure::new(
            "ENGINE_INSPECTION_INTERRUPTED",
            "Inspection stopped because the engine is shutting down",
        ))
    }

    fn check_health(&mut self) -> Result<(), Failure> {
        if let Some(status) = self.child.try_wait().map_err(Failure::io)? {
            return Err(Failure::new(
                "ENGINE_EXITED",
                &format!("Engine exited unexpectedly ({status}); restart it"),
            ));
        }
        match self
            .messages
            .as_ref()
            .expect("active stdout receiver")
            .try_recv()
        {
            Err(mpsc::TryRecvError::Empty) => Ok(()),
            Ok(Ok(message @ Message::Event { .. })) => self.event(message),
            Ok(Err(error)) => Err(error),
            _ => Err(Failure::new(
                "ENGINE_PROTOCOL_ERROR",
                "Unexpected unsolicited engine output; restart it",
            )),
        }
    }

    fn event(&self, message: Message) -> Result<(), Failure> {
        let value = protocol::runtime_event(message)?;
        (self.events)(value);
        Ok(())
    }

    fn shutdown(&mut self, config: &Config) -> Result<Value, Failure> {
        let deadline = Instant::now() + config.shutdown_timeout;
        let acknowledged = self.request("system.shutdown", deadline).is_ok();
        self.stdin.take();
        while Instant::now() < deadline {
            if let Some(status) = self.child.try_wait().map_err(Failure::io)? {
                if !status.success() {
                    return Err(Failure::new(
                        "ENGINE_SHUTDOWN_FAILED",
                        &format!("Engine exited during shutdown with {status}"),
                    ));
                }
                return Ok(json!({"forced":!acknowledged}));
            }
            thread::sleep(Duration::from_millis(10));
        }
        self.child.kill().map_err(Failure::io)?;
        self.child.wait().map_err(Failure::io)?;
        Ok(json!({"forced":true}))
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.stdin.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
        self.ownership.take();
        self.messages.take();
        for reader in self.readers.drain(..) {
            let _ = reader.join();
        }
    }
}

fn open_log(path: &PathBuf) -> std::io::Result<File> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    if path.exists() {
        fs::rename(path, path.with_extension("previous.log"))?;
    }
    OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(path)
}

fn read_line(reader: &mut impl BufRead) -> Result<Vec<u8>, Failure> {
    let mut line = Vec::new();
    reader
        .take(protocol::MAX_LINE_BYTES + 1)
        .read_until(b'\n', &mut line)
        .map_err(Failure::io)?;
    if line.is_empty() {
        return Err(Failure::new(
            "ENGINE_EXITED",
            "Engine closed stdout unexpectedly; restart it",
        ));
    }
    if line.len() as u64 > protocol::MAX_LINE_BYTES || !line.ends_with(b"\n") {
        return Err(Failure::new(
            "ENGINE_PROTOCOL_ERROR",
            "Engine output is oversized or lacks a newline terminator",
        ));
    }
    Ok(line)
}
