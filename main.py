from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    print("Grok Worker 준비 중")
    print(f"프로젝트 경로: {root}")
    print("다음 단계: 기본 UI와 Playwright 자동화 구현")


if __name__ == "__main__":
    main()

