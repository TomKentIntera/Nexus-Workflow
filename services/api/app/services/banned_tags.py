from __future__ import annotations

import json
import re
from pathlib import Path


def normalize_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        t = str(tag).strip()
        if not t:
            continue
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def parse_banned_tags(raw: str | None) -> list[str]:
    """
    Parse banned tags from either:
    - JSON list: '["English text","logo"]'
    - CSV/newline/semicolon separated: 'English text, logo\\nwatermark'
    """
    if raw is None:
        return []
    raw = raw.strip()
    if not raw:
        return []

    # JSON list support
    if raw.startswith("["):
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return normalize_tags([str(x) for x in loaded])
        except Exception:
            # Fall through to delimiter splitting
            pass

    parts = re.split(r"[,\n;]+", raw)
    return normalize_tags([p for p in parts])


def load_banned_tags_from_file(path: str | None) -> list[str] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return None
    return parse_banned_tags(content)

