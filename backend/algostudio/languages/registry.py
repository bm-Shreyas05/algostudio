"""Language frontend registry.

Adding a language means adding one entry here and one package under
``languages/``.  Nothing else in the system learns about it.
"""

from __future__ import annotations

from .base import LanguageFrontend

_FRONTENDS: dict[str, LanguageFrontend] = {}


def register(frontend: LanguageFrontend) -> None:
    _FRONTENDS[frontend.language_id] = frontend


def get(language_id: str) -> LanguageFrontend:
    if language_id not in _FRONTENDS:
        _load_defaults()
    if language_id not in _FRONTENDS:
        raise KeyError(
            f"unknown language {language_id!r}; available: {sorted(_FRONTENDS)}"
        )
    return _FRONTENDS[language_id]


def available() -> list[dict[str, object]]:
    _load_defaults()
    return [
        {
            "id": f.language_id,
            "name": getattr(f, "display_name", f.language_id),
            "extensions": list(f.file_extensions),
        }
        for f in _FRONTENDS.values()
    ]


def _load_defaults() -> None:
    if _FRONTENDS:
        return
    from .python.frontend import FRONTEND as PYTHON

    register(PYTHON)
