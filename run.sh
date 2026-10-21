#!/usr/bin/env bash
set -e

echo "1. run"
echo "2. lint"
echo "3. test"
echo "4. install (안정 버전 전역 설치)"
read -rp "번호 선택: " choice

case "$choice" in
    1) uv run yunhee ;;
    2) uv run ruff check . ;;
    3) uv run pytest ;;
    4) uv tool install --force . ;;
    *) echo "잘못된 번호입니다: $choice" ; exit 1 ;;
esac
