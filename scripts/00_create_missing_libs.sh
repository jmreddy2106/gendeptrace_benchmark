#!/usr/bin/env bash
set -euo pipefail

mkdir -p gendepbench

create_if_missing () {
    local path="$1"
    local content="$2"
    if [ ! -f "$path" ]; then
        echo "[create] $path"
        printf '%s\n' "$content" > "$path"
    else
        echo "[exists] $path"
    fi
}

create_if_missing "gendepbench/__init__.py" '__version__ = "0.2.0"'
create_if_missing "gendepbench/utils.py" 'import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_json(obj: Any) -> str:
    return sha256_text(canonical_json(obj))

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())'

# Add the remaining files the same way (or just copy from the blocks above)

echo "Done."