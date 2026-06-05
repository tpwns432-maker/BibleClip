"""Best-effort anonymous 'app launched' ping (실사용 카운터, Phase 1).

Fire-and-forget in a daemon thread: any network/SSL/timeout error is swallowed
(FAIL-OPEN) so a launch is never delayed or blocked, and an offline user is
unaffected. No personal data is sent — just an anonymous GET with a generic
User-Agent. The endpoint is config.USAGE_PING_URL (set to None to disable, or
repoint at a dedicated analytics/count service).
"""
import threading
import urllib.request

from bibleclip.config import USAGE_PING_URL, __version__


def _ping(url):
    if not url:
        return
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"BibleClip/{__version__}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read(1)  # touch the response, then drop it
    except Exception:
        pass  # fail-open: never surface a launch-time network error


def ping_usage_async(url=USAGE_PING_URL):
    """Fire the usage ping on a background daemon thread (non-blocking). Returns
    the thread (or None if it couldn't start) — callers can ignore it."""
    try:
        t = threading.Thread(target=_ping, args=(url,), daemon=True)
        t.start()
        return t
    except Exception:
        return None
