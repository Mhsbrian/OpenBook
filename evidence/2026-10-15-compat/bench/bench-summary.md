| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 44108 | 44063 | 44192 | 3 | yes |
| exe | x86_64 | 40429 | 40298 | 40480 | 3 | yes |
| exe | arm64-v8a | 18479 | 18478 | 18605 | 3 | yes |
| apk | x86_64 | 39303 | 39211 | 39706 | 3 | yes |
| apk | arm64-v8a | 17819 | 17781 | 18036 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.457** (arm64 runs at 45.7% of native speed)
- **apk: translated arm64 / native x86_64 = 0.453** (arm64 runs at 45.3% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.917
