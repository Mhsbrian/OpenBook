# ARM apps check: OpenBook on ROG Zephyrus G14 (GA403WR)

- build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`
- CPU: AMD Ryzen AI 9 HX 370 w/ Radeon 890M, 24 CPUs; MemTotal: 31934680 kB; translator-relevant flags: fma movbe bmi1 avx2 bmi2 avx512f adx sha_ni vaes 
- cpufreq: driver=amd-pstate-epp governor=powersave epp=balance_performance max_khz=5157895 amd_pstate=active; platform profile: balanced;  AC powered: true level: 16 Capacity level: 3 

| Verdict | Result |
|---|---|
| addon_ran | PASS |
| bridge_check | PASS |
| probe_x86_64 | PASS |
| probe_arm64 | PASS |
| coremark_valid | PASS |

| Probe | Done | Failed groups |
|---|---|---|
| x86_64 | 18 pass / 0 fail / 2 skip | - |
| arm64 | 18 pass / 2 fail / 0 skip | isa, signals |

| CoreMark | it/s (median) |
|---|---|
| exe x86_64 | 27,724 |
| exe arm64-v8a | 10,012 |
| apk x86_64 | 28,205 |
| apk arm64-v8a | 9,902 |

- **exe: arm64 / x86_64 = 0.361**
- **apk: arm64 / x86_64 = 0.351**
