use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

// The gateway child process, so we can kill it (and its MCP subprocess tree) on exit.
struct Gateway(Mutex<Option<Child>>);

fn spawn_gateway(port: u16) -> Option<Child> {
    // DEV: system Python + the repo gateway. Packaging (P5b) will resolve a bundled
    // interpreter and the app-relative gateway path instead of these dev absolutes.
    Command::new("A:/Python310/python.exe")
        .arg("A:/Prismcode/prism-motif/gateway/server.py")
        .env("PRISM_PORT", port.to_string())
        .spawn()
        .ok()
}

fn wait_port(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

fn kill_tree(child: &mut Child) {
    let pid = child.id();
    let _ = child.kill();
    // the gateway spawns MCP subprocesses (perception / reaper) — kill the whole tree
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port: u16 = 8770;
    tauri::Builder::default()
        .manage(Gateway(Mutex::new(None)))
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            // start the Python gateway, wait until it's listening, then load the window on it
            let child = spawn_gateway(port);
            *app.state::<Gateway>().0.lock().unwrap() = child;
            wait_port(port, Duration::from_secs(45));
            // Size to ~82% of the primary monitor so it opens as a real workspace,
            // not a small floating window — adapts to whatever screen the user has.
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
            // Load the BUNDLED frontend (tauri:// origin) so window/drag APIs work;
            // the React app talks to the gateway (127.0.0.1:port) over CORS.
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
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
