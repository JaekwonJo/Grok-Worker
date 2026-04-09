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
001 : @S999 sits, @S998 stands. dramatic lighting
|||

002 : @S997 looks shocked, @S999 points forward.
|||
```

실제 입력창에는 자동으로 이렇게 들어갑니다.

```txt
S001 Prompt : @S999 sits, @S998 stands. dramatic lighting
```

즉:

- `001`은 작업 번호
- `@S999`, `@S998`는 Grok에 미리 올려 둔 이미지 이름
- 실제 입력창에는 `@`가 유지된 본문이 들어감
- 실행할 때 `+` 패널에서 같은 이름 이미지를 찾아 자동 선택함

## 보관 상태인 예전 앱

아래 파일들은 참고용으로 남겨둔 standalone 버전입니다.

- `main.py`
- `grok_worker/`
- `0_원터치_설치+실행.bat`
- `1_필수라이브러리_설치.bat`
- `2_Grok_Worker_실행.bat`
- `Grok_Start.vbs`

이쪽은 더 이상 주 개발축이 아닙니다.
