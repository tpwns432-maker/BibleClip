#!/usr/bin/env bash
# BibleClip 웹판 — Tailscale 로 다른 기기에서 들어오게 하기. 안내서: docs/WEB_SETUP.md
#
#   sudo /opt/bibleclip/deploy/tailscale.sh
#
# Tailscale = 서버와 두 사람의 기기만 들어 있는 사설 통로. 인터넷 · 공유기 쪽으로는 아무것도 열지 않는다.
# 'tailscale serve' 가 https://<이 컴퓨터>.<사설망>.ts.net 으로 받아 앱(127.0.0.1)에 넘겨준다.
set -euo pipefail

SERVICE="bibleclip-web"
CONF="/etc/bibleclip/web.env"

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✔\033[0m %s\n' "$*"; }
die() { printf '\n\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "관리자 권한으로 실행해 주세요:  sudo $0"
[ -f "$CONF" ] || die "먼저 설치해 주세요:  sudo $(dirname "$0")/install.sh"
command -v tailscale >/dev/null || die "Tailscale 이 없습니다. 먼저 설치해 주세요:
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up"

say "1/3 Tailscale 상태"
STATUS="$(tailscale status --json 2>/dev/null)" || die "Tailscale 에 로그인해 주세요:  sudo tailscale up"
NAME="$(printf '%s' "$STATUS" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
[ -n "$NAME" ] || die "이 컴퓨터의 Tailscale 주소를 찾지 못했습니다. 관리 화면에서 MagicDNS 를 켜 주세요."
ok "이 컴퓨터의 주소: $NAME"

# 설정 파일은 실행하지 않고 글자로만 읽는다(값에 띄어쓰기가 있어도 안전하게).
PORT="$(sed -n 's/^BIBLECLIP_PORT=//p' "$CONF" | tail -n 1)"
PORT="${PORT:-8765}"

say "2/3 https 로 내보내기(tailscale serve)"
echo "  처음이면 Tailscale 이 'HTTPS 인증서 켜기' 링크를 보여 줄 수 있습니다. 링크를 열어 켠 뒤 다시 실행하세요."
tailscale serve --bg "http://127.0.0.1:$PORT"
ok "https://$NAME  →  이 컴퓨터의 앱"

say "3/3 앱 설정"
ARGS="--allow-host $NAME --behind-proxy --secure-cookie"
if grep -q '^BIBLECLIP_ARGS=' "$CONF"; then
  sed -i "s|^BIBLECLIP_ARGS=.*|BIBLECLIP_ARGS=$ARGS|" "$CONF"
else
  printf 'BIBLECLIP_ARGS=%s\n' "$ARGS" >> "$CONF"
fi
systemctl restart "$SERVICE"
ok "다시 켰습니다"

cat <<EOF

  ✔ 준비 끝.  주소:  https://$NAME

  이 주소는 Tailscale 에 연결된 기기에서만 열립니다.
  상대에게 열어 주기: Tailscale 관리 화면(https://login.tailscale.com/admin/machines)에서
  이 컴퓨터 옆 '…' → 'Share…' → 상대의 이메일. 상대는 Tailscale 앱을 깔고 초대를 받으면 됩니다.

EOF
