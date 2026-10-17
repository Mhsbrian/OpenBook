| probe_x86_64 | PASS |
| probe_arm64 | PASS |
| coremark_valid | PASS |

| Probe | Done | Failed groups |
|---|---|---|
| x86_64 | 18 pass / 0 fail / 2 skip | - |
| arm64 | 18 pass / 2 fail / 0 skip | isa, signals |

| CoreMark | it/s (median) |
|---|---|
| exe x86_64 | 41,511 |
| exe arm64-v8a | 16,296 |
| apk x86_64 | 39,662 |
| apk arm64-v8a | 15,896 |

- **exe: arm64 / x86_64 = 0.393**
- **apk: arm64 / x86_64 = 0.401**
