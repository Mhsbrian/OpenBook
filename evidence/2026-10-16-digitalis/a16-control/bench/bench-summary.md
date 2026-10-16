| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 43011 | 41710 | 43190 | 3 | yes |
| exe | x86_64 | 39331 | 38307 | 39730 | 3 | yes |
| exe | arm64-v8a | 11588 | 11582 | 11796 | 3 | yes |
| apk | x86_64 | 38209 | 37629 | 38476 | 3 | yes |
| apk | arm64-v8a | 11345 | 11248 | 11515 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.295** (arm64 runs at 29.5% of native speed)
- **apk: translated arm64 / native x86_64 = 0.297** (arm64 runs at 29.7% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.914
