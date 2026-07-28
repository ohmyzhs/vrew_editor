# Vrew 자동 편집기

Vrew 프로젝트 복제본에 다음 작업을 자동 적용하는 로컬 도구입니다.

- 따옴표·문장부호·TTS 휴지를 반영한 대사와 나레이션 경계 재분배
- 서로 다른 발화가 한 클립에 섞인 경우 분리
- 20글자를 기준으로 하되 의미 보존을 위해 최대 22자까지 허용하고,
  조사·의존명사 결합을 고려해 단어 경계에서 분할
- 넘버링 대본과 `001-1.jpeg` 같은 이미지 자동 매칭
- 다음 대본 번호 전까지 이미지가 끊기지 않도록 전 클립 커버
- Ken Burns 사용 시 15~20초 단위 이미지 구간 생성
- 6개 Ken Burns 효과를 시드 기반 랜덤 배치하거나, 효과를 끄고 번호별 한 구간으로 배치
- `intro1.mp4`~`introN.mp4`를 구독 클립 전 구간에 자동 분배
- 공통 Vrew의 1~2번 클립으로 기존 구독 구간 교체
- 공통 Vrew의 3~7번 클립을 영상 끝에 아웃트로로 추가
- 공통 Vrew의 AI 생성 안내와 워터마크를 전체 클립에 복제

모든 처리는 컴퓨터 안에서 이루어집니다. 원본 `.vrew`는 수정하거나
덮어쓰지 않으며 새 파일만 생성합니다. 출력 경로에 파일이 이미 있으면
그 파일도 덮어쓰지 않고 중단합니다.

## 네이티브 앱 실행

macOS용으로 빌드된 앱은 다음 위치에 생성됩니다.

```text
src-tauri/target/release/bundle/macos/Vrew 자동 편집기.app
```

Finder에서 앱을 실행하면 별도 브라우저나 로컬 웹 서버 없이 독립된
데스크톱 창이 열립니다. 파일과 폴더는 macOS/Windows 네이티브 선택창으로
고릅니다.

원본 Vrew 파일을 고르면 같은 폴더의 `*_flow_prompts.txt`,
`intro1.mp4`~`introN.mp4`, 하위 폴더의 `001-1.jpeg` 같은 번호 이미지를
자동으로 찾습니다. 출력은 기본적으로 `{원본파일명}_작업완료.vrew`이며
저장 위치와 이름은 바꿀 수 있습니다. 공통 클립 Vrew 경로는 한 번
선택하면 앱 로컬 저장소에 기억됩니다.

개발 환경에서 네이티브 앱을 실행하거나 다시 빌드하려면:

```bash
python -m pip install pyinstaller
npm install
npm run tauri:dev
```

macOS 앱 번들:

```bash
npm run tauri:build
```

Windows NSIS 앱:

```powershell
py -m pip install pyinstaller
npm install
npm run tauri:build:windows
```

Tauri와 편집 엔진 사이드카는 운영체제별 바이너리이므로 macOS 앱은
macOS에서, Windows 앱은 Windows에서 각각 빌드해야 합니다.

## 레거시 로컬 웹 화면

macOS:

```bash
./run_gui.command
```

Windows:

```bat
run_gui.bat
```

또는 공통으로:

```bash
python3 run_gui.py
```

이 실행 방식은 호환용으로 남겨 둔 로컬 웹 화면입니다. 브라우저에서
`127.0.0.1` 전용 화면이 열립니다. 각 입력 옆의
**파일 선택**, **폴더 선택**, **저장 위치** 버튼을 누르면 macOS Finder
또는 Windows 탐색기의 네이티브 선택창이 열립니다. 먼저 **변경안 분석**을
실행한 뒤 **복제본 생성**을 누르세요.

## 샘플 008 실행

프로젝트 폴더에서 아래처럼 실행할 수 있습니다. 실제 경로는 환경에 맞게
바꾸세요.

```bash
python3 -m vrew_auto_editor.cli analyze \
  "/path/to/영상08.vrew" \
  --script "/path/to/bunok_gureongi_flow_prompts.txt" \
  --images "/path/to/Flow Batch Studio" \
  --common-template "/path/to/공통클립.vrew" \
  --variant 1
```

```bash
python3 -m vrew_auto_editor.cli transform \
  "/path/to/영상08.vrew" \
  "/path/to/영상08_자동편집.vrew" \
  --script "/path/to/bunok_gureongi_flow_prompts.txt" \
  --images "/path/to/Flow Batch Studio" \
  --common-template "/path/to/공통클립.vrew" \
  --intro-directory "/path/to/intro1부터 introN이 있는 폴더" \
  --variant 1 \
  --report "/path/to/영상08_자동편집.report.json"
```

이미지가 `001-1.jpeg`, `001-2.jpeg`처럼 둘 이상이면 `--variant 1` 또는
`--variant 2`로 선택합니다. 선택 후보 전체는 분석 보고서에 남습니다.
화면의 **이미지 변형 1**도 같은 의미로, 동일 번호 중 `-1` 파일을 우선
사용합니다. 이미지가 번호마다 하나뿐이면 이 값은 영향을 주지 않습니다.
Ken Burns를 끄려면 `--no-ken-burns`를 추가합니다. 이 경우 이미지는
15~20초로 나뉘지 않고 해당 번호의 시작 클립부터 다음 번호 직전까지
하나의 에셋으로 적용됩니다.

## 공통 클립과 인트로 처리

`--common-template`을 지정하면 다음 규칙을 적용합니다.

1. 작업 대상에서 `구독과 좋아요는`으로 시작하는 클립을 찾습니다.
2. 그 클립부터 `옛날 옛적`으로 시작하는 본편 직전까지 삭제합니다.
3. 그 자리에 공통 파일의 1~2번 클립을 원본 미디어와 함께 삽입합니다.
4. 공통 파일의 3~7번 클립을 영상 마지막에 삽입합니다.
5. 공통 파일 1~2번에 들어 있는 이미지 워터마크와 웹 텍스트를 전체
   클립에 적용합니다.
6. 공통 파일 첫 클립의 실제 자막 글꼴·크기·색·외곽선과
   `yAlign`, `yOffset`, `xOffset`, 회전, 폭, 배율을 모든 자막에
   적용합니다. 자막 문구 자체는 변경하지 않습니다.

`--intro-directory`를 함께 지정하면 폴더의 `intro1.mp4`,
`intro2.mp4` … 파일을 숫자순으로 찾아 1번 클립부터 새 구독 클립
직전까지 시간 길이가 비슷하도록 연속 분배합니다. 이 구간은 의도적으로
초안 배치이므로 Vrew에서 수동 조정할 수 있습니다.
배정 구간이 원본 영상보다 길어도 인트로는 기본적으로 한 번만 재생하며,
반복하지 않고 마지막 프레임을 유지합니다.

## 개별 후처리 옵션

```bash
python3 -m vrew_auto_editor.cli transform INPUT.vrew OUTPUT.vrew \
  --script numbered.txt \
  --images images \
  --intro-video intro.mp4 \
  --subscribe-video subscribe.mp4 \
  --subscribe-start-clip 120 \
  --outro-video outro.mp4 \
  --watermark watermark.png \
  --ai-notice "이 영상은 AI기술을 이용한 창작물입니다."
```

개별 인트로·구독·아웃트로 옵션은 기존 클립 위에 영상 자산을 붙입니다. 별도의
나레이션 클립이나 새 재생 시간을 생성하지는 않습니다. 영상 메타데이터
판독에는 `ffprobe`가 필요합니다.

## 처리 원칙

1. 원본 프로젝트와 무결성을 읽어 분석합니다.
2. TTS 시간축이 리셋되는 단위별로 따옴표, 마침표·물음표·느낌표,
   의미 있는 쉼표와 실제 발화 휴지를 함께 조사합니다.
3. 문장부호까지의 절이 12자 이하면 강제 분할하지 않고 다음 문맥과
   합칩니다. 자막 토큰과 실제 TTS 단어가 전부 일치하는 구간만
   어절 내부를 자르지 않고 재분배합니다.
4. 번호 대본을 전체 자막 스트림에 순서대로 매칭합니다.
5. 이미지를 모든 대상 클립에 먼저 배치합니다.
6. Ken Burns가 켜져 있으면 6개 효과를 섞은 배치 단위로 속성을 일괄
   적용하고, 꺼져 있으면 번호별 전체 구간을 한 번만 배치합니다.
7. 공통 구독/아웃트로와 전역 안내 에셋을 복사하고 인트로를 분배합니다.
8. Vrew의 SHA-256 무결성 값을 재계산하고 새 ZIP 컨테이너를 만듭니다.
9. 저장 후 프로젝트를 다시 읽어 무결성을 검증합니다.

## 지원 범위

- 검증한 Vrew 프로젝트 버전: 16, 17
- 기준 앱: Vrew 4.3.3
- Python: 3.10 이상
- 운영체제: macOS, Windows
- 이미지: JPEG, PNG
- 영상: `ffprobe`가 읽을 수 있는 MP4/MOV/MKV 등

인트로 분석에는 FFmpeg의 `ffprobe`가 필요합니다. macOS에서는
`/opt/homebrew/bin/ffprobe`와 `/usr/local/bin/ffprobe`도 자동 탐색합니다.
Windows에서는 FFmpeg를 설치해 PATH에 추가하거나 `ffprobe.exe`를 앱
실행 파일과 같은 폴더에 두면 됩니다.

Vrew 파일 형식은 공개 표준이 아닙니다. 앱 업데이트로 프로젝트 버전이
바뀌면 도구는 안전하게 중단하며, 알 수 없는 버전을 임의 변환하지 않습니다.

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

Python 엔진만 독립 실행 파일로 만들려면 각 운영체제에서 빌드해야 합니다.

```bash
python3 -m pip install pyinstaller
python3 build_app.py
```

macOS 빌드는 macOS 앱을, Windows 빌드는 Windows `.exe`를 생성합니다.
