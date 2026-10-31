#!/usr/bin/env bash
# Live check of quired against the agents installed on this machine (docs/quire.md §6).
#
#   1. unit tests (race detector on);
#   2. `quired agents`: discovery, versions, which protocol each agent speaks;
#   3. `quired probe --all`: start every supported agent, ACP initialize + session/new. No prompt,
#      so no model call and no cost;
#   4. two Claude Code turns through the adapter, with a cheap model: one where the permission
#      bridge allows a file write and one where it refuses it. Skipped with QUIRE_NO_PROMPTS=1.
#   5. optional: one turn with an ACP agent, QUIRE_ACP_AGENT=<id> (uses that agent's account).
#
# usage: scripts/quire/live-check.sh [EVIDENCE_DIR]    (default evidence/<today>-quire)
# Writes only to EVIDENCE_DIR and a temporary folder. Agent output is redacted of $HOME.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$R/evidence/$(date -u +%F)-quire}
MODEL=${QUIRE_CLAUDE_MODEL:-haiku}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
redact() { sed -e "s|$HOME|~|g" -e "s|$TMP|\$TMP|g"; }

cd "$R/quire/quired"
echo "== go test" | tee "$OUT/unit-tests.txt"
go version | tee -a "$OUT/unit-tests.txt"
go test -race -count=1 -v ./... 2>&1 | grep -E '^(=== RUN|--- |ok|FAIL|PASS)' | tee -a "$OUT/unit-tests.txt"
go build -trimpath -o "$TMP/quired" .
"$TMP/quired" version | tee "$OUT/version.txt"
uname -srm >> "$OUT/version.txt"

echo "== agents"
"$TMP/quired" agents | redact | tee "$OUT/agents.txt"
"$TMP/quired" agents --json | redact > "$OUT/agents.json"

echo "== probe (initialize + session/new, no prompt)"
"$TMP/quired" probe --all | redact | tee "$OUT/probe.txt"
"$TMP/quired" probe --all --json | redact > "$OUT/probe.json"

if [ "${QUIRE_NO_PROMPTS:-0}" = 1 ]; then exit 0; fi

ask='Create a file named hello.txt in the current folder containing exactly the line: Hello from Quire. Then reply with one short sentence.'
for mode in all none; do
  d="$TMP/claude-$mode"; mkdir -p "$d"
  echo "== claude, --approve $mode"
  set +e
  "$TMP/quired" run --approve "$mode" --cwd "$d" --json --agent-arg=--model --agent-arg="$MODEL" claude "$ask" \
    > "$TMP/run.ndjson" 2> "$TMP/run.err"
  rc=$?
  set -e
  redact < "$TMP/run.ndjson" > "$OUT/claude-approve-$mode.ndjson"
  redact < "$TMP/run.err" > "$OUT/claude-approve-$mode.stderr.txt"
  {
    echo "exit: $rc"
    if [ -f "$d/hello.txt" ]; then echo "hello.txt: $(cat "$d/hello.txt")"; else echo "hello.txt: absent"; fi
    python3 -I - "$TMP/run.ndjson" <<'EOF'
import json, sys
text, tools, perms, result = [], {}, [], None
for line in open(sys.argv[1]):
    m = json.loads(line)
    if m.get("method") == "session/update":
        u = m["params"]["update"]
        k = u.get("sessionUpdate")
        if k == "agent_message_chunk":
            text.append(u["content"].get("text", ""))
        elif k in ("tool_call", "tool_call_update"):
            t = tools.setdefault(u["toolCallId"], {"title": "", "statuses": []})
            t["title"] = u.get("title") or t["title"]
            if u.get("status"):
                t["statuses"].append(u["status"])
    elif m.get("quired") == "permission":
        perms.append((m["request"]["toolCall"].get("title"), m["response"]["outcome"]))
    elif m.get("quired") == "result":
        result = m
print("permission requests:", perms)
for i, t in tools.items():
    print("tool:", t["title"], "->", ",".join(t["statuses"]))
print("reply:", "".join(text).strip())
print("result:", {k: v for k, v in (result or {}).items() if k != "quired"})
EOF
  } | redact | tee "$OUT/claude-approve-$mode.summary.txt"
done

if [ -n "${QUIRE_ACP_AGENT:-}" ]; then
  d="$TMP/acp"; mkdir -p "$d"
  echo "== $QUIRE_ACP_AGENT, --approve read"
  set +e
  "$TMP/quired" run --approve read --cwd "$d" --json "$QUIRE_ACP_AGENT" 'Reply with exactly: QUIRE OK' \
    > "$TMP/acp.ndjson" 2> "$TMP/acp.err"
  echo "exit: $?" > "$OUT/$QUIRE_ACP_AGENT-run.summary.txt"
  set -e
  redact < "$TMP/acp.ndjson" > "$OUT/$QUIRE_ACP_AGENT-run.ndjson"
  redact < "$TMP/acp.err" >> "$OUT/$QUIRE_ACP_AGENT-run.summary.txt"
fi
