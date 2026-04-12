# Grok Worker Codex 인수인계

## 현재 상태

- 2026-04-09: 방향 전환 완료
- standalone `Tkinter + Playwright` Grok Worker는 **보관용**
- 실제 개발 축은 `extension/` 폴더의 **브라우저 확장 프로그램**

## 왜 방향을 바꿨는가

- manual 브라우저에서는 `grok.com/imagine` 접속 가능
- 하지만 Playwright로 띄운 Chrome / Edge는 둘 다 Cloudflare `Sorry, you have been blocked`에 걸림
- 즉 standalone 자동화 브라우저 방식은 구조적으로 막힐 가능성이 매우 큼
- 그래서 사용자의 실제 브라우저 탭 안에서 동작하는 확장 프로그램으로 변경

## 현재 구현됨

- `extension/manifest.json`
- `extension/sidepanel.html`
- `extension/sidepanel.css`
- `extension/sidepanel.js`
- `extension/background.js`
- `extension/content.js`
- `extension/lib/prompt-parser.js`
- `extension/lib/ref-db.js`

## 현재 확장 프로그램 기능

- 사이드패널 UI
- 프롬프트 텍스트 입력 / `.txt` 불러오기
- `001 : 본문 |||` 파서
- `@S999`, `@S998` 같은 이름형 레퍼런스 토큰 파싱
- IndexedDB 기반 레퍼런스 이름 메모
- 연속 / 개별 번호 실행 선택
- 현재 Grok 탭 줌 80% 기본 적용 (`chrome.tabs.setZoom`)
- 현재 Grok 탭을 대상으로 background -> content 실행 메시지 전달
- 미리 올린 이미지 검색/선택 / 프롬프트 입력 / 화살표 제출 / 다운로드 버튼 탐색 1차 연결
- 다운로드 파일명은 `chrome.downloads.onDeterminingFilename`으로 제안

## 현재 프롬프트 규칙

```txt
001 : @S999 sits, @S998 stands. dramatic lighting
|||
```

실행 시:

- Grok의 `+` 패널에서 `S999`, `S998` 이름이 보이는 미리 올린 이미지를 검색
- 현재 프롬프트에 그 이미지를 선택
- 입력창에는 `S001 Prompt : @S999 sits, @S998 stands. dramatic lighting`처럼 `@`를 유지한 텍스트를 넣음

## 지금 꼭 알아둘 점

- 아직 `완성품`은 아님
- 현재 자동화는 1차 DOM 휴리스틱 버전
- Grok UI가 바뀌면 `content.js`의 탐색기부터 다시 맞춰야 함
- 특히:
  - `+` 버튼
  - 파일 입력칸
  - 화살표 제출
  - 결과 카드
  - 다운로드 버튼
  후보 탐색은 계속 다듬어야 함

## 다음 구현 순서

1. 사이드패널 UI 더 컴팩트하게 정리
2. Grok에 미리 올린 이미지 검색/선택이 실제로 붙는지 실사용 확인
3. 제출 뒤 결과 카드 선택 안정화
4. 다운로드 완료 검증 / 실패 재시도 / 실패 번호 복붙 고도화
5. 필요 시 `@S999` 토큰을 유지할지, `S999`만 남길지 사용자 테스트 후 조정

## 보관용 파일

아래는 더 이상 주 개발축은 아니지만 참고용으로 남겨둔 파일이다.

- `main.py`
- `grok_worker/`
- `0_원터치_설치+실행.bat`
- `1_필수라이브러리_설치.bat`
- `2_Grok_Worker_실행.bat`
- `Grok_Start.vbs`

## 최근 업데이트

- 2026-04-09: Grok 자동화는 standalone Playwright 앱 대신 브라우저 확장 프로그램으로 방향을 전환
- 2026-04-09: extension 폴더에 Manifest V3 구조, sidepanel, background, content script, 레퍼런스 이미지 IndexedDB, `001 : 본문 |||` 파서를 추가
- 2026-04-09: 레퍼런스 토큰은 이제 `@1~@5`가 아니라 `@S999`, `@S998` 같은 이름형 별칭을 기준으로 저장/매칭하도록 방향을 변경
- 2026-04-09: 레퍼런스 이미지는 확장 프로그램이 직접 업로드하지 않고, Grok 화면에 미리 올려 둔 이미지 이름(`@S999`)을 검색해서 선택하는 흐름으로 변경
- 2026-04-12: 보관용 standalone `Grok Worker`에 `기존 Edge 창 연결` 테스트 모드 추가. UI에 `브라우저 방식 / 기존 Edge 연결 주소`를 넣었고, Playwright `connect_over_cdp`로 이미 켜져 있는 Edge에 붙도록 분기
- 2026-04-12: 위 모드는 사용 중인 다른 탭을 강제로 바꾸지 않도록, 기존 Edge 안에 이미 `grok.com` 탭이 있으면 그 탭을 우선 쓰고, 없으면 같은 브라우저 안에 새 탭을 열도록 안전하게 보강
- 2026-04-12: 위 모드는 `아무 Edge 창`에 그냥 붙는 방식은 아니고, Edge가 미리 `--remote-debugging-port=9222` 같은 디버그 포트로 켜져 있어야 함
- 2026-04-12: standalone `Grok Worker` 화면에서 `작업봇 창 열기 / 시작` 버튼이 아래로 밀려 안 보이던 문제를 줄이기 위해, 하단 실행줄을 설정 카드 위쪽으로 옮겨 작은 창에서도 먼저 보이게 조정
- 2026-04-12: 사용자가 명령어를 직접 치지 않아도 되게, `3_기존Edge_그록연결용_열기.bat` 파일 추가. 이 파일을 더블클릭하면 `--remote-debugging-port=9222`로 Edge와 `grok.com/imagine`를 쉽게 열 수 있게 정리
- 2026-04-12: Windows CMD 한글 깨짐 대응으로 배치 내용을 전부 ASCII로 다시 바꾸고, 같은 내용의 `3_open_edge_for_grok.cmd`도 추가
- 2026-04-12: 일부 Windows CMD 환경에서 경로/괄호/문자열 처리까지 같이 깨지는 경우가 있어, 실행 파일을 다시 `start "" msedge --remote-debugging-port=9222 https://grok.com/imagine` 한 줄짜리 최소 버전으로 단순화
- 2026-04-12: standalone `Grok Worker` 프롬프트 파서를 `001 : 본문` 재조립 방식에서, Flow Classic Plus 이미지 워커처럼 `S001 Prompt : ...` 원문 유지 방식으로 변경. 자동 입력도 `@` 토큰 분해 없이 원문 전체를 한 번에 그대로 입력하게 수정
- 2026-04-12: 위 파서를 다시 그록워커 방식에 맞게 보강. `S001 Prompt : ...` 원문은 유지하되, 그 안의 `@1~@5`는 Grok 입력창의 `@` 메뉴에서 `Image 1~5`를 실제 클릭 선택하도록 복구
- 2026-04-12: `9222` 포트가 안 열리는 경우를 줄이기 위해 `3_open_edge_for_grok.cmd` / `3_기존Edge_그록연결용_열기.bat`를 다시 수정. 이제 `runtime/edge_attach_profile` 전용 프로필과 `--new-window`를 함께 써서 기존 Edge 세션과 덜 섞이게 전용 Edge를 강제로 띄우도록 조정
- 2026-04-12: 사용 흐름 단순화를 위해 standalone `Grok Worker`의 기본 브라우저 모드를 항상 `기존 Edge 창 연결(edge_attach)`로 고정. 프로그램을 다시 켜도 다른 모드 저장값은 무시하고 항상 이 모드로 시작하게 변경
- 2026-04-12: `logs/` 폴더에 실행별 상세 로그 파일이 자동 생성되도록 추가. `+ 패널 열기`, `+ 패널 이미지 선택`, `제출 버튼 후보`, 실패 스크린샷까지 남겨 원인 추적이 쉬워지게 보강
- 2026-04-12: standalone `Grok Worker`는 이제 병렬 실행도 가능하도록 보강. `main.py`에 `--instance / --attach-url / --worker-name` 인자를 추가했고, 워커별 설정 파일을 `grok_worker_config_worker2.json`처럼 따로 저장하게 변경. `4_병렬_워커_실행.bat`, `5_병렬_워커_2개_실행.bat`, `6_병렬_워커_3개_실행.bat`로 Edge 9222/9223/9224와 워커 1/2/3을 한 번에 띄우는 흐름 추가
- 2026-04-12: standalone `Grok Worker`는 이제 실행 직후 연결 Edge를 자동으로 띄우고, 프로그램 종료 시 같은 디버그 포트 Edge도 같이 닫도록 보강. `browser.py`가 `--remote-debugging-port` 포트를 보고 Edge를 자동 실행/정리함
- 2026-04-12: standalone `Grok Worker`에 `이미지 / 비디오` 작업 모드를 추가. 비디오 모드에서는 `720p / 10s / 16:9` 같은 생성 옵션을 프롬프트 입력 전에 자동으로 맞추도록 보강
