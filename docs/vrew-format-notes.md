# Vrew 4.3.x 프로젝트 형식 메모

이 문서는 샘플 프로젝트와 Vrew 4.3.3 앱 코드를 대조해 확인한 구현 계약입니다.

## 컨테이너

`.vrew`는 ZIP 컨테이너입니다.

```text
project.json
media/<media-id>.<extension>
```

`project.json`의 주요 데이터는 다음과 같습니다.

- `transcript.clips`: 클립, 자막, TTS 단어와 클립 오버레이 자산
- `props.tracks`: 이미지·영상·텍스트·TTS 트랙
- `props.assets`: 여러 트랙을 묶어 클립이나 단어에 연결하는 자산
- `files`: `media/*` 파일의 메타데이터
- `integrity`: 프로젝트 JSON의 SHA-256

## 무결성

Vrew 4.3.3은 다음 순서로 무결성을 계산합니다.

1. 각 `files[]`에서 `path` 제거
2. `integrity`를 빈 문자열로 설정
3. JavaScript `JSON.stringify`와 같은 compact JSON 직렬화
4. UTF-8 바이트의 SHA-256

도구는 원본을 읽을 때와 출력 복제본을 다시 열 때 이 값을 모두 검사합니다.

## 이미지와 Ken Burns

이미지 하나는 `files[]`의 Image 항목과 `props.tracks`의 image 트랙으로
등록됩니다. 특정 구간마다 별도의 sub asset과 image track을 만들고, 그
asset ID를 구간 내 모든 `transcript.clips[].assetIds`에 넣습니다.

확인한 6개 `kenburnsAnimationInfo.type`:

- `zoom-in`
- `zoom-out`
- `left-to-right`
- `right-to-left`
- `top-to-bottom`
- `bottom-to-top`

완성된 참조 프로젝트와 같은 방식으로 이미지를 먼저 전 구간에 연결한 후
애니메이션 속성을 배치 적용합니다.

## 클립 재분배

AI 음성 프로젝트는 동일한 `sceneId`를 긴 범위에서 공유할 수 있으므로,
`sceneId`만으로 TTS 문장 단위를 판단하면 안 됩니다. 각 단어의
`originalStartTime`이 이전 클립보다 작아지는 지점을 TTS 시간축 리셋으로
간주합니다.

재분배 시:

- type 0 단어와 뒤따르는 type 1 공백을 보존
- type 2 종료 마커를 새 클립 끝에 다시 생성
- word ID와 word-level main asset 연결을 보존
- 자막 토큰과 TTS 단어가 일치하지 않으면 해당 단위를 수정하지 않고 보고
- narration/dialogue 및 서로 다른 따옴표 발화를 넘지 않도록 분리

## 동영상 후처리

동영상은 동일 media ID를 참조하는 video track과 선택적 videoAudio track을
한 sub asset으로 묶습니다. 이 도구의 인트로·구독·아웃트로는 기존 클립
범위에 이 sub asset을 연결하는 오버레이 방식입니다.
