"""Compatibility shim for canonical J-Assist MCP identity adapter."""
from pathlib import Path as _Path
import sys as _sys
_root = _Path(__file__).resolve().parents[2] / "implementation"
if str(_root) not in _sys.path:_sys.path.insert(0,str(_root))
from jassist.mcp_identity_adapter import *
