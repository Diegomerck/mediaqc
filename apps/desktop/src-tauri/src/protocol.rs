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
                let _ = error.details;
                Err(Failure::new(&error.code, &error.message))
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

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "bd3ab941-a2e2-4303-a1a6-032c45d428a2";

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
