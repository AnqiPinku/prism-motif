fn main() {
    tauri_build::build();
    // Workaround: 部分环境下 (vswhere.exe 缺失) embed-resource 无法定位 cvtres.exe,
    // 会把 rc.exe 输出的 raw .res 直接命名 .lib 而没做 COFF 转换 → link.exe 不识别,
    // 图标资源静默丢失、exe 里 GROUP_ICON=0。检测到这种情况就自己跑 cvtres 修正。
    #[cfg(windows)]
    {
        let out_dir = match std::env::var("OUT_DIR") { Ok(s) => s, _ => return };
        let res = std::path::Path::new(&out_dir).join("resource.lib");
        let bytes = match std::fs::read(&res) { Ok(b) => b, _ => return };
        // raw .res 文件前 16 字节固定是空 header + 32 32bit + 0xFFFF 标记
        if bytes.len() < 32 || &bytes[..4] != b"\x00\x00\x00\x00" || &bytes[8..12] != b"\xff\xff\x00\x00" {
            return;
        }
        let coff = std::path::Path::new(&out_dir).join("resource_coff.lib");
        let status = std::process::Command::new("cvtres.exe")
            .args(["/nologo", "/MACHINE:X64",
                   &format!("/OUT:{}", coff.display()), &res.display().to_string()])
            .status();
        if matches!(status, Ok(s) if s.success()) && std::fs::copy(&coff, &res).is_ok() {
            println!("cargo:warning=resource.lib rewritten as COFF via cvtres (icon fix)");
        }
    }
}
