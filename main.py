from pathlib import Path

from grok_worker.ui import GrokWorkerApp


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    app = GrokWorkerApp(base_dir)
    app.run()


if __name__ == "__main__":
    main()

