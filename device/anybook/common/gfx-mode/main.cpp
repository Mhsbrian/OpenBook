// Copyright (C) 2026 The AnyBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// openbook-gfx-mode: graphics modes (eco, hybrid, ultimate) with automatic MUX rollback (ANAL-241, ANAL-246).
// docs/nvidia-graphics-modes.md has the design; openbook-gfx-mode.rc runs each command at its point of the boot.

#include <stdio.h>
#include <string.h>

#include <string>

#include "gfx_mode.h"

#ifdef __ANDROID__
#include <sys/system_properties.h>
#endif

namespace {

constexpr char kUsage[] =
    "usage: openbook-gfx-mode [options] COMMAND\n"
    "  boot              early init: reconcile with the firmware, guard ultimate boots, roll back\n"
    "  select            the stack selector's decision (anybook_gpu_probe makes it at boot)\n"
    "  frame CARD:CONN   the composer presented a frame on this panel connector (card1:eDP-1)\n"
    "  booted            boot completed\n"
    "  watchdog          ultimate boots: the frame, boot completion and keep deadlines\n"
    "  keep | revert     the owner's answer after switching to ultimate\n"
    "  deadline          the health watchdog expired\n"
    "  request MODE      eco | hybrid | ultimate\n"
    "  lock [MODE] | unlock\n"
    "  restore           gpu_mux_mode=1 now, then restart\n"
    "  app VALUE         the OpenBook Graphics app's request (openbook.gfx.request): VERB[:MODE]@SEQ\n"
    "  adb VALUE         an adb request (debug.openbook.gfx): hybrid restore revert status, more with the lab\n"
    "  status\n"
    "options: --sysfs DIR --fw DIR --state DIR --stacks FILE --cmdline FILE --props DIR --dry-run\n";

}  // namespace

int main(int argc, char** argv) {
    openbook::gfx::Paths paths;
    bool dry_run = false;
#ifdef __ANDROID__
    // Firmware writes stay off until the image says otherwise: a release turns them on only after the owner
    // approved the first real switch (epic ANAL-237).
    char value[PROP_VALUE_MAX] = "";
    __system_property_get("ro.vendor.openbook.gfx.fw_writes", value);
    dry_run = strcmp(value, "1") != 0;
#endif
    int i = 1;
    for (; i < argc && strncmp(argv[i], "--", 2) == 0; ++i) {
        const std::string opt = argv[i];
        if (opt == "--dry-run") {
            dry_run = true;
            continue;
        }
        if (i + 1 >= argc) {
            fputs(kUsage, stderr);
            return 2;
        }
        const std::string v = argv[++i];
        if (opt == "--sysfs") paths.sysfs = v;
        else if (opt == "--fw") paths.fw = v;
        else if (opt == "--state") paths.state_dir = v;
        else if (opt == "--stacks") paths.stacks = v;
        else if (opt == "--cmdline") paths.cmdline = v;
        else if (opt == "--props") paths.props = v;
        else {
            fputs(kUsage, stderr);
            return 2;
        }
    }
    if (i >= argc) {
        fputs(kUsage, stderr);
        return 2;
    }
    const std::string cmd = argv[i];
    const std::string arg = i + 1 < argc ? argv[i + 1] : "";
    if (i + 2 < argc) {
        fputs(kUsage, stderr);
        return 2;
    }
    openbook::gfx::Controller c(paths, dry_run);
    if (cmd == "boot") return c.Boot();
    if (cmd == "select") return c.SelectStack();
    if (cmd == "frame" && !arg.empty()) return c.Frame(arg);
    if (cmd == "booted") return c.Booted();
    if (cmd == "watchdog") return c.Watchdog();
    if (cmd == "keep") return c.Keep();
    if (cmd == "revert") return c.Revert();
    if (cmd == "deadline") return c.Deadline();
    if (cmd == "request" && !arg.empty()) return c.Request(arg);
    if (cmd == "lock") return c.Lock(arg);
    if (cmd == "unlock") return c.Unlock();
    if (cmd == "restore") return c.Restore();
    if (cmd == "app" && !arg.empty()) return c.App(arg);
    if (cmd == "adb" && !arg.empty()) return c.Adb(arg);
    if (cmd == "status") return c.Status();
    fputs(kUsage, stderr);
    return 2;
}
