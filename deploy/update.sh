#!/usr/bin/env bash
# BibleClip 웹판 — 업데이트: 새 코드를 받고(git pull) 라이브러리 · 서비스를 맞춘 뒤 다시 켠다.
#
#   sudo /opt/bibleclip/deploy/update.sh
#
# 데이터(계정 · 글 · 노트 · 역본)는 /var/lib/bibleclip 에 있어 건드리지 않는다.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "관리자 권한으로 실행해 주세요:  sudo $0" >&2; exit 1; }

printf '\n\033[1m▶ 새 코드 받기\033[0m\n'
before="$(git -C "$APP_DIR" rev-parse --short HEAD)"
git -C "$APP_DIR" pull --ff-only
after="$(git -C "$APP_DIR" rev-parse --short HEAD)"
if [ "$before" = "$after" ]; then
  echo "  이미 최신입니다($after). 그래도 설정을 한 번 맞춥니다."
else
  echo "  $before → $after"
fi

# install.sh 가 바뀌었을 수 있으니 새로 받은 것을 실행한다.
exec "$APP_DIR/deploy/install.sh" --update
