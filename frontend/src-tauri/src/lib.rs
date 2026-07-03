use std::net::TcpStream;
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

// 用户数据目录（日志、startup_error.txt 都在这里；spawn_gateway 也用到）
fn data_dir() -> Option<std::path::PathBuf> {
    Some(
        std::path::Path::new(&std::env::var("LOCALAPPDATA").ok()?)
            .join("PrismMotif"),
    )
}

// Windowless shell (release) has no console: console children would each pop a
// black window unless spawned with CREATE_NO_WINDOW.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

// The gateway child process, so we can kill it (and its MCP subprocess tree) on exit.
struct Gateway(Mutex<Option<Child>>);

// With no console the gateway's prints would vanish — keep them in a per-user log file.
fn gateway_log() -> Option<std::fs::File> {
    let dir = data_dir()?.join("logs");
    std::fs::create_dir_all(&dir).ok()?;
    std::fs::File::create(dir.join("gateway.log")).ok()
}

// Gateway 起不来（端口占用、python 缺失等）时会写这个文件；wait_port 失败后我们读它给用户看
fn startup_error_path() -> Option<std::path::PathBuf> {
    Some(data_dir()?.join("logs").join("startup_error.txt"))
}

fn clear_startup_error() {
    if let Some(p) = startup_error_path() {
        let _ = std::fs::remove_file(p);
    }
}

fn read_startup_error() -> Option<String> {
    let p = startup_error_path()?;
    std::fs::read_to_string(p).ok()
}

// data: URL 里除了 !$&'()*+,;=:@/?-._~A-Za-z0-9 都得 percent-encode。避免加依赖，手写这段。
fn urlencoding_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.as_bytes() {
        let c = *b as char;
        if c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.' | '~' | '/' | ':' | '?' | '=' | '&' | '+' | ' ') {
            out.push(c);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

// 定位 bundled resources 目录: exe 同级的 resources/。tauri build 时 bundle.resources
// 会把 python/、app/(=stage_pkg 输出)、mcps/ 全放这里。dev 模式下不存在,fallback 到 A:/。
fn bundled_root() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let root = exe.parent()?.join("resources");
    if root.join("python").join("python.exe").is_file() { Some(root) } else { None }
}

fn spawn_gateway(port: u16) -> Option<Child> {
    // 优先内置 CPython + 打包版代码;fallback 到 dev 硬编码路径(便于开发时直接跑)
    let (python, script, prism_home) = if let Some(root) = bundled_root() {
        let py = root.join("python").join("python.exe");
        let gw = root.join("app").join("gateway").join("server.py");
        // PRISM_HOME 指向 resources/,让 mcp_servers.json 里的 ${PRISM_HOME}/mcps/... 解析成
        // resources/mcps/... —— 也就是 tauri 把 3 个 mcps 放的位置
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
        .env("PRISM_HOME", &prism_home)
        // 打包版 DATA_ROOT 用 per-user %APPDATA%\PrismMotif;paths.py 里 sys.frozen 分支
        // 不适用(我们没冻 gateway),用显式环境变量指定
        .env("PRISM_DATA_DIR", data_dir().unwrap_or_else(|| prism_home.clone()))
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        .creation_flags(CREATE_NO_WINDOW);
    if let Some(log) = gateway_log() {
        if let Ok(log_err) = log.try_clone() {
            cmd.stdout(Stdio::from(log)).stderr(Stdio::from(log_err));
        }
    }
    cmd.spawn().ok()
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
        .creation_flags(CREATE_NO_WINDOW)
        .spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port: u16 = 8770;
    tauri::Builder::default()
        // 单实例：用户双击图标两次时，第二个进程把命令行 handoff 给第一个，然后自己退出。
        // 我们在 callback 里让已有窗口 unminimize + 前置，用户觉得"已经在跑了、给我拉到前面"。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(Gateway(Mutex::new(None)))
        .setup(move |app| {
            clear_startup_error();                    // 每次启动前清掉上一轮的错误档案
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
            // 端口没起来 → 看 gateway 有没有留下 startup_error.txt，有就用错误页替代主界面
            let gateway_ok = wait_port(port, Duration::from_secs(45));
            if !gateway_ok {
                let msg = read_startup_error()
                    .unwrap_or_else(|| "Gateway 未能在 45 秒内启动。请查看 %LOCALAPPDATA%/PrismMotif/logs/gateway.log。".to_string());
                let html = format!(
                    "<html><head><meta charset='utf-8'><title>Prism Motif</title>\
                     <style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;padding:40px;background:#eeecf7;color:#1c1b1f}}\
                     h1{{color:#6a4cd6;margin:0 0 16px}}pre{{background:#fff;border-radius:12px;padding:16px;white-space:pre-wrap}}</style></head>\
                     <body><h1>Prism Motif 启动失败</h1><pre>{}</pre>\
                     <p style='color:#615f6b'>日志:<code>%LOCALAPPDATA%\\PrismMotif\\logs\\gateway.log</code></p></body></html>",
                    msg.replace('<', "&lt;").replace('>', "&gt;")
                );
                let data_url = format!("data:text/html;charset=utf-8,{}",
                    urlencoding_encode(&html));
                WebviewWindowBuilder::new(app, "main", WebviewUrl::External(data_url.parse().unwrap()))
                    .title("Prism Motif — 启动失败")
                    .decorations(true)
                    .inner_size(720.0, 480.0)
                    .center()
                    .build()?;
                return Ok(());
            }
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
