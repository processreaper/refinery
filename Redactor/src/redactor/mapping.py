"""Persist the original->fake mapping for optional reversibility."""

from __future__ import annotations

import json
from pathlib import Path


def load_mapping(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Mapping file {path} is not a JSON object")
    return data


def save_mapping(path: Path, mapping: dict[str, dict[str, str]]) -> None:
    path.write_text(
        json.dumps(mapping, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def reverse_text(text: str, mapping: dict[str, dict[str, str]]) -> str:
    """Replace fake values back with originals.

    Useful for un-redacting an AI's response that quoted fake names back at you.
    Longer fakes are replaced first to avoid partial overlaps.
    """
    pairs: list[tuple[str, str]] = []
    for entity_pairs in mapping.values():
        for original, fake in entity_pairs.items():
            pairs.append((fake, original))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    for fake, original in pairs:
        text = text.replace(fake, original)
    return text
