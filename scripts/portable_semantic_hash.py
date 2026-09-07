"""Optional portable semantic hashes for evidence portability audits."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

_PATH_KEY = re.compile(r"(?:path|root|directory|filename)$", re.IGNORECASE)


def _float_text(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    if text == "":
        return ""
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "Inf" if number > 0 else "-Inf"
    return format(number, ".17g")


def _normalize_json(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_json(v, str(k)) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_json(item, key) for item in value]
    if isinstance(value, str) and key and _PATH_KEY.search(key):
        normalized = value.replace("\\", "/")
        normalized = re.sub(r"^[A-Za-z]:/", "<DRIVE>/", normalized)
        normalized = re.sub(r"^/mnt/[A-Za-z]/", "<DRIVE>/", normalized)
        return normalized
    return value


def canonical_bytes(path: Path) -> bytes:
    """Return canonical portable bytes without changing the source file."""
    if path.suffix.lower() == ".json":
        value = _normalize_json(json.loads(path.read_text(encoding="utf-8")))
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows:
            return b""
        header, body = rows[0], rows[1:]
        normalized = []
        for row in body:
            values = []
            for column, cell in zip(header, row):
                if re.search(r"(?:path|root|directory|filename)$", column, re.IGNORECASE):
                    normalized_path = cell.replace("\\", "/")
                    normalized_path = re.sub(r"^[A-Za-z]:/+", "<DRIVE>/", normalized_path)
                    normalized_path = re.sub(r"^/mnt/[A-Za-z]/", "<DRIVE>/", normalized_path)
                    values.append(normalized_path)
                else:
                    values.append(_float_text(cell))
            normalized.append(values)
        normalized.sort(key=lambda row: tuple(row))
        return "".join(",".join(cell.replace("\n", " ") for cell in row) + "\n" for row in [header, *normalized]).encode("utf-8")
    raise ValueError(f"portable semantic hashing supports only CSV/JSON: {path}")


def portable_semantic_sha256(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()
