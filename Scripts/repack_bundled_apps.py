#!/usr/bin/env python3
"""Repack the bundled package-manager applications with the Departure identity.

The two applications are supplied as prebuilt Debian archives.  Their bundle ID,
Debian package ID, display name, and application directory have to change as a
single transaction; editing only Info.plist leaves LaunchServices, dpkg, and the
binary's self-identification out of sync.  This script preserves that linkage and
re-signs every Mach-O member of each app with ldid before writing the archive.
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


@dataclass(frozen=True)
class AppSpec:
    deb_name: str
    old_package_id: str
    new_package_id: str
    old_bundle_id: str
    new_bundle_id: str
    old_app_name: str
    new_app_name: str
    old_executable: str
    new_executable: str
    display_name: str
    rename_payload: bool = True
    version_suffix: str | None = None


STORE = AppSpec(
    deb_name="sileo.deb",
    old_package_id="org.coolstar.sileo",
    new_package_id="org.coolstar.sileo",
    old_bundle_id="org.coolstar.SileoStore",
    new_bundle_id="org.coolstar.SileoStore",
    old_app_name="Sileo",
    new_app_name="Sileo",
    old_executable="Sileo",
    new_executable="Sileo",
    display_name="商店",
    rename_payload=False,
)

CLEANER = AppSpec(
    deb_name="roothideapp.deb",
    old_package_id="com.roothide.manager",
    new_package_id="com.roothide.manager",
    old_bundle_id="com.roothide.manager",
    new_bundle_id="com.roothide.manager",
    old_app_name="RootHide",
    new_app_name="RootHide",
    old_executable="RootHide",
    new_executable="RootHide",
    display_name="清理",
    rename_payload=False,
)


def read_ar(path: Path) -> list[tuple[str, bytes]]:
    """Return simple BSD/System-V ar members used by Debian packages."""
    raw = path.read_bytes()
    if raw[:8] != b"!<arch>\n":
        raise ValueError(f"{path} is not an ar archive")
    members: list[tuple[str, bytes]] = []
    offset = 8
    while offset < len(raw):
        header = raw[offset : offset + 60]
        if len(header) != 60 or header[-2:] != b"`\n":
            raise ValueError(f"invalid ar header in {path}")
        offset += 60
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        body = raw[offset : offset + size]
        if len(body) != size:
            raise ValueError(f"truncated ar member {name} in {path}")
        offset += size + (size & 1)
        members.append((name, body))
    return members


def write_ar(path: Path, members: Iterable[tuple[str, bytes]]) -> None:
    with path.open("wb") as archive:
        archive.write(b"!<arch>\n")
        for name, body in members:
            encoded_name = f"{name}/".encode("ascii")
            if len(encoded_name) > 16:
                raise ValueError(f"ar member name is too long: {name}")
            header = (
                encoded_name.ljust(16, b" ")
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


def decompress_tar(member_name: str, body: bytes) -> bytes:
    if member_name.endswith(".tar.gz"):
        return gzip.decompress(body)
    if member_name.endswith(".tar.xz"):
        return lzma.decompress(body)
    if member_name.endswith(".tar.lzma"):
        return lzma.decompress(body, format=lzma.FORMAT_ALONE)
    if member_name.endswith(".tar"):
        return body
    raise ValueError(f"unsupported tar member {member_name}")


def compress_tar(member_name: str, payload: bytes) -> bytes:
    if member_name.endswith(".tar.gz"):
        return gzip.compress(payload, mtime=0)
    if member_name.endswith(".tar.xz"):
        return lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)
    if member_name.endswith(".tar.lzma"):
        return lzma.compress(payload, format=lzma.FORMAT_ALONE, preset=6)
    if member_name.endswith(".tar"):
        return payload
    raise ValueError(f"unsupported tar member {member_name}")


def extract_tar(member_name: str, body: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(decompress_tar(member_name, body)), mode="r:") as archive:
        archive.extractall(destination, filter="fully_trusted")


def build_tar(source: Path) -> bytes:
    result = io.BytesIO()
    entries = sorted(source.rglob("*"), key=lambda item: (len(item.relative_to(source).parts), str(item)))
    # Procursus dpkg-deb accepts GNU/ustar headers, but rejects Python's
    # default POSIX.1-2001 PAX extended headers.
    with tarfile.open(fileobj=result, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for entry in entries:
            archive.add(entry, arcname=f"./{entry.relative_to(source).as_posix()}", recursive=False)
    return result.getvalue()


def replace_bytes(path: Path, replacements: dict[bytes, bytes]) -> int:
    data = path.read_bytes()
    original = data
    for old, new in replacements.items():
        data = data.replace(old, new)
    if data != original:
        path.write_bytes(data)
    return sum(original.count(old) for old in replacements)


def replace_tree(root: Path, replacements: dict[bytes, bytes]) -> int:
    count = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            count += replace_bytes(path, replacements)
    return count


def update_control(path: Path, spec: AppSpec) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    found_package = found_name = False
    rewritten: list[str] = []
    for line in lines:
        if line.startswith("Package:"):
            rewritten.append(f"Package: {spec.new_package_id}")
            found_package = True
        elif line.startswith("Name:"):
            rewritten.append(f"Name: {spec.display_name}")
            found_name = True
        elif line.startswith("Version:") and spec.version_suffix:
            rewritten.append(f"Version: {line.split(':', 1)[1].strip()}{spec.version_suffix}")
        else:
            rewritten.append(line)
    if not found_package or not found_name:
        raise ValueError(f"control file is missing Package or Name: {path}")
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def update_info_plist(path: Path, spec: AppSpec) -> None:
    info = plistlib.loads(path.read_bytes())
    info["CFBundleDisplayName"] = spec.display_name
    info["CFBundleName"] = spec.new_app_name
    info["CFBundleIdentifier"] = spec.new_bundle_id
    info["CFBundleExecutable"] = spec.new_executable
    path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False))


MACHO_MAGICS = {
    b"\xce\xfa\xed\xfe",  # MH_MAGIC (little endian)
    b"\xcf\xfa\xed\xfe",  # MH_MAGIC_64 (little endian)
    b"\xfe\xed\xfa\xce",  # MH_CIGAM
    b"\xfe\xed\xfa\xcf",  # MH_CIGAM_64
    b"\xca\xfe\xba\xbe",  # FAT_MAGIC
    b"\xca\xfe\xba\xbf",  # FAT_MAGIC_64
    b"\xbe\xba\xfe\xca",  # FAT_CIGAM
    b"\xbf\xba\xfe\xca",  # FAT_CIGAM_64
}


def is_macho(path: Path) -> bool:
    with path.open("rb") as executable:
        return executable.read(4) in MACHO_MAGICS


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sign_bundle(app_path: Path, ldid: str) -> int:
    """Preserve per-file entitlements when ldid exposes them, then seal the bundle."""
    signature_dir = app_path / "_CodeSignature"
    if signature_dir.exists():
        shutil.rmtree(signature_dir)
    signed = 0
    with tempfile.TemporaryDirectory(prefix="departure-entitlements-") as temp_dir:
        temp_root = Path(temp_dir)
        for candidate in sorted(app_path.rglob("*")):
            if not candidate.is_file() or candidate.is_symlink() or not is_macho(candidate):
                continue
            extracted = subprocess.run([ldid, "-e", str(candidate)], check=False, capture_output=True)
            entitlement_path = temp_root / f"{signed}.plist"
            if extracted.returncode == 0 and b"<plist" in extracted.stdout:
                entitlement_path.write_bytes(extracted.stdout)
                run([ldid, f"-S{entitlement_path}", str(candidate)])
            else:
                run([ldid, "-S", str(candidate)])
            signed += 1
    run([ldid, "-s", str(app_path)])
    return signed


def repack_deb(path: Path, spec: AppSpec, ldid: str | None, skip_sign: bool) -> int:
    members = read_ar(path)
    member_map = dict(members)
    control_name = next((name for name, _ in members if name.startswith("control.tar")), None)
    data_name = next((name for name, _ in members if name.startswith("data.tar")), None)
    if control_name is None or data_name is None:
        raise ValueError(f"{path} does not contain Debian control and data tarballs")

    with tempfile.TemporaryDirectory(prefix="departure-repack-") as temp_dir:
        temp_root = Path(temp_dir)
        control_root = temp_root / "control"
        data_root = temp_root / "data"
        control_root.mkdir()
        data_root.mkdir()
        extract_tar(control_name, member_map[control_name], control_root)
        extract_tar(data_name, member_map[data_name], data_root)

        update_control(control_root / "control", spec)
        control_replacements = {
            spec.old_package_id.encode(): spec.new_package_id.encode(),
        }
        if spec.rename_payload:
            control_replacements[f"/Applications/{spec.old_app_name}.app/{spec.old_executable}".encode()] = f"/Applications/{spec.new_app_name}.app/{spec.new_executable}".encode()
            control_replacements[f"/Applications/{spec.old_app_name}.app".encode()] = f"/Applications/{spec.new_app_name}.app".encode()
        replace_tree(control_root, control_replacements)

        old_app = data_root / "Applications" / f"{spec.old_app_name}.app"
        new_app = data_root / "Applications" / f"{spec.new_app_name if spec.rename_payload else spec.old_app_name}.app"
        if not old_app.is_dir():
            raise ValueError(f"missing app payload {old_app}")
        if spec.rename_payload:
            old_app.rename(new_app)
        old_executable = new_app / spec.old_executable
        if not old_executable.is_file():
            raise ValueError(f"missing app executable {old_executable}")
        if spec.new_executable != spec.old_executable:
            old_executable.rename(new_app / spec.new_executable)
        update_info_plist(new_app / "Info.plist", spec)
        replacements = {
            spec.old_package_id.encode(): spec.new_package_id.encode(),
            spec.old_bundle_id.encode(): spec.new_bundle_id.encode(),
        }
        if spec.rename_payload:
            replacements[f"/Applications/{spec.old_app_name}.app".encode()] = f"/Applications/{spec.new_app_name}.app".encode()
        replacement_count = replace_tree(data_root, replacements)

        if not skip_sign:
            if not ldid:
                raise ValueError("ldid is required; use --skip-sign only for archive-structure tests")
            signed = sign_bundle(new_app, ldid)
            if signed == 0:
                raise ValueError(f"no Mach-O files found in {new_app}")

        repacked = []
        for name, body in members:
            if name == control_name:
                body = compress_tar(name, build_tar(control_root))
            elif name == data_name:
                body = compress_tar(name, build_tar(data_root))
            repacked.append((name, body))
        write_ar(path, repacked)
    return replacement_count


def verify_deb(path: Path, spec: AppSpec) -> None:
    members = dict(read_ar(path))
    control_name = next(name for name in members if name.startswith("control.tar"))
    data_name = next(name for name in members if name.startswith("data.tar"))
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
                    raise ValueError(f"PAX tar headers are not supported in {path.name}:{member_name}")
        control = (control_root / "control").read_text(encoding="utf-8")
        if f"Package: {spec.new_package_id}\n" not in control:
            raise ValueError(f"incorrect Debian package ID in {path.name}")
        if spec.version_suffix and spec.version_suffix not in control:
            raise ValueError(f"incorrect package version in {path.name}")
        app = data_root / "Applications" / f"{spec.new_app_name if spec.rename_payload else spec.old_app_name}.app"
        info = plistlib.loads((app / "Info.plist").read_bytes())
        expected = {
            "CFBundleDisplayName": spec.display_name,
            "CFBundleName": spec.new_app_name,
            "CFBundleIdentifier": spec.new_bundle_id,
            "CFBundleExecutable": spec.new_executable,
        }
        if {key: info.get(key) for key in expected} != expected:
            raise ValueError(f"incorrect app metadata in {path.name}")
        if not (app / spec.new_executable).is_file():
            raise ValueError(f"missing renamed executable in {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, default=RESOURCES, help="directory containing sileo.deb and roothideapp.deb")
    parser.add_argument("--output-dir", type=Path, help="write rebuilt debs here instead of replacing --resources")
    parser.add_argument("--ldid", help="path to ldid; required unless --skip-sign is set")
    parser.add_argument("--skip-sign", action="store_true", help="only for offline archive-structure tests")
    args = parser.parse_args()

    resources = args.resources.resolve()
    output = args.output_dir.resolve() if args.output_dir else resources
    output.mkdir(parents=True, exist_ok=True)
    if args.skip_sign and not args.output_dir:
        parser.error("--skip-sign requires --output-dir so the source packages remain untouched")
    if not args.skip_sign and not args.ldid:
        parser.error("--ldid is required when creating installable packages")

    for spec in (STORE, CLEANER):
        source = resources / spec.deb_name
        destination = output / spec.deb_name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        changed = repack_deb(destination, spec, args.ldid, args.skip_sign)
        verify_deb(destination, spec)
        print(f"{destination.name}: {changed} identity references updated")


if __name__ == "__main__":
    main()
