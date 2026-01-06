from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for x in value:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    # best-effort scalar
    s = str(value).strip()
    return [s] if s else []


def extract_artist_tags(parameter_blob: Any | None) -> list[str]:
    """
    Extract artist tags from a run's opaque parameter_blob.

    Expected shape (from docs / n8n integration):
      parameter_blob["original_tags"]["artist"] -> list[str]

    We also support a few fallback shapes to be resilient to workflow drift.
    """
    if not isinstance(parameter_blob, Mapping):
        return []

    # Primary expected location.
    original = parameter_blob.get("original_tags")
    if isinstance(original, Mapping):
        artists = _as_list(original.get("artist"))
        if artists:
            return artists

    # Fallbacks.
    tags = parameter_blob.get("tags")
    if isinstance(tags, Mapping):
        artists = _as_list(tags.get("artist"))
        if artists:
            return artists

    return _as_list(parameter_blob.get("artist"))


@dataclass(frozen=True)
class ArtistScoreRow:
    artist: str
    posts: int
    approvals: int
    rejections: int
    delta: int
    score: float


def compute_artist_scores_from_runs(
    runs: Iterable[tuple[Any, int, int]],
) -> list[ArtistScoreRow]:
    """
    Compute per-artist scores from an iterable of (parameter_blob, approvals, rejections).

    Score normalization:
      score = delta / posts
      where delta = approvals - rejections
      and posts = number of runs that contained that artist tag

    This matches: "divide any changes in score by the number of posts with that artist tag".
    """
    # Keyed by casefolded artist tag to keep grouping case-insensitive.
    canonical: Dict[str, str] = {}
    posts: Dict[str, int] = {}
    approvals: Dict[str, int] = {}
    rejections: Dict[str, int] = {}

    for parameter_blob, pos, neg in runs:
        artists = extract_artist_tags(parameter_blob)
        if not artists:
            continue

        # De-dupe per-run to avoid double-counting posts when the same artist appears twice.
        seen: set[str] = set()
        for artist in artists:
            key = artist.casefold()
            if key in seen:
                continue
            seen.add(key)
            canonical.setdefault(key, artist)
            posts[key] = posts.get(key, 0) + 1
            approvals[key] = approvals.get(key, 0) + int(pos or 0)
            rejections[key] = rejections.get(key, 0) + int(neg or 0)

    out: list[ArtistScoreRow] = []
    for key, post_count in posts.items():
        if post_count <= 0:
            continue
        pos = int(approvals.get(key, 0))
        neg = int(rejections.get(key, 0))
        delta = pos - neg
        out.append(
            ArtistScoreRow(
                artist=canonical.get(key, key),
                posts=post_count,
                approvals=pos,
                rejections=neg,
                delta=delta,
                score=(delta / float(post_count)),
            )
        )

    out.sort(key=lambda r: (r.score, r.delta, r.posts), reverse=True)
    return out

