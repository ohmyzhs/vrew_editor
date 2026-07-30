#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use std::path::PathBuf;
use std::process::Command;

use serde::Serialize;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineOutput {
    code: i32,
    stdout: String,
    stderr: String,
}

#[cfg(target_os = "windows")]
const ENGINE_BYTES: &[u8] = include_bytes!("../binaries/vrew-engine-x86_64-pc-windows-msvc.exe");

#[cfg(target_os = "windows")]
fn embedded_engine_path() -> Result<PathBuf, String> {
    let directory = std::env::temp_dir()
        .join("vrew-auto-editor")
        .join(env!("CARGO_PKG_VERSION"));
    std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;

    let path = directory.join("vrew-engine.exe");
    let needs_write = std::fs::read(&path)
        .map(|installed| installed != ENGINE_BYTES)
        .unwrap_or(true);

    if needs_write {
        let temporary = directory.join(format!("vrew-engine-{}.tmp", std::process::id()));
        std::fs::write(&temporary, ENGINE_BYTES).map_err(|error| error.to_string())?;
        if path.exists() {
            std::fs::remove_file(&path).map_err(|error| error.to_string())?;
        }
        std::fs::rename(&temporary, &path).map_err(|error| error.to_string())?;
    }

    Ok(path)
}

#[tauri::command]
fn run_engine(args: Vec<String>) -> Result<EngineOutput, String> {
    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new(embedded_engine_path()?);
        command.creation_flags(0x08000000);
        command
    };

    #[cfg(not(target_os = "windows"))]
    let mut command = Command::new("vrew-engine");

    let output = command
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .args(args)
        .output()
        .map_err(|error| format!("편집 엔진을 실행할 수 없습니다: {error}"))?;

    Ok(EngineOutput {
        code: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8(output.stdout)
            .map_err(|_| "편집 엔진의 표준 출력이 UTF-8이 아닙니다.".to_string())?,
        stderr: String::from_utf8(output.stderr)
            .map_err(|_| "편집 엔진의 오류 출력이 UTF-8이 아닙니다.".to_string())?,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![run_engine])
        .run(tauri::generate_context!())
        .expect("error while running Vrew Auto Editor");
}

#[cfg(all(test, target_os = "windows"))]
mod tests {
    use super::run_engine;

    #[test]
    fn embedded_engine_can_start() {
        let output = run_engine(vec!["--help".to_string()])
            .expect("embedded engine should be extracted and started");
        assert_eq!(output.code, 0, "{}", output.stderr);
        assert!(output.stdout.contains("usage:"));
    }
}
