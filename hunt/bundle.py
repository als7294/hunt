"""The evidence bundle: every evidence file in a case under a readable name, with a hash manifest.

    <case>-evidence-<UTC time>.zip
      exhibits/       each evidence file, e.g. 2024-03-28_tiktok_kestrel_vane88_3fa9c2d1.mp4
      manifest.csv    what each exhibit is, where it came from, when, its original name, and the
                      SHA-256 it was saved under
      SHA256SUMS      the same hashes in the standard format: `shasum -a 256 -c SHA256SUMS`
      audit-log.csv   the case log (searches, decisions, imports, exports), oldest first
      README.txt      the case, its purpose, and how to check the bundle

Files are re-hashed as they are written. One that no longer matches the hash it was saved under is
still included, flagged in the manifest and README, and fails the shasum check: that is the point.
The bundle's own SHA-256 goes in the audit log, so a hand-over can be tied to this case.
"""

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from PIL import Image

from . import inbox
from .case import EVIDENCE_NAME, _sha256

COLUMNS = ("exhibit", "sha256", "bytes", "hash_ok", "what", "source", "url", "account", "posted_at", "saved_at",
           "original_name")
README = """Evidence bundle for case "{label}" ({slug})
Purpose on record: {purpose}
Made by Hunt {version} at {made} UTC from {count} evidence files.

  exhibits/       every evidence file, under a readable name
  manifest.csv    what each exhibit is, where it came from, and the SHA-256 it was saved under
  SHA256SUMS      the same hashes, in the standard format
  audit-log.csv   the case log: every search, decision, import and export, with UTC times

To check that every exhibit is unchanged, in this folder:
  macOS:    shasum -a 256 -c SHA256SUMS
  Linux:    sha256sum -c SHA256SUMS
  Windows:  Get-FileHash -Algorithm SHA256 exhibits\\<file>   (compare with manifest.csv)
"""


def describe(case) -> dict[str, dict]:
    """SHA-256 → what the case's records say about that evidence file. Later records refine earlier ones:
    an investigator's import says more than the page a file was first seen on."""
    out, tables = {}, {r["name"] for r in case.rows("select name from sqlite_master where type = 'table'")}

    def add(file, **info):
        if file and EVIDENCE_NAME.match(Path(file).name):
            out.setdefault(Path(file).name.split(".")[0], {}).update({k: v for k, v in info.items() if v})

    for r in case.rows("select evidence, site, url, fetched_at from findings where evidence is not null"):
        add(r["evidence"], what=f"{r['site']} page source, as fetched", source=r["site"], url=r["url"],
            saved_at=r["fetched_at"], parts=(r["site"], "page"))
    for r in case.rows("select c.evidence, c.kind, c.ts, f.site, f.url from captures c join findings f on f.id = c.finding_id"):
        add(r["evidence"], what=f"{r['site']} profile, {r['kind']}", source=r["site"], url=r["url"], saved_at=r["ts"],
            parts=(r["site"], r["kind"]))
    for r in case.rows("select evidence, url, ts from avatars"):
        add(r["evidence"], what="profile photo", url=r["url"], saved_at=r["ts"], parts=("profile-photo",))
    for r in case.rows("select evidence, name, ts from photos"):
        add(r["evidence"], what="photo added for geolocation", original_name=r["name"], saved_at=r["ts"],
            parts=("photo",))
    if {"posts", "media"} <= tables:
        for r in case.rows("select m.file, m.kind, p.source, p.url, p.account_url, p.posted_at, p.origin, p.fetched_at "
                           "from media m join posts p on p.id = m.post_id"):
            handle = inbox.from_url(r["account_url"])["handle"] if r["account_url"] else None
            add(r["file"], what=f"{r['kind']} {'from a ' + r['source'] + ' post' if r['origin'] == 'fetched' else 'added'}",
                source=r["source"], url=r["url"], account=r["account_url"], posted_at=r["posted_at"],
                saved_at=r["fetched_at"], parts=(r["source"], handle, r["kind"]))
    if {"posts", "media", "hits"} <= tables:
        for r in case.rows("select h.file, h.t0, h.t1, p.source, p.url, p.posted_at from hits h "
                           "join media m on m.id = h.media_id join posts p on p.id = h.post_id where m.kind = 'video'"):
            at = f", {r['t0']:.0f}–{r['t1']:.0f} s" if r["t0"] is not None and r["t1"] is not None else ""
            add(r["file"], what=f"frame from a video{at}", source=r["source"], url=r["url"], posted_at=r["posted_at"],
                parts=(r["source"], "frame"))
    for action, detail, ts in case.db.execute("select action, detail, ts from audit where action in "
                                              "('file added', 'inbox import') order by rowid"):
        d = json.loads(detail)
        if action == "file added":  # posts.add_files: the original name (and the HEIC kept beside its JPEG)
            # app uploads arrive renamed 0.jpg, 1.mp4… (app.add_media): not a name the investigator gave
            name = None if re.fullmatch(r"\d+\.\w+", d["name"]) else d["name"]
            out.setdefault(d["sha256"], {}).update({k: v for k, v in {"original_name": name, "saved_at": ts}.items() if v})
        elif d.get("result") == "added":
            out.setdefault(d["sha256"], {}).update({k: v for k, v in {
                "exhibit": d["exhibit"], "original_name": d["name"], "source": d["platform"], "url": d["url"],
                "posted_at": d["posted_at"], "saved_at": ts,
                "what": "file the investigator saved"}.items() if v})
    return out


def make(case, out_dir: Path) -> dict:
    """Write the bundle into `out_dir`. {path, sha256, exhibits, changed: [exhibit]}."""
    info, made = describe(case), datetime.now(UTC)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{case.name}-evidence-{made:%Y%m%d-%H%M%S}Z.zip"
    files = sorted(f for f in (case.dir / "evidence").iterdir() if EVIDENCE_NAME.match(f.name))
    rows, used = [], set()
    part = path.with_suffix(".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as z:  # media are compressed already
        for f in files:
            sha, ext = f.name.split(".")
            d = info.get(sha, {})
            ext = _image_ext(f) if ext == "img" else ext
            name = d.get("exhibit") or _exhibit(sha, ext, (d.get("posted_at") or d.get("saved_at") or "")[:10],
                                                *d.get("parts", ()))
            name = name if name not in used else f"{sha}.{ext}"
            used.add(name)
            h = hashlib.sha256()
            entry = zipfile.ZipInfo.from_file(f, f"exhibits/{name}")  # dated when it was saved into the case
            with open(f, "rb") as src, z.open(entry, "w", force_zip64=True) as dst:
                while chunk := src.read(1 << 20):
                    h.update(chunk)
                    dst.write(chunk)
            rows.append({**{k: d.get(k, "") for k in COLUMNS}, "exhibit": name, "sha256": sha, "bytes": f.stat().st_size,
                         "hash_ok": "yes" if h.hexdigest() == sha else "NO: changed since saved"})
        changed = [r["exhibit"] for r in rows if r["hash_ok"] != "yes"]
        details = case.details()
        readme = README.format(label=details["label"], slug=case.name, purpose=details["purpose"],
                               version=version("hunt-osint"), made=f"{made:%Y-%m-%d %H:%M:%S}", count=len(rows))
        if changed:
            readme += f"\nWARNING: {len(changed)} files no longer match the hash they were saved under:\n  " + \
                      "\n  ".join(changed) + "\n"
        text = {"manifest.csv": _csv(COLUMNS, rows), "README.txt": readme,
                "SHA256SUMS": "".join(f"{r['sha256']}  exhibits/{r['exhibit']}\n" for r in rows),
                "audit-log.csv": _csv(("id", "ts", "action", "detail"),
                                      case.rows("select rowid as id, ts, action, detail from audit order by rowid"))}
        for name, body in text.items():
            z.writestr(name, body, zipfile.ZIP_DEFLATED)
    os.replace(part, path)
    sha = _sha256(path)
    case.audit("evidence exported", {"file": path.name, "sha256": sha, "exhibits": len(rows), "changed": changed})
    return {"path": str(path), "sha256": sha, "exhibits": len(rows), "changed": changed}


def _exhibit(sha: str, ext: str, *parts) -> str:
    words = [re.sub(r"[^\w.-]+", "-", str(p)).strip("-").lower() for p in parts if p]
    return "_".join([w for w in words if w] + [sha[:8]]) + "." + ext


def _image_ext(path: Path) -> str:
    """Profile photos are stored as .img; a recipient needs the real type to open them."""
    try:
        with Image.open(path) as im:
            return {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}.get(im.format, "img")
    except OSError:
        return "img"


def _csv(columns, rows) -> str:
    """A CSV that's safe to open in a spreadsheet: a cell starting = + - @ is quoted with ', not run."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, columns, extrasaction="ignore")
    w.writeheader()
    w.writerows({k: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
                 for k, v in r.items()} for r in rows)
    return buf.getvalue()
