| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 29029 | 26724 | 39360 | 3 | yes |
| exe | x86_64 | 27390 | 26970 | 33994 | 3 | yes |
| exe | arm64-v8a | 8592 | 8456 | 11405 | 3 | yes |
| apk | x86_64 | 25132 | 24685 | 37519 | 3 | yes |
| apk | arm64-v8a | 7906 | 7645 | 8665 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.314** (arm64 runs at 31.4% of native speed)
- **apk: translated arm64 / native x86_64 = 0.315** (arm64 runs at 31.5% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.944
