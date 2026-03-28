import os
import subprocess
import sys
import time
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
    print(f"\n=== {step_name} ===", flush=True)
    started_at = time.time()
    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"

    result = subprocess.run(
        [sys.executable, "-u", str(BASE_DIR / script_path)],
        cwd=BASE_DIR,
        env=child_env,
    )

    elapsed_seconds = round(time.time() - started_at, 1)
    print(f"Finished {step_name} in {elapsed_seconds} seconds", flush=True)

    if result.returncode != 0:
        print(f"\nStopped because this step failed: {step_name}", flush=True)
        sys.exit(result.returncode)


def main():
    for step_name, script_path in SCRIPTS:
        run_step(step_name, script_path)

    print("\nDaily competitor news run completed successfully.", flush=True)


if __name__ == "__main__":
    main()
