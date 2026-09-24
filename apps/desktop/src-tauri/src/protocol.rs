//! The engine wire format is defined by specs/06_IPC_SPEC.md.

use serde::Deserialize;
use serde_json::{Value, json};

use crate::engine::Failure;

pub const VERSION: &str = "1.0";
pub const MAX_LINE_BYTES: u64 = 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", deny_unknown_fields)]
pub enum Message {
    #[serde(rename = "event")]
    Event {
        protocol_version: String,
        event: String,
        data: serde_json::Map<String, Value>,
    },
    #[serde(rename = "response")]
    Response {
        protocol_version: String,
        request_id: String,
        ok: bool,
        result: Option<serde_json::Map<String, Value>>,
        error: Option<WireError>,
    },
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireError {
    pub code: String,
    pub message: String,
    pub details: serde_json::Map<String, Value>,
}

pub fn parse(bytes: &[u8]) -> Result<Message, Failure> {
    let message: Message = serde_json::from_slice(bytes).map_err(|_| {
        Failure::new(
            "ENGINE_PROTOCOL_ERROR",
            "Engine returned an invalid envelope",
        )
    })?;
    // Option<T> alone treats explicit null like an absent field. The wire contract
    // requires exactly one of result/error, so also check the response's field set.
    if matches!(&message, Message::Response { .. }) {
        let raw: Value = serde_json::from_slice(bytes).expect("already parsed JSON");
        if raw.as_object().is_none_or(|object| object.len() != 5) {
            return Err(Failure::new(
                "ENGINE_PROTOCOL_ERROR",
                "Response must contain exactly one of result or error",
            ));
        }
    }
    let version = match &message {
        Message::Event {
            protocol_version, ..
        }
        | Message::Response {
            protocol_version, ..
        } => protocol_version,
    };
    if version != VERSION {
        return Err(Failure::new(
            "PROTOCOL_VERSION_UNSUPPORTED",
            "Engine protocol is incompatible; reinstall matching components",
        ));
    }
    Ok(message)
}

pub fn request(method: &str, id: &str) -> Value {
    json!({"type":"request", "protocol_version": VERSION, "request_id": id, "method":method, "params":{}})
}

pub fn response(message: Message, id: &str) -> Result<Value, Failure> {
    if let Message::Response {
        request_id,
        ok,
        result,
        error,
        ..
    } = message
        && request_id == id
    {
        return match (ok, result, error) {
            (true, Some(result), None) => Ok(Value::Object(result)),
            (false, None, Some(error)) => {
                let mut failure = Failure::new(&error.code, &error.message);
                failure.details = Value::Object(error.details);
                failure.recoverable = true;
                Err(failure)
            }
            _ => Err(Failure::new(
                "ENGINE_PROTOCOL_ERROR",
                "Engine returned an inconsistent response",
            )),
        };
    }
    Err(Failure::new(
        "ENGINE_PROTOCOL_ERROR",
        "Unexpected engine message or request ID",
    ))
}

pub fn validate_capabilities(value: &Value) -> Result<(), Failure> {
    if value["protocol_version"] != VERSION {
        return Err(Failure::new(
            "PROTOCOL_VERSION_UNSUPPORTED",
            "Engine capabilities report an incompatible protocol",
        ));
    }
    let tool_valid = |name: &str| {
        value[name]["available"].is_boolean()
            && (value[name]["version"].is_string()
                || value[name].get("version") == Some(&Value::Null))
    };
    if !value["engine_version"].is_string()
        || !value["schema_version"].is_u64()
        || !value["platform"].is_string()
        || !value["detectors"].is_array()
        || !tool_valid("ffmpeg")
        || !tool_valid("ffprobe")
        || !value["ai"]["local_available"].is_boolean()
        || !(value["ai"]["provider"].is_string()
            || value["ai"].get("provider") == Some(&Value::Null))
    {
        return Err(Failure::new(
            "ENGINE_PROTOCOL_ERROR",
            "Engine capabilities are incomplete",
        ));
    }
    Ok(())
}

pub fn runtime_event(message: Message) -> Result<Value, Failure> {
    if let Message::Event { event, data, .. } = message {
        // Batch queue entries exist before an analysis run is created. Validate
        // their own correlation/order fields, not a required analysis_run_id.
        if event.starts_with("batch.") {
            let uuid_field = |field: &str| {
                data.get(field)
                    .and_then(Value::as_str)
                    .is_some_and(|id| uuid::Uuid::parse_str(id).is_ok())
            };
            let known = matches!(
                event.as_str(),
                "batch.discovery"
                    | "batch.status"
                    | "batch.item_changed"
                    | "batch.progress"
                    | "batch.completed"
                    | "batch.stopped"
                    | "batch.failed"
                    | "batch.interrupted"
            );
            let ordered = data.get("revision").is_some_and(Value::is_u64)
                && data.get("sequence").is_some_and(Value::is_u64);
            let item_valid = event != "batch.item_changed"
                || (uuid_field("item_id")
                    && (data.get("analysis_run_id") == Some(&Value::Null)
                        || uuid_field("analysis_run_id")));
            let progress_valid = event != "batch.progress"
                || data
                    .get("overall_progress")
                    .and_then(Value::as_f64)
                    .is_some_and(|p| (0.0..=1.0).contains(&p));
            if known
                && uuid_field("batch_id")
                && uuid_field("engine_session_id")
                && ordered
                && item_valid
                && progress_valid
            {
                return Ok(
                    json!({"type":"event", "protocol_version":VERSION, "event":event, "data":data}),
                );
            }
            return Err(Failure::new("ENGINE_PROTOCOL_ERROR", "Invalid batch event"));
        }
        let identifier = data.get("analysis_run_id").and_then(Value::as_str);
        let valid_id = identifier.is_some_and(|id| uuid::Uuid::parse_str(id).is_ok());
        let known = matches!(
            event.as_str(),
            "analysis.status"
                | "analysis.progress"
                | "analysis.detector_status"
                | "analysis.finding_created"
                | "analysis.completed"
                | "analysis.failed"
                | "analysis.cancelled"
        );
        let progress_valid = event != "analysis.progress"
            || data
                .get("overall_progress")
                .and_then(Value::as_f64)
                .is_some_and(|p| (0.0..=1.0).contains(&p));
        if valid_id && known && progress_valid {
            return Ok(
                json!({"type":"event", "protocol_version":VERSION, "event":event, "data":data}),
            );
        }
    }
    Err(Failure::new(
        "ENGINE_PROTOCOL_ERROR",
        "Invalid analysis event",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "bd3ab941-a2e2-4303-a1a6-032c45d428a2";

    fn batch_wire(name: &str) -> Value {
        json!({"type":"event", "protocol_version":VERSION, "event":name,
            "data":{"batch_id":ID,"engine_session_id":ID,"revision":1,"sequence":2,
                "item_id":ID,"analysis_run_id":null,"overall_progress":0.5}})
    }

    #[test]
    fn documented_batch_events_reach_desktop_unchanged() {
        for name in [
            "batch.discovery",
            "batch.status",
            "batch.item_changed",
            "batch.progress",
            "batch.completed",
            "batch.stopped",
            "batch.failed",
            "batch.interrupted",
        ] {
            let wire = batch_wire(name);
            assert_eq!(
                runtime_event(parse(wire.to_string().as_bytes()).unwrap()).unwrap(),
                wire
            );
        }
    }

    #[test]
    fn invalid_batch_events_are_rejected() {
        for (name, field, value) in [
            ("batch.unknown", "revision", json!(1)),
            ("batch.status", "batch_id", json!("invalid")),
            ("batch.status", "engine_session_id", Value::Null),
            ("batch.status", "revision", json!(-1)),
            ("batch.status", "sequence", json!("2")),
            ("batch.progress", "overall_progress", json!(1.1)),
            ("batch.item_changed", "item_id", Value::Null),
            ("batch.item_changed", "analysis_run_id", json!("invalid")),
        ] {
            let mut wire = batch_wire(name);
            wire["data"][field] = value;
            assert!(
                runtime_event(parse(wire.to_string().as_bytes()).unwrap()).is_err(),
                "{wire}"
            );
        }
        for field in [
            "batch_id",
            "revision",
            "engine_session_id",
            "sequence",
            "item_id",
            "analysis_run_id",
        ] {
            let mut wire = batch_wire("batch.item_changed");
            wire["data"].as_object_mut().unwrap().remove(field);
            assert!(
                runtime_event(parse(wire.to_string().as_bytes()).unwrap()).is_err(),
                "{field}"
            );
        }
        let mut wire = batch_wire("batch.item_changed");
        wire["data"]["analysis_run_id"] = json!(ID);
        assert!(runtime_event(parse(wire.to_string().as_bytes()).unwrap()).is_ok());
    }

    #[test]
    fn audio_finding_event_reaches_desktop() {
        let wire = json!({"type":"event", "protocol_version":VERSION,
            "event":"analysis.finding_created", "data":{"analysis_run_id":ID,
            "id":ID,"detector_id":"audio.clipping","severity":"FAIL",
            "title":"Clipping evidence","start_time_seconds":1.0,"end_time_seconds":1.1}});
        let event = runtime_event(parse(wire.to_string().as_bytes()).unwrap()).unwrap();
        assert_eq!(event["data"]["detector_id"], "audio.clipping");
        assert_eq!(event["data"]["severity"], "FAIL");
    }

    #[test]
    fn exact_request_and_success_envelopes() {
        assert_eq!(
            request("system.ping", ID),
            json!({"type":"request", "protocol_version":"1.0", "request_id":ID, "method":"system.ping", "params":{}})
        );
        let wire = json!({"type":"response", "protocol_version":"1.0", "request_id":ID, "ok":true, "result":{"pong":true}});
        assert_eq!(
            response(parse(wire.to_string().as_bytes()).unwrap(), ID).unwrap(),
            json!({"pong":true})
        );
    }

    #[test]
    fn structured_errors_preserve_code_and_message() {
        let wire = json!({"type":"response", "protocol_version":"1.0", "request_id":ID, "ok":false,
            "error":{"code":"METHOD_NOT_FOUND", "message":"Not implemented", "details":{}}});
        let failure = response(parse(wire.to_string().as_bytes()).unwrap(), ID).unwrap_err();
        assert_eq!(failure.code, "METHOD_NOT_FOUND");
        assert_eq!(failure.message, "Not implemented");
    }

    #[test]
    fn inconsistent_responses_and_uncorrelated_events_are_rejected() {
        for extra in [
            json!({"ok":true,"result":{},"error":null}),
            json!({"ok":true,"error":{"code":"X","message":"X","details":{}}}),
            json!({"ok":false,"result":{}}),
        ] {
            let mut wire = json!({"type":"response","protocol_version":"1.0","request_id":ID});
            wire.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            assert!(
                parse(wire.to_string().as_bytes())
                    .and_then(|message| response(message, ID))
                    .is_err()
            );
        }
        let event =
            br#"{"type":"event","protocol_version":"1.0","event":"engine.ready","data":{}}"#;
        assert!(response(parse(event).unwrap(), ID).is_err());
        assert!(parse(br#"{"type":"event","protocol_version":"1.0","event":"engine.ready","data":{},"request_id":"extra"}"#).is_err());
    }
}
