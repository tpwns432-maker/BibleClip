"""Headless test for the remote kill switch (bibleclip.killswitch).

Run with:  python -X utf8 tests/test_killswitch.py

Never touches the network: _fetch_manifest is swapped for an in-memory stub.
Verifies the fail-open contract (any error -> not blocked) and the two block
signals (disabled / min_version).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bibleclip.killswitch as ks
from bibleclip.config import __version__


def with_manifest(value):
    """Make _fetch_manifest return `value` (a dict, or any shape to test)."""
    ks._fetch_manifest = lambda timeout: value


def with_error(exc):
    """Make _fetch_manifest raise `exc` (simulates network/SSL failure)."""
    def boom(timeout):
        raise exc
    ks._fetch_manifest = boom


def main():
    # disabled: true -> blocked, with the manifest's message
    with_manifest({'disabled': True, 'message': '중단되었습니다'})
    blocked, msg = ks.check_killswitch()
    assert blocked is True and msg == '중단되었습니다', (blocked, msg)
    print("disabled:true -> blocked with custom message")

    # disabled: false -> not blocked
    with_manifest({'disabled': False, 'min_version': '0.0.0'})
    assert ks.check_killswitch() == (False, ''), ks.check_killswitch()
    print("disabled:false -> runs")

    # min_version above the current build -> blocked (default message used)
    with_manifest({'min_version': '999.0.0'})
    blocked, msg = ks.check_killswitch()
    assert blocked is True and msg == ks.DEFAULT_BLOCK_MESSAGE, (blocked, msg)
    print(f"min_version 999.0.0 (> {__version__}) -> blocked")

    # min_version at/below the current build -> not blocked
    with_manifest({'min_version': '0.0.1'})
    assert ks.check_killswitch()[0] is False, ks.check_killswitch()
    print(f"min_version 0.0.1 (<= {__version__}) -> runs")

    # network/SSL error -> fail-open
    with_error(OSError('no route to host'))
    assert ks.check_killswitch() == (False, ''), "network error must fail-open"
    print("network error -> fail-open (runs)")

    # malformed payload (not a dict) -> fail-open
    with_manifest("disabled")
    assert ks.check_killswitch() == (False, ''), "bad payload must fail-open"
    print("non-dict payload -> fail-open (runs)")

    # empty / missing keys -> not blocked
    with_manifest({})
    assert ks.check_killswitch() == (False, ''), ks.check_killswitch()
    print("empty manifest -> runs")

    print("\nALL KILLSWITCH CHECKS PASSED ✅")


if __name__ == '__main__':
    main()
    sys.stdout.flush()
    os._exit(0)
