| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 43057 | 42532 | 43079 | 3 | yes |
| exe | x86_64 | 39604 | 39334 | 39812 | 3 | yes |
| exe | arm64-v8a | 17899 | 17808 | 18110 | 3 | yes |
| apk | x86_64 | 38412 | 37989 | 38680 | 3 | yes |
| apk | arm64-v8a | 17515 | 17465 | 17520 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.452** (arm64 runs at 45.2% of native speed)
- **apk: translated arm64 / native x86_64 = 0.456** (arm64 runs at 45.6% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.920
