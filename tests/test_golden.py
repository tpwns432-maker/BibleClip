"""Fails when tests/golden/*.json no longer match the Python engine.

Run with:  python -X utf8 tests/test_golden.py

The Android port is tested against these files (docs/ANDROID_PLAN.md), so an
engine change that skips `python -X utf8 tests/make_golden.py` would leave the
Kotlin side checking stale expectations. This catches that.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_golden

if __name__ == '__main__':
    rc = make_golden.main(check=True)
    print('GOLDEN CHECK PASSED ✅' if rc == 0 else 'GOLDEN CHECK FAILED ❌')
    sys.exit(rc)
