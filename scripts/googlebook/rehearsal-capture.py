#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read serial plus this observation's saved logs, excluding prior sessions."""
import hashlib
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def current_capture(out, observation):
    out = Path(out).absolute()
    names = observation.get("saved_log_files")
    require(isinstance(names, list) and all(isinstance(n, str) for n in names),
            "Missing current capture inventory")
    require(len(names) == len(set(names)), "Duplicate current capture entry")
    prior_root = out / "prior-logs"
    require(not prior_root.is_symlink(), "Symlink prior capture directory")
    prior = {p.name for p in prior_root.iterdir()} if prior_root.is_dir() else set()
    require(len(prior) == observation.get("prior_log_sessions_excluded"),
            "Changed prior capture inventory")
    for name in names:
        p = Path(name)
        require(not p.is_absolute() and ".." not in p.parts and len(p.parts) >= 3
                and p.parts[0] == "saved-logs", "Unsafe current capture path")
        require(p.parts[1] not in prior, "Current capture includes a prior session")
    text, inventory = [], {}
    for name in ["serial.log", *names]:
        p = out / name
        require(not any(q.is_symlink() for q in (p, *p.parents)) and p.is_file(),
                "Regular current capture file required")
        data = p.read_bytes()
        inventory[name] = hashlib.sha256(data).hexdigest()
        text.append(data.decode(errors="replace"))
    return "\n".join(text), inventory
