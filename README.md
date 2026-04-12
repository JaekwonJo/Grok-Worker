# Grok Worker

Grok Imagine 전용 자동화 프로젝트입니다.

지금은 방향이 바뀌었습니다.

- 예전 `Tkinter + Playwright` 기반 standalone `Grok Worker`는 **보관용**
- 새 본체는 `extension/` 폴더의 **브라우저 확장 프로그램**

이유는 간단합니다.

- x.ai / Grok은 Playwright 브라우저를 Cloudflare에서 빠르게 차단함
- 수동 브라우저는 되는데 자동화 브라우저만 막히는 상황이 실제로 확인됨
- 그래서 사용자 브라우저 안에서 직접 움직이는 **확장 프로그램 방식**이 더 현실적임

## 현재 목표

- Grok Imagine 탭 안에서만 동작하는 확장 프로그램
- 프롬프트 안의 `@S999`, `@S998` 같은 토큰을 읽어서
  - Grok 화면에 미리 올려 둔 같은 이름의 이미지를 검색해서 선택
  - 본문은 `S001 Prompt : ...` 형태로 자동 입력
- 전송/결과 확인/다운로드까지 같은 탭 안에서 처리

## 현재 상태

- `extension/` 폴더에 Manifest V3 확장 프로그램 골격 추가
- 사이드패널 UI 추가
- 레퍼런스 이름 메모용 IndexedDB 저장 구조 추가
- `001 : 본문 |||` 프롬프트 파서 JS 버전 추가
- `@S999`, `@S998` 같은 이름형 레퍼런스 토큰 파싱 추가
- background/content script 기본 실행 루프 추가
- 현재 Grok 탭 줌 80% 기본 적용 추가
- 현재 Grok 탭에
  - 미리 올린 이미지 검색/선택
  - 프롬프트 입력
  - 제출
  - 다운로드 버튼 탐색
  1차 휴리스틱 자동화 연결

## 문서

- [Grok Worker 기획서](docs/Grok_Worker_기획서.md)
- [Codex 인수인계](docs/CODEX_인수인계.md)
- [예시 프롬프트 파일](samples/grok_prompt_example.txt)

## 확장 프로그램 실행 방법

1. Edge 또는 Chrome에서 `확장 프로그램 관리` 페이지 열기
2. `개발자 모드` 켜기
3. `압축해제된 확장 프로그램 로드` 클릭
4. 이 폴더의 `extension/` 폴더 선택
5. Grok Imagine 탭 열기
6. 확장 프로그램 아이콘을 누르거나 사이드패널 열기

## 프롬프트 형식

```txt
S001 Prompt : @S999 sits, @S998 stands. dramatic lighting |||
S002 Prompt : @S997 looks shocked, @S999 points forward. |||
```

standalone `Grok Worker` 테스트 모드는 현재 Flow Classic Plus 이미지 워커처럼
프롬프트 원문을 그대로 읽고 그대로 입력합니다.

추가로 2026-04-12 기준으로 standalone `Grok Worker`는:

- 실행하면 연결된 Edge를 자동으로 띄웁니다.
- 창을 닫으면 연결된 Edge도 같이 닫습니다.
- `이미지 / 비디오` 모드를 모두 지원합니다.
- 비디오 모드에서는 `480p / 720p`, `6s / 10s`, `16:9`를 자동으로 맞춥니다.

## 병렬 실행

2026-04-12 기준으로 standalone `Grok Worker`는 병렬 실행도 지원합니다.

- 각 워커는 **설정 파일을 따로 저장**합니다.
- 각 워커는 **서로 다른 Edge 디버그 포트**에 붙을 수 있습니다.
- 예:
  - 워커1 -> `9222`
  - 워커2 -> `9223`
  - 워커3 -> `9224`

원클릭 파일:

- `4_병렬_워커_실행.bat`
- `5_병렬_워커_2개_실행.bat`
- `6_병렬_워커_3개_실행.bat`
- `4_parallel_workers.bat`
- `5_parallel_workers_2.bat`
- `6_parallel_workers_3.bat`

권장 사용 순서:

1. 위 배치파일 실행
2. 뜬 Edge 창마다 서로 다른 계정으로 로그인
3. 각 워커 창에서 프롬프트/저장폴더를 따로 설정
4. 동시에 실행

## 보관 상태인 예전 앱

아래 파일들은 참고용으로 남겨둔 standalone 버전입니다.

- `main.py`
- `grok_worker/`
- `0_원터치_설치+실행.bat`
- `1_필수라이브러리_설치.bat`
- `2_Grok_Worker_실행.bat`
- `Grok_Start.vbs`

이쪽은 더 이상 주 개발축이 아닙니다.

다만 2026-04-12 기준으로, standalone 앱에는 `기존 Edge 창 연결` 테스트 모드를 추가했습니다.

- 목적: 이미 사람이 로그인해서 쓰는 Edge 세션을 재사용할 수 있는지 확인
- 방식: `connect_over_cdp`
- 조건: Edge가 미리 원격 디버깅 포트로 켜져 있어야 함
- 예: `msedge.exe --remote-debugging-port=9222`
- 쉬운 실행용 파일: `3_기존Edge_그록연결용_열기.bat`
- CMD 한글 깨짐 대비 ASCII 실행용 파일: `3_open_edge_for_grok.cmd`
