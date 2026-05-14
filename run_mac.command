#!/bin/zsh
set -e

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python이 설치되어 있지 않습니다. Python 3을 설치한 뒤 다시 실행해주세요."
  read "?Enter 키를 누르면 종료합니다."
  exit 1
fi

"$PYTHON_BIN" collect_notices.py --interactive

echo ""
read "?완료되었습니다. Enter 키를 누르면 종료합니다."
