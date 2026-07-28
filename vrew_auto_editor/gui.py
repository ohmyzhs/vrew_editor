from __future__ import annotations

import json
import socket
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .discovery import discover_companion_paths
from .picker import pick_path
from .workflow import analyze_project, transform_project, write_report


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vrew 자동 편집기</title>
<style>
:root{color-scheme:dark;--bg:#0c1018;--panel:#151c28;--line:#293447;--text:#edf2fb;--muted:#91a0b7;--accent:#78a9ff;--good:#57d38c;--bad:#ff7b86}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#18243a 0,var(--bg) 42%);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:34px 24px 60px}h1{font-size:30px;margin:0 0 4px}.lead{color:var(--muted);margin:0 0 26px}
.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}@media(max-width:840px){.grid{grid-template-columns:1fr}}
.card{background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:15px;padding:20px;box-shadow:0 16px 50px #0004}
h2{font-size:16px;margin:0 0 15px}.field{margin:11px 0}label{display:block;color:#cbd5e5;font-size:13px;margin-bottom:5px}
input[type=text],input[type=number]{width:100%;border:1px solid var(--line);border-radius:9px;padding:10px 11px;background:#0d131e;color:var(--text);outline:none}
input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #78a9ff1c}.row{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.checks{display:flex;gap:22px;flex-wrap:wrap;margin:8px 0 14px}
.path-row{display:grid;grid-template-columns:1fr auto;gap:7px}.path-row button{padding:8px 13px;white-space:nowrap}
.check{display:flex;align-items:center;gap:7px;color:#dbe5f5}.check input{accent-color:var(--accent)}
.actions{display:flex;gap:10px;margin-top:18px}button{border:0;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer;background:#273246;color:var(--text)}
button.primary{background:var(--accent);color:#09101d}button:disabled{opacity:.45;cursor:wait}
.hint{font-size:12px;color:var(--muted);margin-top:8px}.status{min-height:48px;margin-top:14px;padding:11px 13px;border:1px solid var(--line);border-radius:10px;color:var(--muted)}
.status.good{border-color:#57d38c66;color:var(--good)}.status.bad{border-color:#ff7b8666;color:var(--bad)}
pre{margin:0;white-space:pre-wrap;word-break:break-word;max-height:680px;overflow:auto;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:#c9d5e8}
.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}.metric{background:#0d131e;border:1px solid var(--line);border-radius:10px;padding:10px}
.metric strong{display:block;font-size:20px}.metric span{font-size:11px;color:var(--muted)}
</style>
</head>
<body><main>
<h1>Vrew 자동 편집기</h1>
<p class="lead">원본을 보존한 채 대사 경계, 번호 이미지, Ken Burns와 후처리를 복제본에 적용합니다.</p>
<div class="grid">
<section class="card">
<h2>입력과 출력</h2>
<div class="field"><label>Vrew 원본</label><div class="path-row"><input id="source" type="text" placeholder="영상 원본 .vrew"><button class="pick" data-target="source" data-kind="file" data-title="Vrew 원본 선택">파일 선택</button></div></div>
<div class="field"><label>넘버링 대본 TXT</label><div class="path-row"><input id="script" type="text" placeholder="번호와 대사가 있는 .txt"><button class="pick" data-target="script" data-kind="file" data-title="넘버링 대본 선택">파일 선택</button></div></div>
<div class="field"><label>번호 이미지 폴더</label><div class="path-row"><input id="images" type="text" placeholder="001-1.jpeg 등이 있는 폴더"><button class="pick" data-target="images" data-kind="directory" data-title="번호 이미지 폴더 선택">폴더 선택</button></div></div>
<div class="field"><label>공통 클립 Vrew</label><div class="path-row"><input id="commonTemplate" type="text" placeholder="1~2 구독, 3~7 아웃트로가 있는 .vrew"><button class="pick" data-target="commonTemplate" data-kind="file" data-title="공통 클립 Vrew 선택">파일 선택</button></div></div>
<div class="field"><label>인트로 영상 폴더</label><div class="path-row"><input id="introDirectory" type="text" placeholder="intro1.mp4 ~ introN.mp4가 있는 폴더"><button class="pick" data-target="introDirectory" data-kind="directory" data-title="인트로 영상 폴더 선택">폴더 선택</button></div></div>
<div class="field"><label>출력 Vrew</label><div class="path-row"><input id="output" type="text" placeholder="비워두면 원본 옆에 _자동편집.vrew"><button class="pick" data-target="output" data-kind="save" data-title="출력 Vrew 저장 위치">저장 위치</button></div></div>
<p class="hint">원본 Vrew를 고르면 같은 폴더의 *_flow_prompts.txt와 intro1~n.mp4, 하위 폴더의 번호 이미지를 자동으로 찾습니다. 공통 클립 경로는 브라우저에 기억됩니다.</p>

<h2 style="margin-top:24px">핵심 옵션</h2>
<div class="checks">
<label class="check"><input id="repair" type="checkbox" checked>대사/나레이션 재분배</label>
<label class="check"><input id="attachImages" type="checkbox" checked>번호 이미지 첨부</label>
<label class="check"><input id="kenBurns" type="checkbox" checked>Ken Burns 움직임</label>
</div>
<div class="row">
<div class="field"><label>최대 글자</label><input id="maxChars" type="number" value="20"></div>
<div class="field"><label>최소 초</label><input id="minSeconds" type="number" value="15"></div>
<div class="field"><label>최대 초</label><input id="maxSeconds" type="number" value="20"></div>
<div class="field"><label>이미지 변형</label><input id="variant" type="text" value="1" title="001-1, 001-2 중 하이픈 뒤 번호가 1인 파일을 우선 선택"></div>
<div class="field"><label>랜덤 시드</label><input id="seed" type="number" value="20260728"></div>
</div>
<p class="hint"><b>이미지 변형 1</b>은 001-1.jpeg, 001-2.jpeg처럼 같은 번호가 여러 개일 때 -1 파일을 우선 선택한다는 뜻입니다. 이미지가 하나면 영향이 없습니다.</p>

<h2 style="margin-top:24px">공통 후처리 규칙</h2>
<p class="hint">공통 파일의 1~2번 클립으로 기존 구독 안내 구간을 교체하고, 3~7번 클립을 마지막에 추가합니다. 공통 파일의 AI 안내 문구와 워터마크는 전체 클립에 적용됩니다. intro1~n 영상은 구독 클립 전까지 자동 분배됩니다.</p>

<div class="actions">
<button id="analyze" type="button">1. 변경안 분석</button>
<button id="transform" class="primary" type="button">2. 복제본 생성</button>
<button id="shutdown" type="button">앱 종료</button>
</div>
<div id="status" class="status">대기 중</div>
</section>
<section class="card">
<h2>검증 결과</h2>
<div id="metrics" class="metric-grid"></div>
<pre id="result">분석 결과가 여기에 표시됩니다.</pre>
</section>
</div>
</main>
<script>
const $=id=>document.getElementById(id);
const commonTemplateKey="vrew-auto-editor.common-template";
function value(id){return $(id).value.trim()||null}
const rememberedCommon=localStorage.getItem(commonTemplateKey);
if(rememberedCommon)$("commonTemplate").value=rememberedCommon;
$("commonTemplate").onchange=()=>{
  const path=value("commonTemplate");
  if(path)localStorage.setItem(commonTemplateKey,path);
  else localStorage.removeItem(commonTemplateKey);
};
async function discover(){
  if(!value("source"))return;
  const response=await fetch("/api/discover",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:value("source")})});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error||"자동 탐색 오류");
  $("script").value=result.script||"";$("images").value=result.images||"";
  $("introDirectory").value=result.introDirectory||"";$("output").value=result.output;
  $("status").className=result.warnings.length?"status":"status good";
  $("status").textContent=`자동 탐색: 대본 ${result.script?"완료":"없음"}, 이미지 ${result.numberedImageCount}개, 인트로 ${result.introVideos.length}개${result.warnings.length?" · "+result.warnings.join(" "):""}`;
}
function payload(){
  return {source:value("source"),output:value("output"),script:value("script"),image_directory:value("images"),
    common_template:value("commonTemplate"),intro_directory:value("introDirectory"),
    preferred_variant:value("variant")||"1",repair_clips:$("repair").checked,attach_images:$("attachImages").checked,
    ken_burns:$("kenBurns").checked,
    max_chars:Number(value("maxChars")||20),minimum_seconds:Number(value("minSeconds")||15),
    maximum_seconds:Number(value("maxSeconds")||20),seed:Number(value("seed")||20260728)};
}
function metrics(data){
  const repair=data.clipRepair||{},images=data.images||{};
  const items=[
    ["클립",data.finalClipCount??data.clipCount??"-"],
    ["재분배 구간",repair.repairedSceneCount??"-"],
    ["이미지 구간",images.segmentCount??data.matchedScriptCount??"-"],
    ["대본 매칭",images.matchedScriptCount??data.matchedScriptCount??"-"],
    ["무결성",String(data.outputIntegrityValid??data.integrityValid??"-")],
    ["길이(초)",data.durationSeconds??"-"]];
  $("metrics").innerHTML=items.map(([l,v])=>`<div class="metric"><strong>${v}</strong><span>${l}</span></div>`).join("");
}
async function run(endpoint){
  const data=payload(); if(!data.source){alert("Vrew 원본 경로를 입력하세요.");return}
  $("analyze").disabled=$("transform").disabled=true;$("status").className="status";$("status").textContent="처리 중…";
  try{
    const response=await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||"처리에 실패했습니다.");
    $("result").textContent=JSON.stringify(result,null,2);metrics(result);
    $("status").className="status good";$("status").textContent=result.output?`완료: ${result.output}`:"분석 완료 — 원본은 변경되지 않았습니다.";
    if(result.output)$("output").value=result.output;
  }catch(error){$("status").className="status bad";$("status").textContent=error.message}
  finally{$("analyze").disabled=$("transform").disabled=false}
}
$("analyze").onclick=()=>run("/api/analyze");$("transform").onclick=()=>run("/api/transform");
document.querySelectorAll(".pick").forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
    let defaultName=null;
    if(button.dataset.kind==="save"&&value("source")){
      const name=value("source").split(/[\\/]/).pop().replace(/\.vrew$/i,"");
      defaultName=`${name}_작업완료.vrew`;
    }
    const response=await fetch("/api/pick",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:button.dataset.kind,title:button.dataset.title,default_name:defaultName})});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||"선택창 오류");
    if(result.path){
      $(button.dataset.target).value=result.path;
      if(button.dataset.target==="source")await discover();
      if(button.dataset.target==="commonTemplate")$("commonTemplate").onchange();
    }
  }catch(error){$("status").className="status bad";$("status").textContent=error.message}
  finally{button.disabled=false}
});
$("source").onchange=()=>discover().catch(error=>{$("status").className="status bad";$("status").textContent=error.message});
$("shutdown").onclick=async()=>{await fetch("/api/shutdown",{method:"POST"});document.body.innerHTML="<main><h1>Vrew 자동 편집기를 종료했습니다.</h1><p class='lead'>이 창을 닫아도 됩니다.</p></main>"};
</script></body></html>"""


def _default_output(source: str) -> str:
    path = Path(source).expanduser().resolve()
    return str(path.with_name(f"{path.stem}_작업완료.vrew"))


class Handler(BaseHTTPRequestHandler):
    server_version = "VrewAutoEditor/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        raw = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        endpoint = urlparse(self.path).path
        if endpoint == "/api/shutdown":
            self._json(HTTPStatus.OK, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if endpoint not in {
            "/api/pick",
            "/api/discover",
            "/api/analyze",
            "/api/transform",
        }:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if endpoint == "/api/pick":
                selected = pick_path(
                    str(payload.get("kind", "file")),
                    title=str(payload.get("title", "경로 선택")),
                    default_name=payload.get("default_name"),
                )
                self._json(HTTPStatus.OK, {"path": selected})
                return
            if endpoint == "/api/discover":
                source = payload.get("source")
                if not source:
                    raise ValueError("Vrew 원본 경로가 필요합니다.")
                self._json(HTTPStatus.OK, discover_companion_paths(source))
                return
            source = payload.get("source")
            if not source:
                raise ValueError("Vrew 원본 경로가 필요합니다.")
            common = {
                "script": payload.get("script"),
                "image_directory": payload.get("image_directory"),
                "preferred_variant": payload.get("preferred_variant", "1"),
                "max_chars": int(payload.get("max_chars", 20)),
                "common_template": payload.get("common_template"),
            }
            if endpoint == "/api/analyze":
                result = analyze_project(source, **common)
            else:
                output = payload.get("output") or _default_output(source)
                result = transform_project(
                    source,
                    output,
                    **common,
                    repair_clips=bool(payload.get("repair_clips", True)),
                    attach_images=bool(payload.get("attach_images", True)),
                    seed=int(payload.get("seed", 20260728)),
                    minimum_seconds=float(payload.get("minimum_seconds", 15)),
                    maximum_seconds=float(payload.get("maximum_seconds", 20)),
                    ken_burns=bool(payload.get("ken_burns", True)),
                    intro_directory=payload.get("intro_directory"),
                    intro_video=payload.get("intro_video"),
                    subscribe_video=payload.get("subscribe_video"),
                    subscribe_start_clip=payload.get("subscribe_start_clip"),
                    outro_video=payload.get("outro_video"),
                    watermark=payload.get("watermark"),
                    ai_notice=payload.get("ai_notice"),
                )
                write_report(result, Path(output).with_suffix(".report.json"))
            self._json(HTTPStatus.OK, result)
        except Exception as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc), "type": type(exc).__name__},
            )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main(*, open_browser: bool = True) -> None:
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Vrew 자동 편집기 실행 중: {url}")
    print("종료하려면 Ctrl+C를 누르세요.")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
