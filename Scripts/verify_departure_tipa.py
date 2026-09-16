#!/usr/bin/env python3
"""Fail CI unless the final TIPA carries the complete Departure identity set.

Checks the main app bundle plus both embedded Debian packages. Debian package
IDs and every application directory must stay at their upstream values; only
display names and the main app bundle identifier are expected to change.
"""

from __future__ import annotations

import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path

import repack_display_names as relabel

MAIN_BUNDLE_ID = "com.departure.launcher"
MAIN_DISPLAY = "出发"
MAIN_APP_DIR = "Payload/Dopamine.app"


def check_main_app(archive: zipfile.ZipFile, names: set[str]) -> None:
    info_name = f"{MAIN_APP_DIR}/Info.plist"
    executable_name = f"{MAIN_APP_DIR}/Dopamine"
    for required in (info_name, executable_name):
        if required not in names:
            raise ValueError(f"TIPA omits {required}")

    info = plistlib.loads(archive.read(info_name))
    expected = {
        "CFBundleIdentifier": MAIN_BUNDLE_ID,
        "CFBundleDisplayName": MAIN_DISPLAY,
        "CFBundleName": MAIN_DISPLAY,
        "CFBundleExecutable": "Dopamine",
    }
    actual = {key: info.get(key) for key in expected}
    if actual != expected:
        raise ValueError(f"incorrect main app metadata: {actual!r}")

    stale = "com.opa334.Dopamine-roothide"
    blob = archive.read(executable_name)
    if stale.encode() in blob:
        raise ValueError(f"main executable still embeds {stale}")


def check_deb(archive: zipfile.ZipFile, spec: relabel.DebSpec, temp: Path) -> None:
    archive_path = f"{MAIN_APP_DIR}/{spec.deb_name}"
    if archive_path not in archive.namelist():
        raise ValueError(f"TIPA omits {archive_path}")
    extracted = temp / spec.deb_name
    extracted.write_bytes(archive.read(archive_path))
    relabel.verify(extracted, spec)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_departure_tipa.py <tipa>")
    tipa = Path(sys.argv[1]).resolve()
    if not tipa.is_file():
        raise SystemExit(f"missing TIPA: {tipa}")

    with zipfile.ZipFile(tipa) as archive:
        names = set(archive.namelist())
        check_main_app(archive, names)
        with tempfile.TemporaryDirectory(prefix="departure-tipa-verify-") as temp_dir:
            temp = Path(temp_dir)
            for spec in (relabel.STORE, relabel.CLEANER):
                check_deb(archive, spec, temp)

    print(f"TIPA verification passed: {tipa}")
    print(f"main    = {MAIN_BUNDLE_ID} app=Dopamine.app exec=Dopamine display={MAIN_DISPLAY}")
    print("store   = org.coolstar.SileoStore app=Sileo.app exec=Sileo display=商店 package=org.coolstar.sileo")
    print("cleaner = com.roothide.manager app=RootHide.app exec=RootHide display=清理 package=com.roothide.manager")


if __name__ == "__main__":
    main()
