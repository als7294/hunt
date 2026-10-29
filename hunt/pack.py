"""Move a case between computers: one encrypted archive, every file hash-checked before it's accepted.

pack() puts a whole case (case.db with its audit log, notes and decisions; every evidence file;
case.json) and a manifest of SHA-256 hashes into an AES-256 encrypted disk image, locked with a
passphrase the investigator chooses: `<case>-<UTC time>.hunt-case.dmg`. It's macOS's own format
(hdiutil): no extra software, and Finder can open it with the passphrase too. unpack() opens it
read-only, checks every file against the manifest while copying it aside, and only then puts the
case in place. Nothing is accepted if one file is wrong or unexpected.

Chain of custody survives the move: the archived case's own log ends with 'case packed' (which
computer, when), the computer it left logs 'case pack sealed' (the archive's and the manifest's
SHA-256), and the computer it arrives on logs 'case unpacked' with the same two hashes. Watching
is turned off on arrival; turn it on on the computer that should do it.

The passphrase goes to hdiutil on stdin, never on a command line or in a log.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from . import inbox, watch
from .case import EVIDENCE_NAME, HOME, Case, _sha256, slugify

FORMAT = "hunt-case/1"
MIN_PASSPHRASE = 12
SUFFIX = ".hunt-case.dmg"
ALLOWED = re.compile(r"^case/(case\.db|case\.json|evidence/[0-9a-f]{64}\.\w{2,5})$")  # all an archive may hold


def pack(case, out_dir: Path, passphrase: str) -> dict:
    """Write the case's archive into `out_dir`. {path, sha256, manifest_sha256, files, bytes, changed}."""
    _check(passphrase)
    made = datetime.now(UTC)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{case.name}-{made:%Y%m%d-%H%M%S}Z{SUFFIX}"
    case.audit("case packed", {"from": socket.gethostname(), "file": path.name})  # travels with the case
    staging = Path(tempfile.mkdtemp(prefix=".outgoing-", dir=HOME))
    try:
        manifest = _stage(case, staging, made)
        _seal(staging, path, passphrase)
    finally:
        shutil.rmtree(staging, ignore_errors=True)  # our own copy, never the case
    out = {"path": str(path), "sha256": _sha256(path), "manifest_sha256": manifest["sha256"],
           "files": len(manifest["files"]), "bytes": sum(f["bytes"] for f in manifest["files"]),
           "changed": manifest["changed"]}
    case.audit("case pack sealed", {k: v for k, v in out.items() if k != "path"} | {"file": path.name})
    return out


def unpack(path: Path, passphrase: str, replace: bool = False) -> dict:
    """Bring a packed case in. A case with the same name here is kept, and the new one gets -2, -3…;
    with `replace`, the one here goes to the Trash first. ValueError (nothing changed) for a wrong
    passphrase or a file that doesn't match the manifest. {slug, files, replaced, sha256, manifest_sha256}."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"no such file: {path}")
    sha = _sha256(path)
    HOME.mkdir(parents=True, exist_ok=True)  # a computer that has never run Hunt
    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=HOME))
    try:
        with _opened(path, passphrase) as root:
            manifest = _accept(root, staging)
        slug, replaced = manifest["case"], False
        target = HOME / "cases" / slug
        if (target / "case.db").exists() and replace:
            inbox._trash(target)
            replaced = True
        n = 1
        while (HOME / "cases" / slug).exists():
            n += 1
            slug = f"{manifest['case']}-{n}"
        (HOME / "cases").mkdir(parents=True, exist_ok=True)
        os.replace(staging / "case", HOME / "cases" / slug)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    case = Case.open(slug)
    case.audit("case unpacked", {"file": path.name, "sha256": sha, "manifest_sha256": manifest["sha256"],
                                 "from": manifest["from"], "packed_at": manifest["packed_at"],
                                 "files": len(manifest["files"]), "as": slug, "replaced": replaced})
    watch.stop(case, "moved from another computer")
    return {"slug": slug, "files": len(manifest["files"]), "replaced": replaced, "sha256": sha,
            "manifest_sha256": manifest["sha256"]}


def archives(folder: Path) -> list[dict]:
    """Case archives saved in `folder`, newest first (their contents stay locked until unpacked)."""
    found = [p for p in Path(folder).glob(f"*{SUFFIX}") if p.is_file()]
    return [{"name": p.name, "folder": str(p.parent), "size": p.stat().st_size,
             "saved": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds")}
            for p in sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)]


def _stage(case, dest: Path, made: datetime) -> dict:
    """The case at dest/case (a consistent copy of the database; evidence hard-linked where possible) and
    dest/manifest.json. Returns the manifest, with its own SHA-256."""
    (dest / "case" / "evidence").mkdir(parents=True)
    copy = sqlite3.connect(dest / "case" / "case.db")
    case.db.backup(copy)  # includes what's still in the write-ahead log
    copy.execute("pragma journal_mode = delete")  # one file; the case turns write-ahead logging back on when opened
    copy.close()
    for f in sorted((case.dir / "evidence").iterdir()):
        if EVIDENCE_NAME.match(f.name):
            try:
                os.link(f, dest / "case" / "evidence" / f.name)
            except OSError:  # another volume: copy
                shutil.copy2(f, dest / "case" / "evidence" / f.name)
    if (case.dir / "case.json").is_file():
        shutil.copy2(case.dir / "case.json", dest / "case" / "case.json")
    files = [{"path": p.relative_to(dest).as_posix(), "sha256": _sha256(p), "bytes": p.stat().st_size}
             for p in sorted((dest / "case").rglob("*")) if p.is_file()]
    manifest = {"format": FORMAT, "case": case.name, "label": case.details()["label"], "from": socket.gethostname(),
                "packed_at": made.isoformat(timespec="seconds"), "hunt": version("hunt-osint"), "files": files,
                # evidence whose bytes no longer match the hash it was saved under (it's moved as it is)
                "changed": [f["path"] for f in files if "/evidence/" in f["path"]
                            and Path(f["path"]).name.split(".")[0] != f["sha256"]]}
    body = json.dumps(manifest, indent=1).encode()
    (dest / "manifest.json").write_bytes(body)
    return manifest | {"sha256": hashlib.sha256(body).hexdigest()}


def _accept(root: Path, staging: Path) -> dict:
    """Copy root's case into staging/case, hashing as it goes. ValueError unless every file matches the
    manifest and nothing else is there. Returns the manifest, with its own SHA-256."""
    try:
        body = (root / "manifest.json").read_bytes()
        manifest = json.loads(body)
        assert manifest["format"] == FORMAT and slugify(manifest["case"]) == manifest["case"] != ""
        files = {f["path"]: f for f in manifest["files"]}
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        raise ValueError("not a Hunt case archive (no readable manifest)")
    if bad := [p for p in files if not ALLOWED.match(p)]:
        raise ValueError(f"unexpected file in the manifest: {bad[0]}")
    present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
               and not any(part.startswith(".") for part in p.relative_to(root).parts)} - {"manifest.json"}
    if extra := sorted(present - set(files)):
        raise ValueError(f"a file that isn't in the manifest: {extra[0]}")
    if missing := sorted(set(files) - present):
        raise ValueError(f"missing from the archive: {missing[0]}")
    for rel, f in files.items():
        (staging / rel).parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with open(root / rel, "rb") as src, open(staging / rel, "wb") as out:
            while chunk := src.read(1 << 20):
                h.update(chunk)
                out.write(chunk)
        if h.hexdigest() != f["sha256"]:
            raise ValueError(f"{rel} doesn't match its hash in the manifest; nothing was imported")
    db = sqlite3.connect(staging / "case" / "case.db")
    try:
        if db.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise ValueError("the case database is damaged; nothing was imported")
    finally:
        db.close()
    return manifest | {"sha256": hashlib.sha256(body).hexdigest()}


def _check(passphrase: str):
    if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE or "\0" in passphrase:
        raise ValueError(f"the passphrase needs at least {MIN_PASSPHRASE} characters (a few words works well)")


def _seal(folder: Path, out: Path, passphrase: str):
    """An AES-256 encrypted, compressed, read-only disk image of `folder`."""
    part = out.with_name(f".{out.name}.{secrets.token_hex(4)}.dmg")
    done = subprocess.run(["hdiutil", "create", "-quiet", "-srcfolder", str(folder), "-volname", "Hunt case",
                           "-encryption", "AES-256", "-stdinpass", "-format", "UDZO", str(part)],
                          input=passphrase.encode(), capture_output=True, timeout=3600)
    if done.returncode:
        part.unlink(missing_ok=True)
        raise OSError(f"hdiutil couldn't make the archive: {done.stderr.decode().strip()}")
    os.replace(part, out)


@contextmanager
def _opened(path: Path, passphrase: str):
    """The archive mounted read-only and hidden from Finder, for the length of the block."""
    mount = Path(tempfile.mkdtemp(prefix="hunt-case-"))
    done = subprocess.run(["hdiutil", "attach", "-quiet", "-stdinpass", "-nobrowse", "-readonly", "-noautoopen",
                           "-mountpoint", str(mount), str(path)], input=passphrase.encode(), capture_output=True,
                          timeout=600)
    if done.returncode:
        mount.rmdir()
        raise ValueError("wrong passphrase, or not a Hunt case archive")
    try:
        yield mount
    finally:
        subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], capture_output=True, timeout=120)
        try:
            mount.rmdir()  # only ever an empty folder
        except OSError:  # still mounted: leave it
            pass
