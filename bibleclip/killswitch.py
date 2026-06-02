"""Remote kill switch: lets the maintainer disable distributed copies.

At startup the app fetches a small JSON manifest from a public URL
(config.KILLSWITCH_URL). When the manifest says this build is disabled
— globally ("disabled": true) or below a minimum version ("min_version")
— the app refuses to run and shows the manifest's message.

By design this is FAIL-OPEN: any network / SSL / parse error is treated as
"not blocked", so a GitHub outage or an offline user never bricks the app.
Only a positive, well-formed "disabled"/"min_version" signal blocks it, and
flipping the manifest back revives every copy on its next launch.

Reuses bibleclip.update's resilient SSL/urlopen handling and version parser.
"""
import json
import urllib.request

from bibleclip.config import KILLSWITCH_URL, __version__
from bibleclip.update import urlopen_resilient, parse_version

DEFAULT_BLOCK_MESSAGE = (
    "이 버전은 더 이상 사용할 수 없습니다.\n관리자에게 문의하세요."
)


def _fetch_manifest(timeout):
    """Fetch and JSON-decode the kill-switch manifest. Raises on any failure."""
    req = urllib.request.Request(KILLSWITCH_URL, headers={
        'User-Agent': f'BibleClip/{__version__}',
        'Accept': 'application/json',
        # Ask the CDN not to serve a stale copy so a freshly-flipped switch
        # propagates as fast as the raw cache allows.
        'Cache-Control': 'no-cache',
    })
    with urlopen_resilient(req, timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def check_killswitch(timeout=6):
    """Return (blocked, message).

    blocked is True only when the remote manifest positively says so:
      - "disabled": true            -> block every build that has this check
      - "min_version": "1.6.0"      -> block builds older than that

    Any error (no network, SSL, bad JSON, wrong shape) returns (False, '')
    — fail-open, never block on uncertainty.
    """
    try:
        data = _fetch_manifest(timeout)
    except Exception:
        return False, ''
    if not isinstance(data, dict):
        return False, ''

    message = data.get('message') or DEFAULT_BLOCK_MESSAGE

    if data.get('disabled') is True:
        return True, message

    min_version = data.get('min_version')
    if min_version:
        try:
            if parse_version(__version__) < parse_version(min_version):
                return True, message
        except Exception:
            return False, ''

    return False, ''
