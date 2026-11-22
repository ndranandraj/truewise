"""What a search result shows: the rules every page family's description follows (review of 13
November 2026, Phase 1; Prototype P, approved 21 November).

Query first, one number, and no more than DESC_MAX characters, so a search result never cuts a
description mid-sentence. A builder lists its wordings longest first, each keeping the words that
qualify its number, and fit() takes the first that fits. If none fits, the build stops: a cut
description could lose the qualifier that changes what its number means.

No pipeline imports, so every builder can use it without an import cycle.
"""

from __future__ import annotations

DESC_MAX = 155


def fit(*options: str) -> str:
    """The first wording no longer than DESC_MAX; the build stops if none is."""
    for o in options:
        if len(o) <= DESC_MAX:
            return o
    raise SystemExit(f"search_copy: no description fits {DESC_MAX} characters: {options[-1]!r}")


def fitting(*options: str) -> list[str]:
    """Every wording no longer than DESC_MAX, in order and without repeats; stops if there is none."""
    out = list(dict.fromkeys(o for o in options if len(o) <= DESC_MAX))
    if not out:
        raise SystemExit(f"search_copy: no description fits {DESC_MAX} characters: {options[-1]!r}")
    return out


def n_of(n: int, word: str, many: str | None = None) -> str:
    """'1 program', '3 programs'."""
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def agree(n: int, of: int, one: str, many: str) -> str:
    """The verb after "N of M programs": '1 of 5 programs has', '0 of 1 program has',
    '3 of 5 programs have'."""
    return one if n == 1 or of == 1 else many
