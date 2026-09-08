#!/usr/bin/env python3
"""Verify main identity plus display-only Sileo/RootHide relabeling."""

from __future__ import annotations

import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path

import relabel_bundled_apps as relabel

MAIN_ID = "com.departure.launcher"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_compat_build.py <tipa>")
    tipa = Path(sys.argv[1]).resolve()
    if not tipa.is_file():
        raise ValueError(f"missing TIPA: {tipa}")

    with zipfile.ZipFile(tipa) as archive:
        names = set(archive.namelist())
        required = {
            "Payload/Dopamine.app/Info.plist",
            "Payload/Dopamine.app/Dopamine",
            "Payload/Dopamine.app/sileo.deb",
            "Payload/Dopamine.app/roothideapp.deb",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"TIPA is missing official paths: {missing!r}")
        if any(name.startswith("Payload/Dop.app/") for name in names):
            raise ValueError("custom Dop.app path must not remain")

        info = plistlib.loads(archive.read("Payload/Dopamine.app/Info.plist"))
        expected = {
            "CFBundleIdentifier": MAIN_ID,
            "CFBundleDisplayName": "出发",
            "CFBundleName": "Dopamine",
            "CFBundleExecutable": "Dopamine",
        }
        actual = {key: info.get(key) for key in expected}
        if actual != expected:
            raise ValueError(f"incorrect main app metadata: {actual!r}")

        with tempfile.TemporaryDirectory(prefix="departure-compat-verify-") as temp_dir:
            temp = Path(temp_dir)
            for filename, spec in (
                ("sileo.deb", relabel.STORE),
                ("roothideapp.deb", relabel.CLEANER),
            ):
                path = f"Payload/Dopamine.app/{filename}"
                extracted = temp / filename
                extracted.write_bytes(archive.read(path))
                relabel.verify_deb(extracted, spec)

    print(f"TIPA verification passed: {tipa}")
    print("main=com.departure.launcher display=出发 app=Dopamine.app executable=Dopamine")
    print("store=org.coolstar.SileoStore display=商店 app=Sileo.app executable=Sileo package=org.coolstar.sileo")
    print("manager=com.roothide.manager display=清理 app=RootHide.app executable=RootHide package=com.roothide.manager")


if __name__ == "__main__":
    main()
