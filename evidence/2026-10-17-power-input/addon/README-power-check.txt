OpenBook power check (ANAL-178), added to this live stick
================================================================
Three extra menu entries, after the normal OpenBook ones. Each boots its own small Linux (openbook/check/kernel),
not Android, writes openbook/logs/hwcheck-NNN.txt, .json and -dmesg.txt on THIS stick and powers the laptop off.
Nothing is written to the laptop's own disk, and no firmware setting changes.

- "OpenBook power check: S0i3": powers the NVIDIA GPU and an unused PCIe port down for this boot, then sleeps up to
  four times for 20 s, woken by the clock: as-is, then with the AMD security processor (PSP) given power
  management, then also an unused AMD function, then with the ASUS keyboard and hotkey drivers loaded. It stops
  early once the laptop reaches its deepest sleep state (S0i3). The screen stays black throughout; the laptop
  powers off by itself after about 3 minutes.
- "... 60 s cycles, all steps": the same with 60 s sleeps and all steps (about 5 minutes).
- "OpenBook hardware check (no sleep test)": drivers and devices only, about 1 minute.

Run it plugged in or on battery (the report records which). Then plug the stick into the build host and run
scripts/installer/read-stick-logs.sh. The add-on can be removed by deleting openbook/check/ and
loader/entries/openbook-check-*.conf; the normal entries are untouched.
