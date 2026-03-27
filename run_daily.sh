#!/bin/zsh

PROJECT_DIR="/Users/avramesh/Documents/AI Agents/Competitor-Research"
cd "$PROJECT_DIR" || exit 1

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" src/run_daily.py >> output/daily_run.log 2>&1
