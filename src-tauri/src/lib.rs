use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

#[derive(Serialize)]
struct EngineOutput {
    code: i32,
    stdout: String,
    stderr: String,
}

fn engine_filename() -> &'static str {
    if cfg!(target_os = "windows") {
        "vrew-engine.exe"
    } else {
        "vrew-engine"
    }
}

fn development_sidecar_path() -> Option<PathBuf> {
    let triple = match (std::env::consts::OS, std::env::consts::ARCH) {
        ("windows", "x86_64") => "x86_64-pc-windows-msvc",
        ("windows", "aarch64") => "aarch64-pc-windows-msvc",
        ("macos", "aarch64") => "aarch64-apple-darwin",
        ("macos", "x86_64") => "x86_64-apple-darwin",
        ("linux", "x86_64") => "x86_64-unknown-linux-gnu",
        ("linux", "aarch64") => "aarch64-unknown-linux-gnu",
        _ => return None,
    };
    let extension = if cfg!(target_os = "windows") {
        ".exe"
    } else {
        ""
    };
    Some(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("binaries")
            .join(format!("vrew-engine-{triple}{extension}")),
    )
}

fn locate_engine() -> Result<PathBuf, String> {
    let current_exe = std::env::current_exe()
        .map_err(|error| format!("앱 실행 경로를 확인하지 못했습니다: {error}"))?;
    let mut candidates = vec![current_exe
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(engine_filename())];
    if let Some(path) = development_sidecar_path() {
        candidates.push(path);
    }
    candidates
        .into_iter()
        .find(|path| path.is_file())
        .ok_or_else(|| "Vrew 편집 엔진 실행 파일을 찾지 못했습니다.".to_string())
}

fn execute_engine(executable: PathBuf, args: Vec<String>) -> Result<EngineOutput, String> {
    let mut command = Command::new(executable);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let output = command
        .output()
        .map_err(|error| format!("Vrew 편집 엔진을 실행하지 못했습니다: {error}"))?;
    Ok(EngineOutput {
        code: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8(output.stdout)
            .map_err(|_| "편집 엔진의 출력이 UTF-8이 아닙니다.".to_string())?,
        stderr: String::from_utf8(output.stderr)
            .map_err(|_| "편집 엔진의 오류 출력이 UTF-8이 아닙니다.".to_string())?,
    })
}

#[tauri::command]
async fn run_engine(args: Vec<String>) -> Result<EngineOutput, String> {
    let executable = locate_engine()?;
    tauri::async_runtime::spawn_blocking(move || execute_engine(executable, args))
        .await
        .map_err(|error| format!("편집 엔진 작업을 기다리지 못했습니다: {error}"))?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![run_engine])
        .run(tauri::generate_context!())
        .expect("error while running Vrew Auto Editor");
}
