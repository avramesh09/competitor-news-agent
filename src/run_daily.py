import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = [
    ("Fetch news", "src/fetch_news.py"),
    ("Remove duplicates", "src/dedupe.py"),
    ("Filter with OpenAI", "src/filter_with_openai.py"),
    ("Generate brief", "src/generate_brief.py"),
    ("Send email", "src/send_email.py"),
]


def run_step(step_name, script_path):
    print(f"\n=== {step_name} ===")

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / script_path)],
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        print(f"\nStopped because this step failed: {step_name}")
        sys.exit(result.returncode)


def main():
    for step_name, script_path in SCRIPTS:
        run_step(step_name, script_path)

    print("\nDaily competitor news run completed successfully.")


if __name__ == "__main__":
    main()
