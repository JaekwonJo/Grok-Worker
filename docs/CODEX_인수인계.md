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
- IndexedDB 기반 레퍼런스 이미지 저장
- 이름 저장 / 삭제
- 연속 / 개별 번호 실행 선택
- 현재 Grok 탭을 대상으로 background -> content 실행 메시지 전달
- 이미지 첨부 / 프롬프트 입력 / 화살표 제출 / 다운로드 버튼 탐색 1차 연결
- 다운로드 파일명은 `chrome.downloads.onDeterminingFilename`으로 제안

## 현재 프롬프트 규칙

```txt
001 : @S999 sits, @S998 stands. dramatic lighting
|||
```

실행 시:

- 레퍼런스 이미지 라이브러리에서 `S999`, `S998`를 찾음
- 현재 프롬프트에 그 이미지를 첨부
- 입력창에는 `S001 Prompt : S999 sits, S998 stands. dramatic lighting`처럼 `@`를 뺀 텍스트를 넣음

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
2. 레퍼런스 이미지 업로드 후 페이지에 실제 첨부되는지 실사용 확인
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
