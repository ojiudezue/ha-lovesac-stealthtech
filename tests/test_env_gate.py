"""B-HIGH-1 gate: a silent HA-layer skip must fail the run.

test_v0_3.py and test_ha_layer.py self-skip at module level on Python < 3.10
(their modules need kw_only dataclasses). Before this gate, running the suite
on python3.9 reported green while silently dropping 56 tests. This test always
runs and mirrors the exact skip condition: on an old interpreter it FAILS
loudly unless LOVESAC_ALLOW_PY39_SKIP=1 explicitly accepts the reduced run.
"""
import os
import sys

import pytest


def test_ha_layer_modules_not_silently_skipped():
    if sys.version_info >= (3, 10):
        return  # the HA-layer modules ran; nothing to gate
    if os.environ.get("LOVESAC_ALLOW_PY39_SKIP") == "1":
        pytest.skip(
            "HA-layer tests (test_v0_3.py + test_ha_layer.py) skipped on "
            "Python %d.%d — explicitly allowed via LOVESAC_ALLOW_PY39_SKIP=1"
            % sys.version_info[:2]
        )
    pytest.fail(
        "Python %d.%d silently skips the HA-layer tests in test_v0_3.py and "
        "test_ha_layer.py (they require Python >= 3.10). Run the suite with "
        ".venv313 (see README 'Development'), or set LOVESAC_ALLOW_PY39_SKIP=1 "
        "to accept the pure-protocol subset." % sys.version_info[:2]
    )
