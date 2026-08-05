import "./style.css";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

const COMMON_TEMPLATE_STORAGE_KEY = "vrew-auto-editor.common-template";

const $ = (id) => document.getElementById(id);
const status = $("status");
const actionButtons = [$("analyze"), $("transform")];

const state = {
  dependenciesReady: false,
  dependenciesFailed: false,
  source: null,
  directory: null,
  discovery: null,
};

function separatorOf(path) {
  return path.includes("\\") ? "\\" : "/";
}

function fileNameOf(path) {
  return path.split(/[\\/]/).pop();
}

function relativeTo(path, base) {
  if (!path || !base) return path || "";
  const sep = separatorOf(base);
  const normalize = (value) => value.replace(/[\\/]+$/, "");
  const target = normalize(path);
  const root = normalize(base);
  if (target === root) return ".";
  if (target.toLowerCase().startsWith(`${root}${sep}`.toLowerCase())) {
    return `.${sep}${target.slice(root.length + 1)}`;
  }
  return path;
}

function formatDuration(seconds) {
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return minutes ? `${minutes}분 ${rest}초` : `${rest}초`;
}

function nextPaint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function showOverlay(message, steps = []) {
  $("overlay-message").textContent = message;
  $("overlay-steps").innerHTML = steps
    .map((step, index) => `<li data-step="${index}">${step}</li>`)
    .join("");
  const firstStep = $("overlay-steps").firstElementChild;
  if (firstStep) firstStep.classList.add("active");
  $("overlay").classList.remove("hidden");
}

function advanceOverlayStep(index) {
  const items = [...document.querySelectorAll("#overlay-steps li")];
  const item = items[index];
  if (!item) return;
  item.classList.remove("active");
  item.classList.add("done");
  items[index + 1]?.classList.add("active");
}

function hideOverlay() {
  $("overlay").classList.add("hidden");
}

function syncControls() {
  const ready = state.dependenciesReady;
  $("pick-source").disabled = !ready;
  $("pick-common").disabled = !ready;
  actionButtons.forEach((button) => {
    button.disabled = !ready || !state.source;
  });
  $("retry-dependencies").hidden = ready || !state.dependenciesFailed;
}

function setStatus(kind, message) {
  status.className = `status${kind ? ` ${kind}` : ""}`;
  status.textContent = message;
}

function setDetect(id, stateName, detail) {
  const item = $(id);
  item.className = `detect ${stateName}`;
  item.querySelector(".detect-detail").textContent = detail;
  const stateLabels = { ok: "READY", miss: "MISSING", pending: "WAIT" };
  item.querySelector(".detect-state").textContent = stateLabels[stateName] || "WAIT";
}

function resetDetectList() {
  ["detect-script", "detect-images", "detect-intros"].forEach((id) =>
    setDetect(id, "pending", "대기 중")
  );
}

function renderSourceInfo(data) {
  const info = $("source-info");
  info.classList.remove("empty");
  const meta = data.sourceMeta;
  const metaText = meta
    ? `클립 ${meta.clipCount}개 · 총 ${formatDuration(meta.durationSeconds)}`
    : "메타정보를 읽지 못했습니다";
  info.innerHTML = `
    <span class="source-status">READY</span>
    <span class="source-name">${fileNameOf(data.source)}</span>
    <span class="source-meta">${metaText}</span>
    <span class="mini-path">${data.source}</span>
  `;
}

function renderDiscovery(data) {
  if (data.script) {
    const count = data.scriptLineCount;
    setDetect(
      "detect-script",
      "ok",
      `${relativeTo(data.script, data.directory)} · 대본 ${count ?? "?"}개 인식`
    );
  } else {
    setDetect("detect-script", "miss", "찾지 못함 (*_flow_prompts.txt)");
  }

  if (data.images) {
    setDetect(
      "detect-images",
      "ok",
      `${relativeTo(data.images, data.directory)} · 번호 이미지 ${data.numberedImageCount}개`
    );
  } else {
    setDetect("detect-images", "miss", "번호 이미지를 찾지 못함");
  }

  if (data.introDirectory && data.introVideos.length) {
    setDetect(
      "detect-intros",
      "ok",
      `${relativeTo(data.introDirectory, data.directory)} · 인트로 영상 ${data.introVideos.length}개`
    );
  } else {
    setDetect("detect-intros", "miss", "인트로 영상을 찾지 못함");
  }

  $("output-name").value = fileNameOf(data.output);
  $("output-name").disabled = false;
}

async function discoverFromSource(source) {
  const steps = [
    "원본 Vrew 메타정보 읽는 중",
    "넘버링 대본 탐색 중",
    "번호 이미지 폴더 탐색 중",
    "인트로 영상 탐색 중",
  ];
  showOverlay("원본을 분석하고 주변 파일을 자동으로 찾고 있습니다", steps);
  const timer = { index: 0 };
  const interval = setInterval(() => {
    advanceOverlayStep(timer.index);
    timer.index = Math.min(timer.index + 1, steps.length - 1);
  }, 600);
  try {
    await nextPaint();
    const result = await invoke("run_engine", { args: ["discover", source] });
    if (result.code !== 0) {
      throw new Error(result.stderr.trim() || "관련 파일 자동 탐색에 실패했습니다.");
    }
    steps.forEach((_, index) => advanceOverlayStep(index));
    return JSON.parse(result.stdout);
  } finally {
    clearInterval(interval);
    setTimeout(hideOverlay, 250);
  }
}

async function chooseSource() {
  const selected = await open({
    multiple: false,
    directory: false,
    title: "Vrew 원본 선택",
    filters: [{ name: "Vrew 프로젝트", extensions: ["vrew"] }],
  });
  if (!selected) return;
  try {
    const data = await discoverFromSource(selected);
    state.source = data.source;
    state.directory = data.directory;
    state.discovery = data;
    renderSourceInfo(data);
    renderDiscovery(data);
    syncControls();
    const warning = data.warnings.length ? ` · ${data.warnings.join(" ")}` : "";
    setStatus(data.warnings.length ? "" : "success", `자동 인식 완료${warning}`);
  } catch (error) {
    resetDetectList();
    showError(error);
  }
}

function rememberCommonTemplate(path) {
  if (path) localStorage.setItem(COMMON_TEMPLATE_STORAGE_KEY, path);
  else localStorage.removeItem(COMMON_TEMPLATE_STORAGE_KEY);
}

function renderCommonPath(path) {
  $("common-path").textContent = path || "선택된 파일 없음";
  $("common-path").title = path || "";
}

async function chooseCommon() {
  const selected = await open({
    multiple: false,
    directory: false,
    title: "공통 클립 Vrew 선택",
    filters: [{ name: "Vrew 프로젝트", extensions: ["vrew"] }],
  });
  if (!selected) return;
  rememberCommonTemplate(selected);
  renderCommonPath(selected);
}

$("pick-source").addEventListener("click", chooseSource);
$("pick-common").addEventListener("click", chooseCommon);
renderCommonPath(localStorage.getItem(COMMON_TEMPLATE_STORAGE_KEY));

function buildOutputPath() {
  const name = $("output-name").value.trim() || `${fileNameOf(state.source).replace(/\.vrew$/i, "")}_작업완료.vrew`;
  const sep = separatorOf(state.directory);
  return `${state.directory}${sep}${name}`;
}

function buildArgs(mode) {
  if (!state.source) throw new Error("Vrew 원본을 먼저 선택하세요.");
  const discovery = state.discovery || {};
  const args = [mode, state.source];
  if (mode === "transform") args.push(buildOutputPath());
  if (discovery.script) args.push("--script", discovery.script);
  if (discovery.images) args.push("--images", discovery.images);
  const common = localStorage.getItem(COMMON_TEMPLATE_STORAGE_KEY);
  if (common) args.push("--common-template", common);
  args.push("--variant", $("variant").value.trim() || "1");
  args.push("--max-chars", $("max-chars").value.trim() || "20");
  if (mode === "transform") {
    if (discovery.introDirectory) args.push("--intro-directory", discovery.introDirectory);
    args.push("--seed", $("seed").value.trim() || "20260728");
    args.push("--min-seconds", $("min-seconds").value.trim() || "15");
    args.push("--max-seconds", $("max-seconds").value.trim() || "20");
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
  setStatus("error", String(error?.message || error));
}

async function ensureDependencies() {
  state.dependenciesFailed = false;
  syncControls();
  const steps = [
    "필수 프로그램 설치 여부 확인 중",
    "FFmpeg·FFprobe 준비 중",
    "설치 상태 확인 중",
  ];
  showOverlay("프로그램 실행에 필요한 라이브러리를 확인·설치하고 있습니다", steps);
  let currentStep = 0;
  const interval = setInterval(() => {
    advanceOverlayStep(currentStep);
    currentStep = Math.min(currentStep + 1, steps.length - 1);
  }, 700);

  try {
    await nextPaint();
    const result = await invoke("run_engine", { args: ["dependencies"] });
    if (result.code !== 0) {
      throw new Error(result.stderr.trim() || "필수 프로그램 준비에 실패했습니다.");
    }
    const data = JSON.parse(result.stdout);
    state.dependenciesReady = true;
    setStatus(
      "success",
      data.installed
        ? "FFmpeg·FFprobe 설치 완료. Vrew 원본을 선택하세요."
        : "필수 프로그램 확인 완료. Vrew 원본을 선택하세요."
    );
  } catch (error) {
    state.dependenciesFailed = true;
    showError(new Error(`필수 프로그램 준비 실패: ${String(error?.message || error)}`));
  } finally {
    clearInterval(interval);
    steps.forEach((_, index) => advanceOverlayStep(index));
    hideOverlay();
    syncControls();
  }
}

async function run(mode) {
  try {
    const args = buildArgs(mode);
    actionButtons.forEach((button) => { button.disabled = true; });
    showOverlay(
      mode === "analyze"
        ? "자동편집 체크 — 프로젝트를 분석하고 있습니다"
        : "자동편집 실행 — 복제본을 생성하고 있습니다"
    );
    await nextPaint();
    const output = await invoke("run_engine", { args });
    if (output.code !== 0) {
      throw new Error(output.stderr.trim() || `편집 엔진 종료 코드: ${output.code}`);
    }
    const data = JSON.parse(output.stdout);
    renderMetrics(data);
    setStatus(
      "success",
      data.output ? `완료: ${data.output}` : "체크 완료 — 원본은 변경되지 않았습니다."
    );
  } catch (error) {
    showError(error);
  } finally {
    hideOverlay();
    syncControls();
  }
}

$("analyze").addEventListener("click", () => run("analyze"));
$("transform").addEventListener("click", () => run("transform"));
$("retry-dependencies").addEventListener("click", ensureDependencies);
syncControls();
ensureDependencies();
