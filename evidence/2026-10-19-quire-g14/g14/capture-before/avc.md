# SELinux denials: capture-before

- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): **0**
- Distinct (source, target, class) in kernel log + logcat: **0** (0 without flags_health_check, which only runs after repeated system_server crashes)
- Raw lines: kernel log {}, logcat {'helper': 11}

| source | target | class | permissions | example |
|---|---|---|---|---|
