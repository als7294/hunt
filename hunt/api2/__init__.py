"""API for the new frontend (hunt/static/v2, docs/frontend-v2.md): one module per screen, each with a ROUTES list.

A module here can `from ..app import _case, _body` at its top: routes() runs from make_app, after hunt.app has loaded.
"""

import importlib
import pkgutil


def routes() -> list:
    return [r for m in pkgutil.iter_modules(__path__) for r in importlib.import_module(f"{__name__}.{m.name}").ROUTES]
