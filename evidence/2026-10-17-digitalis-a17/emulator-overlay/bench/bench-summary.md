| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 44228 | 43943 | 44676 | 3 | yes |
| exe | x86_64 | 40546 | 40494 | 40656 | 3 | yes |
| exe | arm64-v8a | 12155 | 12091 | 12179 | 3 | yes |
| apk | x86_64 | 39456 | 39347 | 39575 | 3 | yes |
| apk | arm64-v8a | 11774 | 11713 | 11828 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.300** (arm64 runs at 30.0% of native speed)
- **apk: translated arm64 / native x86_64 = 0.298** (arm64 runs at 29.8% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.917
