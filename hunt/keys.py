"""Free API keys the investigator pastes into Hunt (docs/research/tools.md, "Free keys").

Every key is optional except CourtListener's, and Hunt works fully without any of them. They are kept in
HUNT_HOME/keys.json (mode 0600) and put into this process's environment, where the sources already read
them (`os.environ.get(KEY)` at call time). A key set in the shell wins and can't be changed here. No
function or route ever returns a key's value: only whether it's set, and where from.

Which keys exist comes from the sources' KEY / KEY_REQUIRED / KEY_URL / KEY_FREE attributes. A key no
source module declares (a reader elsewhere in Hunt) goes in EXTRA: {env var: {label, url, free}}.
"""

import json
import os

from . import sources
from .case import HOME

PATH = HOME / "keys.json"
MAX_CHARS = 500
LABEL = {"github": "GitHub", "gravatar": "Gravatar", "fec": "OpenFEC", "courtlistener": "CourtListener",
         "licences": "State open-data portals", "businesses": "State open-data portals", "fmcsa": "State open-data portals",
         "edgar": "SEC EDGAR"}
EXTRA: dict[str, dict] = {}
_shell = {k for k in os.environ if k.startswith("HUNT_")}  # set before Hunt started: the shell's, not ours


def known() -> dict[str, dict]:
    """{env var: {label, sources, required, url, free}}, one entry per key (the state portals share one)."""
    out = {}
    for src in sources.SOURCES:
        if key := getattr(src, "KEY", None):
            k = out.setdefault(key, {"label": LABEL.get(src.NAME, src.NAME), "sources": [], "required": False,
                                     "url": getattr(src, "KEY_URL", None), "free": getattr(src, "KEY_FREE", None)})
            k["sources"].append(src.NAME)
            k["required"] |= bool(getattr(src, "KEY_REQUIRED", False))
    return out | {key: {"sources": [], "required": False, **x} for key, x in EXTRA.items()}


def _saved() -> dict:
    try:
        return json.loads(PATH.read_text())
    except (OSError, ValueError):
        return {}


def load():
    """Put the saved keys into this process's environment (the shell's own settings win)."""
    for key, value in _saved().items():
        if key in known() and key not in _shell:
            os.environ[key] = value


def status() -> list[dict]:
    """[{key, label, sources, required, url, free, set, where: "saved"|"environment"|None}], never a value."""
    saved = _saved()
    return [{"key": key, **k, "set": bool(os.environ.get(key)),
             "where": "environment" if key in _shell and os.environ.get(key) else "saved" if key in saved else None}
            for key, k in known().items()]


def save(updates: dict) -> list[dict]:
    """{env var: value}; "" removes one. ValueError for an unknown key, a non-string or overlong value, or a key
    set in the shell."""
    names, saved = known(), _saved()
    for key, value in updates.items():
        if key not in names:
            raise ValueError(f"{key} isn't a key Hunt uses")
        if not isinstance(value, str) or len(value.strip()) > MAX_CHARS:
            raise ValueError(f"{key} must be text of at most {MAX_CHARS} characters")
        if key in _shell:
            raise ValueError(f"{key} is set in the shell that started Hunt; change it there")
    for key, value in updates.items():
        if value.strip():
            saved[key] = os.environ[key] = value.strip()
        else:
            saved.pop(key, None)
            os.environ.pop(key, None)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(saved, f)
    os.chmod(PATH, 0o600)  # an older file keeps its mode through O_TRUNC
    return status()


if __name__ == "__main__":  # self-check: python -m hunt.keys (uses a throwaway HUNT_HOME)
    import tempfile
    from pathlib import Path
    PATH = Path(tempfile.mkdtemp()) / "keys.json"
    _shell = {"HUNT_SEC_UA"}
    os.environ.pop("HUNT_GITHUB_TOKEN", None)
    rows = {r["key"]: r for r in save({"HUNT_GITHUB_TOKEN": " ghp_example "})}
    assert rows["HUNT_GITHUB_TOKEN"] == {**rows["HUNT_GITHUB_TOKEN"], "set": True, "where": "saved"}
    assert os.environ["HUNT_GITHUB_TOKEN"] == "ghp_example" and oct(PATH.stat().st_mode)[-3:] == "600"
    assert "ghp_example" not in json.dumps(status())
    assert rows["HUNT_SOCRATA_TOKEN"]["sources"] == ["licences", "businesses", "fmcsa"]
    assert rows["HUNT_COURTLISTENER_TOKEN"]["required"] and not rows["HUNT_GITHUB_TOKEN"]["required"]
    for bad in ({"HUNT_NOPE": "x"}, {"HUNT_SEC_UA": "x"}, {"HUNT_FEC_KEY": 3}):
        try:
            save(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    save({"HUNT_GITHUB_TOKEN": ""})
    assert "HUNT_GITHUB_TOKEN" not in os.environ and _saved() == {}
    print("ok")
