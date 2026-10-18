#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""A scripted ACP agent for the Quire Q5 checks (ANAL-219): real ACP v1 over TCP, fixed scenarios.

usage: q5-acp-agent.py [--port 7070] [--name claude-code] [--title "Claude Code"] [--auth] [--log FILE]

Quire core reaches it through `adb reverse tcp:PORT tcp:PORT` and a loopback endpoint (note/LabReceiver ENDPOINT).
Each connection is one agent process as far as Quire can tell. The agent picks a scenario from the prompt's words,
so every state the note shows in the checks comes from ACP messages on the wire: session/update (thought and message
chunks, tool calls and their updates, plans), session/request_permission with Claude Code's option names as quired's
adapter sends them, stop reasons, errors and a dropped connection. It reads and writes nothing on the host.

--auth makes session/new fail with -32000 until `authenticate` is called (the sign-in state).
Holds: scenarios that a check captures mid-flight wait at a "hold" until the agent gets SIGUSR1 (the check, on the
same host, sends it after its screenshot) or HOLD_S seconds pass. scripts/quire/q5-cf-check.py drives them.
"""
import argparse
import json
import signal
import socket
import sys
import threading
import time
import uuid

HOLD_S = 25.0
CLAUDE_OPTIONS = [
    {"optionId": "deny", "name": "Don’t allow", "kind": "reject_once"},
    {"optionId": "always", "name": "Allow for this session", "kind": "allow_always"},
    {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
]
RELEASE = threading.Event()

ADAPTIVE = ("**Adaptive brightness** uses the light sensor to set the screen's brightness for the room you are in, "
            "and learns from the adjustments you make.\n\nOn this laptop it is on. It will not change the brightness "
            "while Battery saver is active, which is why the slider stays where you left it. Turn Battery saver off "
            "and it will start adjusting again within a minute.")
SUMMARY = ("**Summary of the trip notes**\n\nTravel is settled: flights on the 14th at 07:40 and an apartment in "
           "Alfama with check-in from 15:00. The walk from Santa Apolónia is about ten minutes.\n\nThe conference "
           "runs Tuesday to Thursday. Registration opens at 08:30 on Tuesday and the keynote is at 09:15; badges can "
           "also be collected on Monday afternoon.\n\nTwo things are still open: the dinner with the Porto team, and "
           "whether Thursday's workshop needs its own ticket.\n\nPacking: HDMI adapter, a second charger, walking "
           "shoes and a light jacket. The forecast is 18 °C and mostly dry.\n\nSuggested next steps:\n\n"
           "- Confirm the Porto dinner by Friday.\n- Email the organisers about the workshop ticket.\n- Check the "
           "Belém tram times for Thursday afternoon.\n\nIf you want, I can add the registration and keynote to "
           "your calendar and draft the email to the organisers. I can also turn the packing list into a checklist "
           "file, or look up the tram times for you once you tell me which day you plan to go to Belém.")
CODE = ("This uses the date in each photo's metadata and keeps the originals if a name already exists:\n\n"
        "```bash\n# Rename photos in ~/Pictures/Lisbon by the date they were taken\n"
        "for f in ~/Pictures/Lisbon/*.jpg; do\n"
        "  d=$(exiftool -s3 -DateTimeOriginal \"$f\" | tr ': ' '--')\n"
        "  mv -n \"$f\" \"$(dirname \"$f\")/$d.jpg\"\ndone\n```")


class Session:
    def __init__(self, conn, args, log):
        self.conn = conn
        self.args = args
        self.log = log
        self.wlock = threading.Lock()
        self.next_id = 1000
        self.pending = {}
        self.authed = not args.auth
        self.cancelled = threading.Event()
        self.alive = True

    # ------------------------------------------------------------------ wire
    def send(self, msg):
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        with self.wlock:
            try:
                self.conn.sendall(line.encode())
            except OSError:
                self.alive = False
        self.log("->", msg)

    def result(self, rid, result):
        self.send({"jsonrpc": "2.0", "id": rid, "result": result})

    def error(self, rid, code, message):
        self.send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method, params, timeout=600):
        rid = self.next_id
        self.next_id += 1
        ev = threading.Event()
        box = {}
        self.pending[rid] = (ev, box)
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        ev.wait(timeout)
        return box.get("result")

    def update(self, sid, update):
        self.notify("session/update", {"sessionId": sid, "update": update})

    def serve(self):
        buf = b""
        while self.alive:
            try:
                chunk = self.conn.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    self.dispatch(json.loads(line))
        self.alive = False
        self.cancelled.set()

    def dispatch(self, msg):
        self.log("<-", msg)
        method, rid = msg.get("method"), msg.get("id")
        if method is None and rid in self.pending:
            ev, box = self.pending.pop(rid)
            box["result"] = msg.get("result")
            ev.set()
            return
        p = msg.get("params") or {}
        if method == "initialize":
            self.result(rid, {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": False, "promptCapabilities": {"image": True, "audio": False,
                                                                                   "embeddedContext": False}},
                "authMethods": [
                    {"id": "browser", "name": "Sign in with the browser", "description": f"{self.args.name} login"},
                    {"id": "api-key", "name": "Use an API key", "description": f"stays in {self.args.title}"},
                ] if self.args.auth else [],
                "agentInfo": {"name": self.args.name, "title": self.args.title, "version": "q5-scenario"},
            })
        elif method == "authenticate":
            self.authed = True
            self.result(rid, {})
        elif method == "session/new":
            if not self.authed:
                self.error(rid, -32000, "Authentication required")
            else:
                self.result(rid, {"sessionId": "sess-" + uuid.uuid4().hex[:8]})
        elif method == "session/prompt":
            threading.Thread(target=self.turn, args=(rid, p), daemon=True).start()
        elif method == "session/cancel":
            self.cancelled.set()
        elif rid is not None:
            self.error(rid, -32601, f"no method {method}")

    # ------------------------------------------------------------------ scenarios
    def turn(self, rid, p):
        sid = p["sessionId"]
        text = " ".join(b.get("text", "") for b in p.get("prompt", []) if b.get("type") == "text").lower()
        images = sum(1 for b in p.get("prompt", []) if b.get("type") == "image")
        self.log("turn", {"sid": sid, "text": text[-120:], "images": images})
        self.images = [b for b in p.get("prompt", []) if b.get("type") == "image"]
        self.cancelled.clear()
        for key, fn in SCENARIOS:
            if key in text:
                break
        else:
            fn = Session.short
        try:
            reason = fn(self, sid)
        except Cancelled:
            reason = "cancelled"
        except Dropped:
            # shutdown() sends the FIN now and wakes the reader; close() alone waits for the reader's recv.
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.conn.close()
            self.alive = False
            return
        if reason is not None:
            self.result(rid, {"stopReason": reason})

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled()

    def sleep(self, s):
        end = time.time() + s
        while time.time() < end:
            self.check()
            time.sleep(0.05)

    def hold(self):
        """Waits for a release from the check (SIGUSR1) or HOLD_S seconds."""
        end = time.time() + HOLD_S
        while time.time() < end and not RELEASE.is_set():
            self.check()
            time.sleep(0.05)
        RELEASE.clear()

    def think(self, sid, text="Looking at the settings on this page."):
        for w in text.split(" "):
            self.update(sid, {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": w + " "}})
            self.sleep(0.03)

    def say(self, sid, text, step=3, delay=0.08):
        words = text.split(" ")
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + step]) + (" " if i + step < len(words) else "")
            self.update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": chunk}})
            self.sleep(delay)

    def tool(self, sid, tid, title, kind, status="pending", **extra):
        u = {"sessionUpdate": "tool_call", "toolCallId": tid, "title": title, "kind": kind, "status": status}
        u.update(extra)
        self.update(sid, u)

    def tool_update(self, sid, tid, status, **extra):
        u = {"sessionUpdate": "tool_call_update", "toolCallId": tid, "status": status}
        u.update(extra)
        self.update(sid, u)

    def ask(self, sid, tool_call, options=CLAUDE_OPTIONS):
        r = self.request("session/request_permission", {"sessionId": sid, "toolCall": tool_call, "options": options})
        self.check()
        outcome = (r or {}).get("outcome", {})
        return outcome.get("optionId") if outcome.get("outcome") == "selected" else None

    def short(self, sid):
        self.think(sid)
        self.say(sid, "I can help with this window. Ask me to change a setting, explain what you see, or tidy your "
                      "windows.")
        return "end_turn"

    def adaptive(self, sid):
        self.think(sid, "The person is on the Display page and asks about Adaptive brightness.")
        self.sleep(0.8)
        half = ADAPTIVE[:ADAPTIVE.index("which is why")]
        self.say(sid, half)
        self.hold()
        self.say(sid, ADAPTIVE[len(half):])
        return "end_turn"

    def battery(self, sid):
        self.think(sid)
        self.tool(sid, "t1", "Reading Display settings", "read", "in_progress")
        self.sleep(0.6)
        self.tool_update(sid, "t1", "completed")
        self.tool(sid, "t2", "Reading Battery settings", "read", "in_progress")
        self.sleep(0.6)
        self.tool_update(sid, "t2", "completed")
        self.tool(sid, "t3", "Turning on Battery saver", "other", "in_progress")
        self.tool(sid, "t4", "Lowering brightness to 40%", "other", "pending")
        self.hold()
        self.tool_update(sid, "t3", "completed")
        self.tool_update(sid, "t4", "in_progress")
        self.sleep(1.0)
        self.tool_update(sid, "t4", "completed")
        self.say(sid, "Battery saver is on and brightness is at 40%.")
        return "end_turn"

    def talk(self, sid):
        self.think(sid)
        entries = [("Check the HDMI output and mirror mode", "medium", "completed"),
                   ("Turn off notifications during the talk", "high", "in_progress"),
                   ("Set screen timeout to 30 minutes", "medium", "pending"),
                   ("Open the slides in a new window", "medium", "pending")]
        self.update(sid, {"sessionUpdate": "plan", "entries": [
            {"content": c, "priority": p, "status": s} for c, p, s in entries]})
        self.tool(sid, "p1", "Reading Display settings", "read", "completed")
        self.tool(sid, "p2", "Reading Notification settings", "read", "in_progress")
        self.hold()
        self.tool_update(sid, "p2", "completed")
        self.say(sid, "Your laptop is ready for the talk.")
        return "end_turn"

    def checklist(self, sid):
        self.think(sid, "The selection is a packing list.")
        self.tool(sid, "c1", "Reading the selection", "read", "completed")
        new = ("# Lisbon packing list\n- [ ] HDMI adapter\n- [ ] Second laptop charger\n- [ ] Walking shoes\n"
               "- [ ] Light jacket for the evenings\n")
        path = "/home/brian/Documents/Lisbon-packing.md"
        call = {"toolCallId": "c2", "title": "Write Documents/Lisbon-packing.md", "kind": "edit", "status": "pending",
                "content": [{"type": "diff", "path": path, "oldText": None, "newText": new}],
                "rawInput": {"file_path": path, "content": new}}
        self.tool(sid, "c2", call["title"], "edit", "pending", content=call["content"], rawInput=call["rawInput"])
        choice = self.ask(sid, call)
        if choice in ("allow", "always"):
            self.tool_update(sid, "c2", "completed")
            self.say(sid, "Saved the checklist to Documents/Lisbon-packing.md.")
        else:
            self.tool_update(sid, "c2", "failed")
            self.say(sid, "Okay, I didn't write the file.")
        return "end_turn"

    def command(self, sid):
        self.think(sid, "Listing the photos first.")
        cmd = "ls -1 ~/Pictures/Lisbon | wc -l"
        call = {"toolCallId": "x1", "title": "Run ls -1 ~/Pictures/Lisbon | wc -l", "kind": "execute",
                "status": "pending", "rawInput": {"command": cmd}}
        self.tool(sid, "x1", call["title"], "execute", "pending", rawInput=call["rawInput"])
        choice = self.ask(sid, call)
        if choice:
            self.tool_update(sid, "x1", "completed" if choice != "deny" else "failed")
        self.say(sid, "There are 42 photos in that folder." if choice in ("allow", "always") else
                 "Okay, I won't run it.")
        return "end_turn"

    def stopme(self, sid):
        self.think(sid)
        self.tool(sid, "s1", "Reading Display settings", "read", "completed")
        self.tool(sid, "s2", "Reading Battery settings", "read", "completed")
        self.tool(sid, "s3", "Writing the summary to Documents/battery.md", "edit", "completed")
        self.tool(sid, "s4", "Running the brightness script", "execute", "in_progress")
        while True:  # until Esc or Stop
            self.sleep(0.2)

    def broken(self, sid):
        self.think(sid)
        self.tool(sid, "e1", "Reading Display settings", "read", "completed")
        self.tool(sid, "e2", "Reading Battery settings", "read", "in_progress")
        self.sleep(1.2)
        raise Dropped()

    def refuse(self, sid):
        self.think(sid, "This asks me to switch off the lock screen.")
        self.sleep(0.6)
        return "refusal"

    def summary(self, sid):
        self.think(sid, "Reading the document.")
        self.say(sid, SUMMARY[:SUMMARY.index("Suggested next")], step=4, delay=0.06)
        self.hold()
        self.say(sid, SUMMARY[SUMMARY.index("Suggested next"):], step=4, delay=0.06)
        return "end_turn"

    def code(self, sid):
        self.think(sid, "A shell loop with exiftool will do.")
        self.say(sid, CODE, step=4, delay=0.04)
        return "end_turn"

    def schedule(self, sid):
        self.think(sid, "Reading the region.")
        # Shows the region it was given back as an image block, so the note's image state comes over ACP too.
        if self.images:
            img = self.images[0]
            self.update(sid, {"sessionUpdate": "agent_message_chunk",
                              "content": {"type": "image", "mimeType": img.get("mimeType", "image/jpeg"),
                                          "data": img.get("data", "")}})
        self.say(sid, "From the region you pointed at:\n\n- **Mon** · Badge collection, afternoon\n- **Tue** "
                      "· Registration 08:30 · Keynote 09:15\n- **Wed–Thu** · Conference sessions")
        return "end_turn"


class Cancelled(Exception):
    pass


class Dropped(Exception):
    pass


SCENARIOS = [
    ("adaptive brightness", Session.adaptive),
    ("battery saver and lower", Session.battery),
    ("talk tomorrow", Session.talk),
    ("checklist file", Session.checklist),
    ("count the photos", Session.command),
    ("stop me", Session.stopme),
    ("break", Session.broken),
    ("lock screen", Session.refuse),
    ("summarise this document", Session.summary),
    ("renames these photos", Session.code),
    ("schedule here", Session.schedule),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7070)
    ap.add_argument("--name", default="claude-code")
    ap.add_argument("--title", default="Claude Code")
    ap.add_argument("--auth", action="store_true")
    ap.add_argument("--log")
    args = ap.parse_args()
    out = open(args.log, "a") if args.log else sys.stderr
    lock = threading.Lock()

    def log(tag, msg):
        with lock:
            s = json.dumps(msg, ensure_ascii=False)
            if len(s) > 400:
                s = s[:400] + "…"
            print(f"{time.strftime('%H:%M:%S')} {args.port} {tag} {s}", file=out, flush=True)

    signal.signal(signal.SIGUSR1, lambda *_: RELEASE.set())
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen()
    log("listen", {"port": args.port, "name": args.title, "auth": args.auth})
    while True:
        conn, _ = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=Session(conn, args, log).serve, daemon=True).start()


if __name__ == "__main__":
    main()
