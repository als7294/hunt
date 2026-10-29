"""Minimisation at the end of retention: remove the raw media nobody kept or cited, and keep the case.

Hunt scans everything, but a report uses only what is material (10 CCR §2695.7(d);
docs/research/automation-legal.md §4.5). When a case's retention period has ended and it isn't on
legal hold, plan() lists the photos, videos and screenshots of posts that no kept or reported hit and
no note points to, plus the frames the scan saved for hits nobody kept. purge() moves exactly those to
the Trash, as one folder, once the investigator has confirmed the count and size, and audits every
file with its hash ('media minimised').

Hunt never deletes: emptying the Trash is the investigator's own step, and the purge isn't finished
until she does. A case on legal hold keeps everything. Page archives, search results, profile
screenshots and the investigator's own case files are records, not raw media, and stay.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

from . import inbox

KEPT = ("kept", "in report")


def plan(case) -> dict:
    """{ready, why, files: [{file, sha256, bytes, post, kind, source, posted_at}], count, bytes}.
    `why` says why nothing may be removed yet (retention not over, legal hold)."""
    status = case.status()
    why = ("the case is on legal hold: nothing may be removed" if status["legal_hold"] else
           f"the retention period ends {status['retention_ends'][:10]}" if not status["retention_due"] else None)
    if why:
        return {"ready": False, "why": why, "files": [], "count": 0, "bytes": 0}
    tables = {r["name"] for r in case.rows("select name from sqlite_master where type = 'table'")}
    if "media" not in tables:
        return {"ready": True, "why": None, "files": [], "count": 0, "bytes": 0}
    hits = case.rows("select id, post_id, file, status from hits") if "hits" in tables else []
    noted = case.rows("select about, ref from notes") if "notes" in tables else []
    kept_posts = {h["post_id"] for h in hits if h["status"] in KEPT} | {int(n["ref"]) for n in noted if n["about"] == "post"}
    kept_posts |= {h["post_id"] for h in hits for n in noted if n["about"] == "hit" and n["ref"] == str(h["id"])}
    kept_files = {h["file"] for h in hits if h["status"] in KEPT}
    media = case.rows("select m.file, m.sha256, m.kind, m.post_id, p.source, p.posted_at from media m "
                      "join posts p on p.id = m.post_id")
    kept_files |= {m["file"] for m in media if m["post_id"] in kept_posts}
    candidates = [{"file": m["file"], "sha256": m["sha256"], "post": m["post_id"], "kind": m["kind"],
                   "source": m["source"], "posted_at": m["posted_at"]} for m in media if m["file"] not in kept_files]
    candidates += [{"file": h["file"], "sha256": Path(h["file"]).name.split(".")[0], "post": h["post_id"],
                    "kind": "scan frame", "source": None, "posted_at": None}
                   for h in hits if h["file"] and h["file"] not in kept_files and h["status"] not in KEPT]
    files, seen = [], set()
    for c in candidates:
        path = case.dir / c["file"]
        if c["file"] not in seen and path.is_file():
            seen.add(c["file"])
            files.append(c | {"bytes": path.stat().st_size})
    return {"ready": True, "why": None, "files": files, "count": len(files), "bytes": sum(f["bytes"] for f in files)}


def purge(case, count: int, size: int) -> dict:
    """Move plan()'s files to the Trash, if `count` and `size` are what the investigator was shown.
    ValueError otherwise. {count, bytes, trashed_as}. Audited, with every file's hash."""
    p = plan(case)
    if not p["ready"]:
        raise ValueError(p["why"])
    if (count, size) != (p["count"], p["bytes"]) or not p["count"]:
        raise ValueError("confirm the number and size of files shown first")
    folder = case.dir / f"{case.name} unused media {datetime.now(UTC):%Y-%m-%d %H%M%S}"
    folder.mkdir()
    moved = []
    try:
        for f in p["files"]:
            os.replace(case.dir / f["file"], folder / Path(f["file"]).name)
            moved.append(f)
        inbox._trash(folder)
    except OSError:
        for f in moved:  # put everything back: never half a purge, never a deletion
            os.replace(folder / Path(f["file"]).name, case.dir / f["file"])
        folder.rmdir()
        raise
    case.audit("media minimised", {"count": p["count"], "bytes": p["bytes"], "trashed_as": folder.name,
                                   "files": [{k: f[k] for k in ("file", "sha256", "bytes", "post", "kind")}
                                             for f in p["files"]]})
    return {"count": p["count"], "bytes": p["bytes"], "trashed_as": folder.name}
