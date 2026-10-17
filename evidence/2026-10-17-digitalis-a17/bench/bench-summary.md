| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 43709 | 43362 | 44085 | 3 | yes |
| exe | x86_64 | 42839 | 42532 | 42937 | 3 | yes |
| exe | arm64-v8a | 16870 | 16809 | 17506 | 3 | yes |
| apk | x86_64 | 40568 | 39609 | 40631 | 3 | yes |
| apk | arm64-v8a | 16181 | 16119 | 16191 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.394** (arm64 runs at 39.4% of native speed)
- **apk: translated arm64 / native x86_64 = 0.399** (arm64 runs at 39.9% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.980
