# ARM apps check: OpenBook on ROG Zephyrus G14 (GA403WR)

- build: `OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys`
- CPU: AMD Ryzen 9 7950X 16-Core Processor, 8 CPUs; MemTotal: 8112180 kB; translator-relevant flags: fma movbe bmi1 avx2 bmi2 avx512f adx sha_ni vaes 
- cpufreq: driver= governor= epp= max_khz= amd_pstate=; platform profile: ;  AC powered: false level: 0 Capacity level: -1 

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
| exe x86_64 | 37,309 |
| exe arm64-v8a | 13,512 |
| apk x86_64 | 38,885 |
| apk arm64-v8a | 14,446 |

- **exe: arm64 / x86_64 = 0.362**
- **apk: arm64 / x86_64 = 0.372**
