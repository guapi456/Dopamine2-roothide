#!/usr/bin/env python3
"""Verify the final TIPA changes only the main application identity."""

from __future__ import annotations

import hashlib
import plistlib
import sys
import zipfile
from pathlib import Path

MAIN_ID = "com.departure.launcher"
OFFICIAL_DEB_SHA256 = {
    "sileo.deb": "E85AB12F8D98DA9A5350293647266B898282B0D766DF2397526AB253D84EEDE3",
    "roothideapp.deb": "B8F075E1844709845962900B22FE71136A66369A2C35BB1201087F2FD9476B7D",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_mainonly_build.py <tipa>")
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

        for filename, expected_hash in OFFICIAL_DEB_SHA256.items():
            path = f"Payload/Dopamine.app/{filename}"
            actual_hash = sha256(archive.read(path))
            if actual_hash != expected_hash:
                raise ValueError(
                    f"{filename} differs from upstream: {actual_hash} != {expected_hash}"
                )
            print(f"{filename}=OFFICIAL sha256={actual_hash}")

    print(f"TIPA verification passed: {tipa}")
    print("main=com.departure.launcher display=出发 app=Dopamine.app executable=Dopamine")
    print("store=OFFICIAL org.coolstar.SileoStore app=Sileo.app package=org.coolstar.sileo")
    print("manager=OFFICIAL com.roothide.manager app=RootHide.app package=com.roothide.manager")


if __name__ == "__main__":
    main()
