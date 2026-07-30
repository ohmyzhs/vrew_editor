import "./style.css";
import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

const COMMON_TEMPLATE_STORAGE_KEY = "vrew-auto-editor.common-template";

const fields = [
  { id: "source", label: "Vrew 원본", kind: "vrew", placeholder: "작업할 .vrew 파일", required: true },
  { id: "script", label: "넘버링 대본", kind: "text", placeholder: "번호와 대사가 있는 .txt" },
  { id: "images", label: "번호 이미지 폴더", kind: "directory", placeholder: "001-1.jpeg 등이 있는 폴더" },
  { id: "common", label: "공통 클립 Vrew", kind: "vrew", placeholder: "구독·아웃트로·공통 서식 원본" },
  { id: "intros", label: "인트로 영상 폴더", kind: "directory", placeholder: "intro1.mp4 ~ introN.mp4 폴더" },
  { id: "output", label: "출력 Vrew", kind: "save", placeholder: "새 .vrew 파일 저장 위치", required: true },
];

const fieldRoot = document.querySelector("#path-fields");
fieldRoot.innerHTML = fields.map((field) => `
  <label class="path-field">
    <span>${field.label}${field.required ? '<em>필수</em>' : ""}</span>
    <div>
      <input id="${field.id}" placeholder="${field.placeholder}" />
      <button class="pick" data-id="${field.id}" data-kind="${field.kind}">선택</button>
    </div>
  </label>
`).join("");

const $ = (id) => document.getElementById(id);
const value = (id) => $(id).value.trim();
const status = $("status");
const buttons = [$("analyze"), $("transform")];

function defaultOutput() {
  const source = value("source");
  if (!source) return "작업완료.vrew";
  const separator = source.includes("\\") ? "\\" : "/";
  const parts = source.split(/[\\/]/);
  const name = parts.pop().replace(/\.vrew$/i, "");
  return [...parts, `${name}_작업완료.vrew`].join(separator);
}

function rememberCommonTemplate() {
  const path = value("common");
  if (path) localStorage.setItem(COMMON_TEMPLATE_STORAGE_KEY, path);
  else localStorage.removeItem(COMMON_TEMPLATE_STORAGE_KEY);
}

function restoreCommonTemplate() {
  const remembered = localStorage.getItem(COMMON_TEMPLATE_STORAGE_KEY);
  if (remembered) $("common").value = remembered;
}

function discoverySummary(data) {
  const found = [
    data.script ? "대본" : null,
    data.images ? `이미지 ${data.numberedImageCount}개` : null,
    data.introDirectory ? `인트로 ${data.introVideos.length}개` : null,
  ].filter(Boolean);
  const warning = data.warnings.length ? ` · ${data.warnings.join(" ")}` : "";
  return `자동 탐색: ${found.join(", ") || "추가 파일 없음"}${warning}`;
}

async function discoverFromSource() {
  const source = value("source");
  if (!source) return;
  status.className = "status";
  status.textContent = "원본 폴더에서 대본·이미지·인트로를 찾고 있습니다…";
  const result = await invoke("run_engine", {
    args: ["discover", source],
  });
  if (result.code !== 0) {
    throw new Error(result.stderr.trim() || "관련 파일 자동 탐색에 실패했습니다.");
  }
  const data = JSON.parse(result.stdout);
  $("script").value = data.script || "";
  $("images").value = data.images || "";
  $("intros").value = data.introDirectory || "";
  $("output").value = data.output;
  status.className = data.warnings.length ? "status" : "status success";
  status.textContent = discoverySummary(data);
}

async function choose(field) {
  const options = { multiple: false, title: `${field.label} 선택` };
  let selected;
  if (field.kind === "directory") {
    selected = await open({ ...options, directory: true });
  } else if (field.kind === "save") {
    selected = await save({
      title: "출력 Vrew 저장 위치",
      defaultPath: defaultOutput(),
      filters: [{ name: "Vrew 프로젝트", extensions: ["vrew"] }],
    });
  } else {
    const extensions = field.kind === "text" ? ["txt"] : ["vrew"];
    selected = await open({
      ...options,
      directory: false,
      filters: [{ name: field.label, extensions }],
    });
  }
  if (!selected) return false;
  $(field.id).value = selected;
  if (field.id === "common") rememberCommonTemplate();
  if (field.id === "source") await discoverFromSource();
  return true;
}

document.querySelectorAll(".pick").forEach((button) => {
  button.addEventListener("click", async () => {
    const field = fields.find((item) => item.id === button.dataset.id);
    try {
      button.disabled = true;
      const selected = await choose(field);
      if (selected && field.id !== "source") {
        status.className = "status";
        status.textContent = "경로를 선택했습니다.";
      }
    } catch (error) {
      showError(error);
    } finally {
      button.disabled = false;
    }
  });
});

$("source").addEventListener("change", async () => {
  try {
    await discoverFromSource();
  } catch (error) {
    showError(error);
  }
});
$("common").addEventListener("change", rememberCommonTemplate);
restoreCommonTemplate();

function addArg(args, flag, field) {
  const content = value(field);
  if (content) args.push(flag, content);
}

function buildArgs(mode) {
  const source = value("source");
  if (!source) throw new Error("Vrew 원본을 선택하세요.");
  const args = [mode, source];
  if (mode === "transform") {
    const output = value("output") || defaultOutput();
    $("output").value = output;
    args.push(output);
  }
  addArg(args, "--script", "script");
  addArg(args, "--images", "images");
  addArg(args, "--common-template", "common");
  args.push("--variant", value("variant") || "1");
  args.push("--max-chars", value("max-chars") || "20");
  if (mode === "transform") {
    addArg(args, "--intro-directory", "intros");
    args.push("--seed", value("seed") || "20260728");
    args.push("--min-seconds", value("min-seconds") || "15");
    args.push("--max-seconds", value("max-seconds") || "20");
    if (!$("repair").checked) args.push("--no-repair");
    if (!$("attach-images").checked) args.push("--no-images");
    if (!$("ken-burns").checked) args.push("--no-ken-burns");
  }
  return args;
}

function syncImageOptions() {
  const imagesEnabled = $("attach-images").checked;
  $("ken-burns").disabled = !imagesEnabled;
  const animationEnabled = imagesEnabled && $("ken-burns").checked;
  ["min-seconds", "max-seconds", "seed"].forEach((id) => {
    $(id).disabled = !animationEnabled;
  });
}

$("attach-images").addEventListener("change", syncImageOptions);
$("ken-burns").addEventListener("change", syncImageOptions);
syncImageOptions();

function setBusy(busy, message) {
  buttons.forEach((button) => { button.disabled = busy; });
  status.className = "status";
  status.textContent = message;
  $("result-state").textContent = busy ? "처리 중" : "완료";
}

function renderMetrics(data) {
  const repair = data.clipRepair || {};
  const images = data.images || {};
  const style = data.commonTemplate?.captionStyle || {};
  const items = [
    ["최종 클립", data.finalClipCount ?? data.clipCount ?? "—"],
    ["재분배 구간", repair.repairedSceneCount ?? "—"],
    ["이미지 구간", images.segmentCount ?? data.matchedScriptCount ?? "—"],
    ["대본 매칭", images.matchedScriptCount ?? data.matchedScriptCount ?? "—"],
    ["공통 자막", style.font || "분석 후 확인"],
    ["무결성", String(data.outputIntegrityValid ?? data.integrityValid ?? "—")],
  ];
  $("metrics").innerHTML = items.map(([label, result]) =>
    `<div><strong>${result}</strong><span>${label}</span></div>`
  ).join("");
}

function showError(error) {
  status.className = "status error";
  status.textContent = String(error?.message || error);
  $("result-state").textContent = "오류";
}

async function run(mode) {
  try {
    const args = buildArgs(mode);
    setBusy(true, mode === "analyze" ? "프로젝트를 분석하고 있습니다…" : "복제본을 생성하고 있습니다…");
    const output = await invoke("run_engine", { args });
    if (output.code !== 0) {
      throw new Error(output.stderr.trim() || `편집 엔진 종료 코드: ${output.code}`);
    }
    const data = JSON.parse(output.stdout);
    $("result").textContent = JSON.stringify(data, null, 2);
    renderMetrics(data);
    status.className = "status success";
    status.textContent = data.output ? `완료: ${data.output}` : "분석 완료 — 원본은 변경되지 않았습니다.";
  } catch (error) {
    showError(error);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

$("analyze").addEventListener("click", () => run("analyze"));
$("transform").addEventListener("click", () => run("transform"));
