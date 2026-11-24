#!/usr/bin/env bash
# BibleClip 웹판 — 백업: 계정 · 두 사람의 설정 · 노트 · 형광펜 · 커뮤니티 글을 파일 하나(.tar.gz)로.
#
#   sudo /opt/bibleclip/deploy/backup.sh [저장할 폴더]      (기본: 실행한 사람의 집/bibleclip-backup)
#   sudo /opt/bibleclip/deploy/backup.sh --with-bibles     역본 파일(bible_versions)까지
#
# 켜 둔 채로 해도 된다: 커뮤니티 DB 는 SQLite 의 백업 기능으로 쓰는 중에도 온전하게 복사한다.
# 되돌리기는 docs/WEB_SETUP.md '백업 · 되돌리기'.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${BIBLECLIP_DATA:-/var/lib/bibleclip}"
VENV="$APP_DIR/.venv"
[ "$(id -u)" -eq 0 ] || { echo "관리자 권한으로 실행해 주세요:  sudo $0" >&2; exit 1; }

WITH_BIBLES=0
OUT_DIR=""
for a in "$@"; do
  case "$a" in
    --with-bibles) WITH_BIBLES=1 ;;
    *) OUT_DIR="$a" ;;
  esac
done
if [ -z "$OUT_DIR" ]; then
  home="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
  OUT_DIR="${home:-/root}/bibleclip-backup"
fi
mkdir -p "$OUT_DIR"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/db"
if [ -f "$DATA_DIR/community.db" ]; then
  "$VENV/bin/python" - "$DATA_DIR/community.db" "$tmp/db/community.db" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
src.close(); dst.close()
PY
fi

out="$OUT_DIR/bibleclip-$(date +%Y%m%d-%H%M%S).tar.gz"
excl=(--exclude=./community.db --exclude='./community.db-*')
[ "$WITH_BIBLES" -eq 1 ] || excl+=(--exclude=./bible_versions)
# 쓰는 중인 원본 DB 는 빼고 묶은 뒤, 안전하게 복사한 DB 를 따로 덧붙인다(빼기 규칙이 덧붙인 것엔 안 걸리게).
tar cf "$tmp/b.tar" -C "$DATA_DIR" "${excl[@]}" .
[ -f "$tmp/db/community.db" ] && tar rf "$tmp/b.tar" -C "$tmp/db" ./community.db
gzip -c "$tmp/b.tar" > "$out"
chmod 600 "$out"
[ -n "${SUDO_USER:-}" ] && chown "$SUDO_USER" "$out" "$OUT_DIR" 2>/dev/null || true
printf '\n  \033[32m✔\033[0m 백업: %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"
echo "    이 파일에는 계정 비밀번호 해시와 로그인 열쇠도 들어 있습니다. 남에게 주지 마세요."
