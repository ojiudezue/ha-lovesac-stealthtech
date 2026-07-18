"""Test bootstrap.

Registers `lovesac_stealthtech` as a namespace-style package WITHOUT executing
its __init__.py (which imports Home Assistant). This lets the pure protocol
and BLE-session modules be tested with no HA install.
"""
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "lovesac_stealthtech"

pkg = types.ModuleType("lovesac_stealthtech")
pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("lovesac_stealthtech", pkg)
