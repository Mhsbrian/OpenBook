#!/usr/bin/env python3
"""Log in on a VM's serial console (a TCP chardev) and run commands, printing each one's output.

    serial-shell.py HOST PORT USER PASSWORD 'cmd1' 'cmd2' ...

Each command's output is printed between "### $ cmd" and "### exit N". Exits non-zero if the login
fails. Used by scripts/quire/linux-env-qemu.sh to run `quired agents` inside the Linux
environment's guest; the guest's default user is AOSP's (droid/droid, cloud-init user-data).
"""
import re
import socket
import sys
import time


def main():
    host, port, user, password, *cmds = sys.argv[1:]
    s = socket.create_connection((host, int(port)), timeout=5)
    s.settimeout(0.5)
    buf = b""

    def read_until(pattern, timeout):
        nonlocal buf
        end = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < end:
            m = rx.search(buf)
            if m:
                out, buf = buf[: m.end()], buf[m.end():]
                return out
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                pass
        return None

    def send(text):
        s.sendall(text.encode() + b"\r")

    # Wake the console and log in.
    for _ in range(30):
        send("")
        if read_until(rb"login: ", 2) is not None:
            break
    else:
        print("serial-shell: no login prompt", file=sys.stderr)
        return 1
    send(user)
    if read_until(rb"[Pp]assword: ", 10) is None:
        print("serial-shell: no password prompt", file=sys.stderr)
        return 1
    send(password)
    if read_until(rb"\$ $", 20) is None:
        print("serial-shell: no shell prompt after login", file=sys.stderr)
        return 1
    send("trap - DEBUG; export TERM=dumb PS1='$ '; stty -echo cols 200")
    read_until(rb"\$ $", 5)
    for i, cmd in enumerate(cmds):
        mark = f"__QUIRE_DONE_{i}__"
        send(f"{cmd}; echo {mark} $?")
        out = read_until(rb"__QUIRE_DONE_%d__ (\d+)" % i, 180)
        print(f"### $ {cmd}")
        if out is None:
            print("### timeout")
            continue
        text = out.decode(errors="replace").replace("\r", "")
        m = re.search(r"__QUIRE_DONE_\d+__ (\d+)", text)
        body = text[: m.start()] if m else text
        print(body.strip("\n"))
        print(f"### exit {m.group(1) if m else '?'}")
    send("exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
