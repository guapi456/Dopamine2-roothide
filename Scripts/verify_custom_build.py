#!/usr/bin/env python3
"""Fail CI unless the final TIPA contains the complete Departure identity set."""

from __future__ import annotations

import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path

import repack_bundled_apps as repack


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_custom_build.py <tipa>")
    tipa = Path(sys.argv[1]).resolve()
    if not tipa.is_file():
        raise SystemExit(f"missing TIPA: {tipa}")

    with zipfile.ZipFile(tipa) as archive:
        names = set(archive.namelist())
        info_name = "Payload/Dop.app/Info.plist"
        executable_name = "Payload/Dop.app/Dopamine"
        for required in (info_name, executable_name):
            if required not in names:
                raise ValueError(f"TIPA omits {required}")
        if any(name.startswith("Payload/Dopamine.app/") for name in names):
            raise ValueError("TIPA retains the official Dopamine.app wrapper")
        info = plistlib.loads(archive.read(info_name))
        expected = {
            "CFBundleIdentifier": repack.MAIN_BUNDLE_ID,
            "CFBundleDisplayName": "出发",
            "CFBundleName": "出发",
            "CFBundleExecutable": "Dopamine",
        }
        actual = {key: info.get(key) for key in expected}
        if actual != expected:
            raise ValueError(f"incorrect main app metadata: {actual!r}")

        with tempfile.TemporaryDirectory(prefix="departure-tipa-verify-") as temp_dir:
            temp = Path(temp_dir)
            for filename, spec in (("sileo.deb", repack.STORE), ("roothideapp.deb", repack.CLEANER)):
                archive_path = f"Payload/Dop.app/{filename}"
                if archive_path not in names:
                    raise ValueError(f"TIPA omits {archive_path}")
                extracted = temp / filename
                extracted.write_bytes(archive.read(archive_path))
                repack.verify_deb(extracted, spec)

    print(f"TIPA verification passed: {tipa}")
    print("main=com.departure.launcher wrapper=Dop.app display=出发")
    print("store=com.departure.marketapp app=Sileo.app display=商店 package=org.coolstar.sileo")
    print("cleaner=com.departure.cleaner app=RTHD.app display=清理 package=com.roothide.manager")


if __name__ == "__main__":
    main()
