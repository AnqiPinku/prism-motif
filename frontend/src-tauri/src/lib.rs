use serde::Serialize;
use serde_json::Value;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, State, WebviewUrl, WebviewWindowBuilder};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const GATEWAY_PROTOCOL: u64 = 2;

struct Gateway(Mutex<Option<Child>>);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct GatewaySession {
    base_url: String,
    token: String,
    instance_id: String,
}

#[tauri::command]
fn gateway_session(state: State<'_, GatewaySession>) -> GatewaySession {
    state.inner().clone()
}

fn data_dir() -> Option<std::path::PathBuf> {
    Some(
        std::path::Path::new(&std::env::var("LOCALAPPDATA").ok()?)
            .join("PrismMotif"),
    )
}

fn gateway_log() -> Option<std::fs::File> {
    let dir = data_dir()?.join("logs");
    std::fs::create_dir_all(&dir).ok()?;
    std::fs::File::create(dir.join("gateway.log")).ok()
}

fn startup_error_path() -> Option<std::path::PathBuf> {
    Some(data_dir()?.join("logs").join("startup_error.txt"))
}

fn clear_startup_error() {
    if let Some(p) = startup_error_path() {
        let _ = std::fs::remove_file(p);
    }
}

fn read_startup_error() -> Option<String> {
    std::fs::read_to_string(startup_error_path()?).ok()
}

fn random_hex(bytes: usize) -> Option<String> {
    let mut data = vec![0_u8; bytes];
    getrandom::getrandom(&mut data).ok()?;
    let mut out = String::with_capacity(bytes * 2);
    for byte in data {
        out.push_str(&format!("{byte:02x}"));
    }
    Some(out)
}

fn allocate_loopback_port() -> Option<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).ok()?;
    listener.local_addr().ok().map(|addr| addr.port())
}

fn new_gateway_session() -> Option<(u16, GatewaySession)> {
    let port = allocate_loopback_port()?;
    let token = random_hex(32)?;
    let instance_id = random_hex(16)?;
    Some((
        port,
        GatewaySession {
            base_url: format!("http://127.0.0.1:{port}"),
            token,
            instance_id,
        },
    ))
}

fn urlencoding_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.as_bytes() {
        let c = *b as char;
        if c.is_ascii_alphanumeric()
            || matches!(c, '-' | '_' | '.' | '~' | '/' | ':' | '?' | '=' | '&' | '+' | ' ')
        {
            out.push(c);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

fn bundled_root() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let root = exe.parent()?.join("resources");
    if root.join("python").join("python.exe").is_file() {
        Some(root)
    } else {
        None
    }
}

fn spawn_gateway(port: u16, session: &GatewaySession) -> Option<Child> {
    let bundled = bundled_root();
    let (python, script, prism_home) = if let Some(ref root) = bundled {
        let py = root.join("python").join("python.exe");
        let gw = root.join("app").join("gateway").join("server.py");
        (py, gw, root.clone())
    } else {
        (
            std::path::PathBuf::from("A:/Python310/python.exe"),
            std::path::PathBuf::from("A:/Prismcode/prism-motif/gateway/server.py"),
            std::path::PathBuf::from("A:/Prismcode"),
        )
    };
    let mut cmd = Command::new(&python);
    cmd.arg(&script)
        .env("PRISM_PORT", port.to_string())
        .env("PRISM_SESSION_TOKEN", &session.token)
        .env("PRISM_INSTANCE_ID", &session.instance_id)
        .env("PRISM_HOME", &prism_home)
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        .creation_flags(CREATE_NO_WINDOW);
    if bundled.is_some() {
        if let Some(dd) = data_dir() {
            cmd.env("PRISM_DATA_DIR", dd);
        }
    }
    if let Some(log) = gateway_log() {
        if let Ok(log_err) = log.try_clone() {
            cmd.stdout(Stdio::from(log)).stderr(Stdio::from(log_err));
        }
    }
    cmd.spawn().ok()
}

fn health_response_matches(response: &str, expected_instance: &str) -> bool {
    let (head, body) = match response.split_once("\r\n\r\n") {
        Some(parts) => parts,
        None => return false,
    };
    if !(head.starts_with("HTTP/1.0 200") || head.starts_with("HTTP/1.1 200")) {
        return false;
    }
    let payload: Value = match serde_json::from_str(body) {
        Ok(value) => value,
        Err(_) => return false,
    };
    payload.get("product").and_then(Value::as_str) == Some("prism-motif")
        && payload.get("protocol").and_then(Value::as_u64) == Some(GATEWAY_PROTOCOL)
        && payload.get("instance_id").and_then(Value::as_str) == Some(expected_instance)
        && payload.get("ready").and_then(Value::as_bool) == Some(true)
}

fn probe_gateway(port: u16, session: &GatewaySession) -> bool {
    let mut stream = match TcpStream::connect(("127.0.0.1", port)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let timeout = Some(Duration::from_millis(750));
    let _ = stream.set_read_timeout(timeout);
    let _ = stream.set_write_timeout(timeout);
    let request = format!(
        "GET /health HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nX-Prism-Session: {}\r\nConnection: close\r\n\r\n",
        session.token
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    health_response_matches(&response, &session.instance_id)
}

fn wait_gateway(port: u16, session: &GatewaySession, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if probe_gateway(port, session) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

fn kill_tree(child: &mut Child) {
    let pid = child.id();
    let _ = child.kill();
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let (port, session) = new_gateway_session()
        .expect("failed to create a secure local gateway session");
    let setup_session = session.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(Gateway(Mutex::new(None)))
        .manage(session)
        .invoke_handler(tauri::generate_handler![gateway_session])
        .setup(move |app| {
            clear_startup_error();
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            let child = spawn_gateway(port, &setup_session);
            *app.state::<Gateway>().0.lock().unwrap() = child;
            let gateway_ok = wait_gateway(port, &setup_session, Duration::from_secs(45));
            if !gateway_ok {
                let msg = read_startup_error().unwrap_or_else(|| {
                    "Gateway 未能在 45 秒内通过身份验证。请查看 %LOCALAPPDATA%/PrismMotif/logs/gateway.log。"
                        .to_string()
                });
                let html = format!(
                    "<html><head><meta charset='utf-8'><title>Prism Motif</title>\
                     <style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;padding:40px;background:#eeecf7;color:#1c1b1f}}\
                     h1{{color:#6a4cd6;margin:0 0 16px}}pre{{background:#fff;border-radius:12px;padding:16px;white-space:pre-wrap}}</style></head>\
                     <body><h1>Prism Motif 启动失败</h1><pre>{}</pre>\
                     <p style='color:#615f6b'>日志:<code>%LOCALAPPDATA%\\PrismMotif\\logs\\gateway.log</code></p></body></html>",
                    msg.replace('<', "&lt;").replace('>', "&gt;")
                );
                let data_url = format!(
                    "data:text/html;charset=utf-8,{}",
                    urlencoding_encode(&html)
                );
                WebviewWindowBuilder::new(
                    app,
                    "main",
                    WebviewUrl::External(data_url.parse().unwrap()),
                )
                .title("Prism Motif — 启动失败")
                .decorations(true)
                .inner_size(720.0, 480.0)
                .center()
                .build()?;
                return Ok(());
            }
            let (win_w, win_h) = app
                .handle()
                .primary_monitor()
                .ok()
                .flatten()
                .map(|m| {
                    let sf = m.scale_factor();
                    let lw = m.size().width as f64 / sf;
                    let lh = m.size().height as f64 / sf;
                    ((lw * 0.82).max(1120.0), (lh * 0.86).max(720.0))
                })
                .unwrap_or((1360.0, 880.0));
            let main_window =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()));
            #[cfg(debug_assertions)]
            let main_window = match std::env::var("PRISM_WEBVIEW_BROWSER_ARGS") {
                Ok(browser_args) if !browser_args.trim().is_empty() => {
                    main_window.additional_browser_args(&browser_args)
                }
                _ => main_window,
            };
            main_window
                .title("Prism Motif")
                .decorations(false)
                .inner_size(win_w, win_h)
                .min_inner_size(960.0, 640.0)
                .center()
                .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(mut child) = window.state::<Gateway>().0.lock().unwrap().take() {
                    kill_tree(&mut child);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secure_random_values_have_expected_length() {
        let a = random_hex(32).unwrap();
        let b = random_hex(32).unwrap();
        assert_eq!(a.len(), 64);
        assert_eq!(b.len(), 64);
        assert_ne!(a, b);
    }

    #[test]
    fn loopback_port_is_dynamic_and_nonzero() {
        let port = allocate_loopback_port().unwrap();
        assert_ne!(port, 0);
    }

    #[test]
    fn health_response_requires_matching_identity() {
        let response = concat!(
            "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n",
            "{\"product\":\"prism-motif\",\"protocol\":2,",
            "\"instance_id\":\"instance-a\",\"ready\":true}"
        );
        assert!(health_response_matches(response, "instance-a"));
        assert!(!health_response_matches(response, "instance-b"));
    }
}
