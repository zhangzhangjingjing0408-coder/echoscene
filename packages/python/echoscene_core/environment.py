from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, MutableMapping

from dotenv import dotenv_values


def merged_environment(
    paths: Iterable[str] = (".env", ".env.local"),
    process_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve non-empty settings with local files below the real process environment.

    `.env.local` intentionally wins over `.env`, but an empty placeholder never erases a
    configured value. A non-empty shell value remains the highest-priority deployment input.
    """
    resolved: dict[str, str] = {}
    for path in paths:
        for key, value in dotenv_values(path).items():
            if value:
                resolved[key] = value
    process_values = os.environ if process_environment is None else process_environment
    for key, value in process_values.items():
        if value:
            resolved[key] = value
    return resolved


def apply_environment(
    paths: Iterable[str] = (".env", ".env.local"),
    target_environment: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Apply the resolved environment for SDKs that only inspect process variables.

    Existing non-empty process values retain highest priority. Empty placeholders are
    replaced by a configured file value, and no values are logged or written back to disk.
    """
    target = os.environ if target_environment is None else target_environment
    resolved = merged_environment(paths, target)
    target.update(resolved)
    return resolved
