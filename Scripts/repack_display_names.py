#!/usr/bin/env python3
"""Relabel the bundled Sileo and RootHide payloads for the Departure build.

Only display names change. Bundle IDs, application directories, executables and
Debian package IDs stay at their upstream values so APT state, plugin
dependencies and RootHide's path-based logic keep working. Every Mach-O inside a
relabelled bundle is re-signed after Info.plist is rewritten.
"""

from __future__ import annotations

import argparse
import gzip
import io
import lzma
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "Application" / "Dopamine" / "Resources"

MAIN_BUNDLE_ID = "com.departure.launcher"

# Longest first: the shorter official IDs are prefixes of the longer one.
STALE_MAIN_BUNDLE_IDS = (
    "com.opa334.Dopamine.roothide",
    "com.opa334.Dopamine-roothide",
    "com.opa334.Dopamine",
)

MACHO_MAGICS = {
    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf",
    b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca",
}


@dataclass(frozen=True)
class DebSpec:
    deb_name: str
    package_id: str
    app_name: str
    executable: str
    new_display_name: str
    new_bundle_name: str
    clean_rules: bool = False


STORE = DebSpec(
    deb_name="sileo.deb",
    package_id="org.coolstar.sileo",
    app_name="Sileo",
    executable="Sileo",
    new_display_name="商店",
    new_bundle_name="Sileo",
)

CLEANER = DebSpec(
    deb_name="roothideapp.deb",
    package_id="com.roothide.manager",
    app_name="RootHide",
    executable="RootHide",
    new_display_name="清理",
    new_bundle_name="RootHide",
    clean_rules=True,
)


def read_ar(path: Path) -> list[tuple[str, bytes]]:
    raw = path.read_bytes()
    if raw[:8] != b"!<arch>\n":
        raise ValueError(f"{path} is not an ar archive")
    members: list[tuple[str, bytes]] = []
    offset = 8
    while offset < len(raw):
        header = raw[offset:offset + 60]
        if len(header) != 60 or header[-2:] != b"`\n":
            raise ValueError(f"invalid ar header in {path}")
        offset += 60
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        body = raw[offset:offset + size]
        if len(body) != size:
            raise ValueError(f"truncated ar member {name} in {path}")
        offset += size + (size & 1)
        members.append((name, body))
    return members


def write_ar(path: Path, members: Iterable[tuple[str, bytes]]) -> None:
    with path.open("wb") as archive:
        archive.write(b"!<arch>\n")
        for name, body in members:
            encoded = f"{name}/".encode("ascii")
            if len(encoded) > 16:
                raise ValueError(f"ar member name too long: {name}")
            header = (
                encoded.ljust(16, b" ")
                + b"0".ljust(12, b" ")
                + b"0".ljust(6, b" ")
                + b"0".ljust(6, b" ")
                + b"100644".ljust(8, b" ")
                + str(len(body)).encode("ascii").ljust(10, b" ")
                + b"`\n"
            )
            archive.write(header)
            archive.write(body)
            if len(body) & 1:
                archive.write(b"\n")


def decompress_tar(name: str, body: bytes) -> bytes:
    if name.endswith(".tar.gz"):
        return gzip.decompress(body)
    if name.endswith(".tar.xz"):
        return lzma.decompress(body)
    if name.endswith(".tar.lzma"):
        return lzma.decompress(body, format=lzma.FORMAT_ALONE)
    if name.endswith(".tar"):
        return body
    raise ValueError(f"unsupported tar member {name}")


def compress_tar(name: str, payload: bytes) -> bytes:
    if name.endswith(".tar.gz"):
        return gzip.compress(payload, mtime=0)
    if name.endswith(".tar.xz"):
        return lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)
    if name.endswith(".tar.lzma"):
        return lzma.compress(payload, format=lzma.FORMAT_ALONE, preset=6)
    if name.endswith(".tar"):
        return payload
    raise ValueError(f"unsupported tar member {name}")


def extract_tar(name: str, body: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(decompress_tar(name, body)), mode="r:") as archive:
        archive.extractall(destination, filter="fully_trusted")


def build_tar(source: Path) -> bytes:
    result = io.BytesIO()
    entries = sorted(source.rglob("*"), key=lambda p: (len(p.relative_to(source).parts), str(p)))
    # Procursus dpkg-deb accepts GNU/ustar headers but rejects Python's default PAX headers.
    with tarfile.open(fileobj=result, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for entry in entries:
            archive.add(entry, arcname=f"./{entry.relative_to(source).as_posix()}", recursive=False)
    return result.getvalue()


def is_macho(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(4) in MACHO_MAGICS


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sign_bundle(app: Path, ldid: str) -> int:
    signature_dir = app / "_CodeSignature"
    if signature_dir.exists():
        shutil.rmtree(signature_dir)
    signed = 0
    with tempfile.TemporaryDirectory(prefix="departure-entitlements-") as temp_dir:
        temp_root = Path(temp_dir)
        for candidate in sorted(app.rglob("*")):
            if not candidate.is_file() or candidate.is_symlink() or not is_macho(candidate):
                continue
            extracted = subprocess.run([ldid, "-e", str(candidate)], check=False, capture_output=True)
            if extracted.returncode == 0 and b"<plist" in extracted.stdout:
                entitlement_path = temp_root / f"{signed}.plist"
                entitlement_path.write_bytes(extracted.stdout)
                run([ldid, f"-S{entitlement_path}", str(candidate)])
            else:
                run([ldid, "-S", str(candidate)])
            signed += 1
    run([ldid, "-s", str(app)])
    return signed


def update_control(path: Path, spec: DebSpec) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    rewritten: list[str] = []
    for line in lines:
        if line.startswith("Name:"):
            rewritten.append(f"Name: {spec.new_display_name}")
            found = True
        else:
            rewritten.append(line)
    if not found:
        raise ValueError(f"control file has no Name field: {path}")
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def update_clean_rules(app: Path, spec: DebSpec) -> int:
    """Point RootHide's trace-cleaning rules at the new main app bundle ID.

    The cleaner deletes leftover files by bundle identifier, so the renamed main
    app must be listed or its preferences, caches and snapshots survive cleaning.
    """
    rules_path = app / "varCleanRules.json"
    if not rules_path.is_file():
        raise ValueError(f"missing cleaning rules: {rules_path}")
    text = rules_path.read_text(encoding="utf-8")
    replaced = 0
    for stale in STALE_MAIN_BUNDLE_IDS:
        replaced += text.count(stale)
        text = text.replace(stale, MAIN_BUNDLE_ID)
    if replaced == 0:
        raise ValueError(f"no stale main app identifiers found in {rules_path}")
    if MAIN_BUNDLE_ID not in text:
        raise ValueError(f"cleaning rules do not reference {MAIN_BUNDLE_ID}")
    rules_path.write_text(text, encoding="utf-8")
    return replaced


def update_info_plist(path: Path, spec: DebSpec) -> None:
    info = plistlib.loads(path.read_bytes())
    info["CFBundleDisplayName"] = spec.new_display_name
    info["CFBundleName"] = spec.new_bundle_name
    path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False))


def repack(path: Path, spec: DebSpec, ldid: str | None, skip_sign: bool = False) -> None:
    members = read_ar(path)
    member_map = dict(members)
    control_name = next((n for n, _ in members if n.startswith("control.tar")), None)
    data_name = next((n for n, _ in members if n.startswith("data.tar")), None)
    if control_name is None or data_name is None:
        raise ValueError(f"{path} lacks Debian control/data tarballs")

    with tempfile.TemporaryDirectory(prefix="departure-relabel-") as temp_dir:
        temp_root = Path(temp_dir)
        control_root = temp_root / "control"
        data_root = temp_root / "data"
        control_root.mkdir()
        data_root.mkdir()
        extract_tar(control_name, member_map[control_name], control_root)
        extract_tar(data_name, member_map[data_name], data_root)

        update_control(control_root / "control", spec)

        app = data_root / "Applications" / f"{spec.app_name}.app"
        if not app.is_dir():
            raise ValueError(f"missing app payload {app}")
        if not (app / spec.executable).is_file():
            raise ValueError(f"missing app executable {app / spec.executable}")
        update_info_plist(app / "Info.plist", spec)
        if spec.clean_rules:
            update_clean_rules(app, spec)

        if not skip_sign:
            if not ldid:
                raise ValueError("ldid is required to produce installable bundles")
            signed = sign_bundle(app, ldid)
            if signed == 0:
                raise ValueError(f"no Mach-O files found in {app}")

        repacked = []
        for name, body in members:
            if name == control_name:
                body = compress_tar(name, build_tar(control_root))
            elif name == data_name:
                body = compress_tar(name, build_tar(data_root))
            repacked.append((name, body))
        write_ar(path, repacked)


def verify(path: Path, spec: DebSpec) -> None:
    members = dict(read_ar(path))
    control_name = next(n for n in members if n.startswith("control.tar"))
    data_name = next(n for n in members if n.startswith("data.tar"))
    with tempfile.TemporaryDirectory(prefix="departure-verify-") as temp_dir:
        root = Path(temp_dir)
        control_root = root / "control"
        data_root = root / "data"
        control_root.mkdir()
        data_root.mkdir()
        extract_tar(control_name, members[control_name], control_root)
        extract_tar(data_name, members[data_name], data_root)

        for member_name in (control_name, data_name):
            with tarfile.open(fileobj=io.BytesIO(decompress_tar(member_name, members[member_name])), mode="r:") as archive:
                if any(member.pax_headers for member in archive.getmembers()):
                    raise ValueError(f"PAX headers not supported: {path.name}:{member_name}")

        control = (control_root / "control").read_text(encoding="utf-8")
        if f"Package: {spec.package_id}\n" not in control:
            raise ValueError(f"Debian package ID changed in {path.name}")
        if f"Name: {spec.new_display_name}\n" not in control:
            raise ValueError(f"Debian display name not applied in {path.name}")

        app = data_root / "Applications" / f"{spec.app_name}.app"
        info = plistlib.loads((app / "Info.plist").read_bytes())
        if info.get("CFBundleDisplayName") != spec.new_display_name:
            raise ValueError(f"CFBundleDisplayName wrong in {path.name}")
        if info.get("CFBundleName") != spec.new_bundle_name:
            raise ValueError(f"CFBundleName wrong in {path.name}")
        if not (app / spec.executable).is_file():
            raise ValueError(f"missing executable in {path.name}")

        if spec.clean_rules:
            rules = (app / "varCleanRules.json").read_text(encoding="utf-8")
            if MAIN_BUNDLE_ID not in rules:
                raise ValueError(f"cleaning rules omit {MAIN_BUNDLE_ID} in {path.name}")
            for stale in STALE_MAIN_BUNDLE_IDS:
                if stale in rules:
                    raise ValueError(f"cleaning rules retain {stale} in {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, default=RESOURCES)
    parser.add_argument("--output-dir", type=Path, help="write relabelled packages here")
    parser.add_argument("--ldid", help="path to ldid; required unless --skip-sign is set")
    parser.add_argument("--skip-sign", action="store_true", help="offline structure test only")
    args = parser.parse_args()
    if not args.skip_sign and not args.ldid:
        parser.error("--ldid is required unless --skip-sign is set")

    output = args.output_dir.resolve() if args.output_dir else args.resources
    output.mkdir(parents=True, exist_ok=True)

    for spec in (STORE, CLEANER):
        source = args.resources / spec.deb_name
        if not source.is_file():
            raise SystemExit(f"missing bundled package: {source}")
        target = output / spec.deb_name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        repack(target, spec, args.ldid, args.skip_sign)
        verify(target, spec)
        print(f"{target.name}: relabelled to {spec.new_display_name} (package {spec.package_id} unchanged)")


if __name__ == "__main__":
    main()
