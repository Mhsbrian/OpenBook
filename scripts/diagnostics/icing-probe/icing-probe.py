#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inputs and decoding for icing_probe (ANAL-234).

  icing-probe.py inputs OUT.bin       write the schema, documents, specs and queries
  icing-probe.py decode RESULT.bin    summarise one run as JSON against the expected matches

Protos are hand-encoded from external/icing's field numbers so no protoc is needed.
Documents are synthetic Settings-like titles; no device or user data is used.
"""
import argparse
import json
import struct
import sys

TITLES = [
    "Display", "Display size and text", "Brightness level", "Adaptive brightness", "Dark theme",
    "Screen timeout", "Night Light", "Bluetooth", "Bluetooth devices", "Pair new device",
    "Keyboard", "On-screen keyboard", "Physical keyboard", "Keyboard shortcuts", "Battery",
    "Battery saver", "Battery usage", "Network and internet", "Internet", "Hotspot and tethering",
    "Sound and vibration", "Media volume", "Ring and notification volume", "Do Not Disturb",
    "Storage", "Free up space", "Apps", "Default apps", "App info", "Notifications",
    "Security and privacy", "Screen lock", "Device unlock", "Accessibility", "Text to speech",
    "Mouse and touchpad", "Touchpad gestures", "Pointer speed", "System", "Languages",
    "Date and time", "Backup", "Reset options", "About device", "Build number",
    "Location", "Location services", "Passwords and accounts", "Printing", "Cast",
]
KEYWORDS = ["settings", "device", "screen", "power", "audio", "input", "privacy", "connection"]
FILLER = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
DOCS = 600
# (query, terms joined by AND unless "OR" is present)
QUERIES = ["disp", "display", "blue", "keyb", "batt", "touchpad", "sound OR vibration",
           "display brightness", "screen", "nonexistentzz"]


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field(num, value):
    if isinstance(value, int):
        return varint(num << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode()
    return varint(num << 3 | 2) + varint(len(value)) + value


def documents():
    for i in range(DOCS):
        title = TITLES[i % len(TITLES)]
        if i >= len(TITLES):
            title = f"{title} {FILLER[i % len(FILLER)]} {i}"
        words = [KEYWORDS[i % len(KEYWORDS)], KEYWORDS[(i * 3 + 1) % len(KEYWORDS)]]
        yield f"setting/{i}", title, words


def tokens(text):
    out, cur = [], ""
    for ch in text.lower():
        if ch.isalnum() or ch == "_":
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def expected(query):
    groups = query.split(" OR ") if " OR " in query else [query]
    hits = set()
    for uri, title, words in documents():
        toks = tokens(title) + [t for w in words for t in tokens(w)]
        for group in groups:
            if all(any(t.startswith(term) for t in toks) for term in tokens(group)):
                hits.add(uri)
    return hits


def write_inputs(path):
    plain_prefix = field(1, 2) + field(2, 1)          # PREFIX, PLAIN
    prop = lambda name, card: field(1, name) + field(2, 1) + field(4, card) + field(5, plain_prefix)
    schema_type = field(1, "Setting") + field(4, prop("title", 2)) + field(4, prop("keywords", 1))
    records = [(b"S", field(1, schema_type))]
    for n, (uri, title, words) in enumerate(documents()):
        props = field(5, field(1, "title") + field(2, title))
        props += field(5, field(1, "keywords") + b"".join(field(2, w) for w in words))
        records.append((b"D", field(1, "settings") + field(2, uri) + field(3, "Setting")
                        + field(4, 1760000000000 + n) + props))
    records.append((b"C", b""))                        # default ScoringSpecProto
    records.append((b"R", field(1, 1000)))             # num_per_page: every match on one page
    for q in QUERIES:
        records.append((b"Q", field(1, q) + field(2, 2)))  # PREFIX
    with open(path, "wb") as f:
        for kind, data in records:
            f.write(kind + struct.pack("<I", len(data)) + data)


def parse(buf):
    """Yield (field, wire_type, value) for one message."""
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = read_varint(buf, i)
        elif wt == 2:
            n, i = read_varint(buf, i)
            v, i = buf[i:i + n], i + n
        elif wt == 1:
            v, i = buf[i:i + 8], i + 8
        elif wt == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"wire type {wt}")
        yield num, wt, v


def read_varint(buf, i):
    shift = n = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7


STATUS = {0: "UNKNOWN", 1: "OK", 2: "WARNING_DATA_LOSS", 3: "INVALID_ARGUMENT", 4: "NOT_FOUND",
          5: "FAILED_PRECONDITION", 6: "ABORTED", 7: "INTERNAL", 8: "OUT_OF_SPACE",
          9: "ALREADY_EXISTS", 10: "UNAVAILABLE"}


def status(msg):
    for num, _, v in parse(msg):
        if num == 1:
            code, text = None, ""
            for n2, _, v2 in parse(v):
                if n2 == 1:
                    code = v2
                elif n2 == 2:
                    text = v2.decode(errors="replace")
            return {"code": STATUS.get(code, code), "message": text[:200]}
    return {"code": None, "message": ""}


def search_uris(msg):
    uris = []
    for num, _, v in parse(msg):
        if num == 2:
            for n2, _, doc in parse(v):
                if n2 == 1:
                    uris += [u.decode() for n3, _, u in parse(doc) if n3 == 2]
    return uris


def decode(path):
    with open(path, "rb") as f:
        data = f.read()
    records, i = [], 0
    while i < len(data):
        kind = chr(data[i])
        (n,) = struct.unpack_from("<i", data, i + 1)
        i += 5
        body = None if n < 0 else data[i:i + n]
        i += max(n, 0)
        records.append((kind, body))
    out = {"puts": {"total": 0, "ok": 0, "other": {}}, "queries": [], "restart_queries": []}
    first = {"I": "initialize", "S": "set_schema", "F": "persist_full", "J": "restart_initialize"}
    for kind, body in records:
        if body is None:
            out.setdefault("null_results", []).append(kind)
            continue
        if kind in first:
            out[first[kind]] = status(body)
        elif kind == "P":
            out["puts"]["total"] += 1
            code = status(body)["code"]
            if code == "OK":
                out["puts"]["ok"] += 1
            else:
                out["puts"]["other"][str(code)] = out["puts"]["other"].get(str(code), 0) + 1
        elif kind in "QK":
            key = "queries" if kind == "Q" else "restart_queries"
            q = QUERIES[len(out[key])]
            uris = search_uris(body)
            want = expected(q)
            out[key].append({"query": q, "status": status(body)["code"], "results": len(uris),
                             "expected": len(want), "matches_expected": set(uris) == want and len(uris) == len(want)})
    ok = lambda s: s and s.get("code") == "OK"
    out["pass"] = bool(ok(out.get("initialize")) and ok(out.get("set_schema")) and ok(out.get("persist_full"))
                       and ok(out.get("restart_initialize")) and out["puts"]["ok"] == DOCS
                       and len(out["queries"]) == len(QUERIES) == len(out["restart_queries"])
                       and all(q["status"] == "OK" and q["matches_expected"]
                               for q in out["queries"] + out["restart_queries"])
                       and "null_results" not in out)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inputs").add_argument("out")
    sub.add_parser("decode").add_argument("result")
    sub.add_parser("expected")
    a = p.parse_args()
    if a.cmd == "inputs":
        write_inputs(a.out)
    elif a.cmd == "decode":
        json.dump(decode(a.result), sys.stdout, indent=2)
        print()
    else:
        json.dump({q: len(expected(q)) for q in QUERIES}, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
