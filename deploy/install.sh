#!/usr/bin/env bash
# BibleClip 웹판 — 리눅스 설치(다시 실행해도 안전). 안내서: docs/WEB_SETUP.md
#
#   sudo /opt/bibleclip/deploy/install.sh            처음 설치(계정 만들기까지)
#   sudo /opt/bibleclip/deploy/install.sh --update   업데이트 뒤 다시 맞추기(update.sh 가 부른다)
#
# 하는 일: Python 확인 → 전용 사용자 'bibleclip' · 데이터 폴더 → 가상환경 · 라이브러리 →
#          서비스 등록(systemd: 켜 두고, 꺼지면 다시 켜고, 재부팅 때 자동으로) → 계정 → 시작 확인.
# 앱은 이 컴퓨터(127.0.0.1)에만 열린다. 다른 기기는 deploy/tailscale.sh 로 연결한다.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${BIBLECLIP_DATA:-/var/lib/bibleclip}"
SVC_USER="bibleclip"
SERVICE="bibleclip-web"
VENV="$APP_DIR/.venv"
CONF_DIR="/etc/bibleclip"
CONF="$CONF_DIR/web.env"
UNIT="/etc/systemd/system/$SERVICE.service"
UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

say()  { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "관리자 권한으로 실행해 주세요:  sudo $0"
command -v systemctl >/dev/null || die "systemd 가 없는 리눅스입니다. 안내서의 '직접 실행'을 보세요."

# 이 사용자로 명령 실행(프로그램 폴더에서 — bibleclip 패키지를 찾게).
as_svc() { (cd "$APP_DIR" && runuser -u "$SVC_USER" -- "$@"); }

# ---- 1. Python ----
say "1/6 Python 확인"
py_ok() { command -v python3 >/dev/null && python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; }
if ! py_ok; then
  echo "  Python 3.9 이상(가상환경 포함)을 설치합니다."
  if command -v apt-get >/dev/null; then
    apt-get update -qq && apt-get install -y -qq python3 python3-venv
  elif command -v dnf >/dev/null; then
    dnf install -y -q python3
  elif command -v pacman >/dev/null; then
    pacman -Sy --noconfirm --needed python
  elif command -v zypper >/dev/null; then
    zypper --non-interactive install python3
  else
    die "Python 3.9 이상을 직접 설치한 뒤 다시 실행해 주세요."
  fi
  py_ok || die "Python 3.9 이상(venv 포함)을 찾지 못했습니다: $(python3 --version 2>&1 || true)"
fi
ok "$(python3 --version)"

# ---- 2. 전용 사용자 · 데이터 폴더 ----
say "2/6 사용자 '$SVC_USER' · 데이터 폴더 $DATA_DIR"
if ! id -u "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --no-create-home \
          --shell "$(command -v nologin || echo /usr/sbin/nologin)" "$SVC_USER"
  ok "사용자를 만들었습니다(로그인할 수 없는 서비스 전용)"
else
  ok "사용자가 이미 있습니다"
fi
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$DATA_DIR" "$DATA_DIR/bible_versions"
# 프로그램 폴더는 읽기만 하면 된다(고칠 수는 없게).
chmod -R o+rX "$APP_DIR"
as_svc test -r "$APP_DIR/bibleclip/server/__main__.py" \
  || die "'$SVC_USER' 사용자가 $APP_DIR 를 읽지 못합니다. 프로그램을 /opt/bibleclip 에 받아 주세요."
ok "데이터 폴더 준비됨"

# ---- 3. 가상환경 · 라이브러리 ----
say "3/6 가상환경 · 라이브러리(Flask, waitress)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/pip" install -q --disable-pip-version-check -r "$APP_DIR/requirements-server.txt"
chmod -R o+rX "$VENV"
ok "설치됨"

# ---- 4. 설정 파일 · 서비스 ----
say "4/6 서비스 등록($SERVICE)"
install -d -m 755 "$CONF_DIR"
if [ ! -f "$CONF" ]; then
  cat > "$CONF" <<EOF
# BibleClip 웹판 설정. 바꾼 뒤:  sudo systemctl restart $SERVICE
BIBLECLIP_PORT=8765
# Tailscale 로 연결하면 deploy/tailscale.sh 가 아래 줄을 채운다.
BIBLECLIP_ARGS=
EOF
  ok "설정 파일 $CONF"
fi
sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@DATA_DIR@|$DATA_DIR|g" \
    -e "s|@VENV@|$VENV|g" -e "s|@USER@|$SVC_USER|g" \
    "$APP_DIR/deploy/bibleclip-web.service" > "$UNIT"
systemctl daemon-reload
systemctl enable -q "$SERVICE"
ok "부팅 때 자동으로 켜지게 등록함"

# ---- 5. 계정 ----
say "5/6 계정"
count_users() { as_svc "$VENV/bin/python" -m bibleclip.server.accounts --data "$DATA_DIR" list | grep -c . || true; }
n="$(count_users)"
if [ "$n" -eq 0 ] && [ "$UPDATE" -eq 0 ]; then
  if [ ! -t 0 ]; then
    die "계정이 없습니다. 터미널에서 직접 실행해 주세요(아이디 · 비밀번호를 물어봅니다)."
  fi
  echo "  두 분의 계정을 만듭니다. 비밀번호는 화면에 보이지 않습니다."
  echo "  상대의 비밀번호는 임시로 정해 알려 주고, 상대가 홈 화면에서 직접 바꾸면 됩니다."
  while :; do
    read -rp "  아이디(영문 소문자 · 숫자, 예: sejun): " uid
    [ -n "$uid" ] || continue
    read -rp "  화면에 보일 이름(예: 세준): " uname
    if as_svc "$VENV/bin/python" -m bibleclip.server.accounts --data "$DATA_DIR" add "$uid" --name "${uname:-$uid}"; then
      n=$((n + 1))
    fi
    if [ "$n" -ge 2 ]; then break; fi
    read -rp "  계정을 하나 더 만들까요? [Y/n] " more
    case "$more" in [nN]*) [ "$n" -ge 1 ] && break ;; esac
  done
fi
[ "$(count_users)" -ge 1 ] || die "계정이 없어 시작할 수 없습니다."
ok "계정 $(count_users)개"

# ---- 6. 시작 ----
say "6/6 시작"
systemctl restart "$SERVICE"
# shellcheck disable=SC1090
PORT="$(. "$CONF"; echo "${BIBLECLIP_PORT:-8765}")"
for _ in $(seq 1 30); do
  if "$VENV/bin/python" - "$PORT" <<'PY' 2>/dev/null; then
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/login", timeout=2)
PY
    ok "켜졌습니다:  http://127.0.0.1:$PORT  (이 컴퓨터에서만)"
    ver="$(cd "$APP_DIR" && git describe --tags --always 2>/dev/null || true)"
    [ -n "$ver" ] && ok "버전 $ver"
    if ! grep -q -- '--allow-host' "$CONF"; then
      printf '\n  다음: 다른 기기에서 들어오려면 Tailscale 연결  →  sudo %s/deploy/tailscale.sh\n' "$APP_DIR"
    fi
    printf '  역본 넣기: %s/bible_versions/ 에 .SQLite3 파일을 넣고  sudo systemctl restart %s\n\n' "$DATA_DIR" "$SERVICE"
    exit 0
  fi
  sleep 1
done
systemctl --no-pager status "$SERVICE" | tail -n 15 || true
die "30초 안에 켜지지 않았습니다. 기록 보기:  journalctl -u $SERVICE -n 50"
