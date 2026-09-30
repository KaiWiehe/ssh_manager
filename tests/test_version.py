from __future__ import annotations

import re
from pathlib import Path

from ssh_manager_app.version import APP_DISPLAY_NAME, APP_NAME, APP_VERSION


ROOT = Path(__file__).resolve().parent.parent
WINDOWS_VERSION_FILE = ROOT / "packaging" / "ssh_manager_version_info.txt"


def test_app_version_is_semantic_and_used_in_display_name() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
    assert APP_DISPLAY_NAME == f"{APP_NAME} v{APP_VERSION}"


def test_windows_metadata_matches_app_version() -> None:
    source = WINDOWS_VERSION_FILE.read_text(encoding="utf-8")
    major, minor, patch = APP_VERSION.split(".")

    assert f"filevers=({major}, {minor}, {patch}, 0)" in source
    assert f"prodvers=({major}, {minor}, {patch}, 0)" in source
    assert f"StringStruct('FileVersion', '{APP_VERSION}')" in source
    assert f"StringStruct('ProductVersion', '{APP_VERSION}')" in source
