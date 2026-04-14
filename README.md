# Grok Worker

Grok Imagine 전용 자동화 프로젝트입니다.

## 현재 실사용 기준

2026-04-13 현재 **사용자가 실제로 돌리는 기준은 standalone `Grok Worker` + 기존 Edge 연결 방식**입니다.

- 실제 사용 앱: `main.py` + `grok_worker/`
- 실제 사용 브라우저 방식: 사용자가 직접 연 Edge에 워커가 `connect_over_cdp`로 붙음
- 워커1/2/3 포트:
  - 워커1 `9222`
  - 워커2 `9223`
  - 워커3 `9224`
- 프롬프트 파일 요약 표시는 `001~100` 범위형이 아니라 실제 번호 목록 `001,004,007,010,090,100`처럼 보여야 정상

예전 문서에는 `extension/` 중심 설명이 많이 남아 있지만, 다음 Codex는 **지금 실사용 설명은 standalone 기준**으로 이해해야 합니다.
또한 `extension/` 폴더는 이제 **폐기 예정 참고 자료**로만 보고, 현재/앞으로의 실사용 본체로 취급하면 안 됩니다.

## 가장 먼저 읽을 문서

- [실사용 매뉴얼](docs/Grok_Worker_실사용_매뉴얼.md)
- [Codex 인수인계](docs/CODEX_인수인계.md)
- [Grok Worker 기획서](docs/Grok_Worker_기획서.md)

## 중요 방향 메모

- `extension/` 폴더는 **폐기 예정**입니다.
- 다음 Codex는 `extension`을 현재 본체나 주 개발축으로 이해하면 안 됩니다.
- 실제 유지/수정 대상은 계속 **standalone `Grok Worker` + `grok_worker/`** 입니다.
- 확장 프로그램 코드는 필요하면 참고만 하고, 실사용 기능 수정은 standalone 기준으로 해야 합니다.

## 문서

- [실사용 매뉴얼](docs/Grok_Worker_실사용_매뉴얼.md)
- [Grok Worker 기획서](docs/Grok_Worker_기획서.md)
- [Codex 인수인계](docs/CODEX_인수인계.md)
- [예시 프롬프트 파일](samples/grok_prompt_example.txt)

## 확장 프로그램 관련 주의

- `extension/`은 지금 실사용이 아닙니다.
- 새 세션에서 Codex가 이 부분을 보고 확장 프로그램 쪽으로 작업 방향을 잡으면 안 됩니다.
- 사용자가 현재 쓰는 것은 확장 프로그램이 아니라 standalone `Grok Worker`입니다.

## 프롬프트 형식

```txt
S001 Prompt : @S999 sits, @S998 stands. dramatic lighting |||
S002 Prompt : @S997 looks shocked, @S999 points forward. |||
```

standalone `Grok Worker` 테스트 모드는 현재 Flow Classic Plus 이미지 워커처럼
프롬프트 원문을 그대로 읽고 그대로 입력합니다.

추가로 2026-04-12 기준으로 standalone `Grok Worker`는:

- `이미지 / 비디오` 모드를 모두 지원합니다.
- 비디오 모드에서는 `480p / 720p`, `6s / 10s`, `16:9`를 자동으로 맞춥니다.
- Edge는 반드시 사용자가 먼저 직접 열고 로그인한 뒤 연결하는 방식으로 사용합니다.

## 병렬 실행

2026-04-13 현재 standalone `Grok Worker`는 병렬 실행도 지원합니다.

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

1. 먼저 Edge를 각 포트별로 직접 열기
   - 워커1: `3_open_edge_for_grok.cmd`
   - 워커2: `4_open_edge_for_worker2.cmd`
   - 워커3: `7_open_edge_for_worker3.cmd`
2. 각 Edge 창마다 서로 다른 계정으로 로그인
3. 그 다음 병렬 워커 배치파일 실행
4. 각 워커 창에서 프롬프트/저장폴더를 따로 설정
5. 동시에 실행

## 매우 중요한 실행 파일 규칙

- `3_open_edge_for_grok.cmd`, `4_open_edge_for_worker2.cmd`, `7_open_edge_for_worker3.cmd`는 이 프로젝트의 핵심 실행 파일입니다.
- 이 폴더 경로에는 공백(`Grok Worker`)이 있어서, CMD/VBS/python 래퍼를 조금만 잘못 바꿔도 Edge가 아예 안 뜨는 문제가 자주 납니다.
- 그래서 이 파일들을 수정했다면 반드시 실제 실행 테스트를 해야 합니다.
  - 권장 확인: 더블클릭 또는 `cmd /c call 3_open_edge_for_grok.cmd`
  - 워커2도 같은 방식으로 재확인
- `python edge_launcher.py ...` 같이 경로 인자가 섞이는 구조를 바꿀 때는 특히 주의해야 합니다.
- 실행 파일은 가능하면 최소 수정만 하고, 이미 잘 되던 호출 방식은 함부로 구조 변경하지 않는 것을 원칙으로 합니다.
- 실행 파일을 건드렸다면 실제 통과 기준은 아래입니다.
  - `3_open_edge_for_grok.cmd` 실행 시 Edge 창이 실제로 떠야 함
  - `4_open_edge_for_worker2.cmd`도 실제로 떠야 함
  - 문법 검사나 `--help`만으로 통과 처리하면 안 됨

## 최근 실사용 보강

- Edge 창은 이제 **위치는 자유**, **크기만 작업용으로 맞춤**
- 마지막 Edge 위치를 저장하고 다음 실행 때 재사용하도록 보강
- 다운로드 후 화면 중앙 클릭을 제거해서 앞 이미지가 다시 선택되는 문제를 줄임
- 상태 표시를 `20초 -> 19초 -> 18초` 식의 실시간 카운트다운으로 보강
- 대기열은 기본 크게, 로그 패널은 기본 숨김으로 보강
- 모드/비율 버튼 클릭 실패 시 전체 중단 대신 경고 후 계속 진행하도록 보강

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
- 워커2용 ASCII 실행용 파일: `4_open_edge_for_worker2.cmd`
- 워커3용 ASCII 실행용 파일: `7_open_edge_for_worker3.cmd`
