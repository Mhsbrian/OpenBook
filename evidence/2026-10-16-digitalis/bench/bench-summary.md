| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 43573 | 43365 | 43700 | 3 | yes |
| exe | x86_64 | 39979 | 39963 | 40298 | 3 | yes |
| exe | arm64-v8a | 11908 | 11846 | 11948 | 3 | yes |
| apk | x86_64 | 38256 | 37845 | 39040 | 3 | yes |
| apk | arm64-v8a | 11631 | 11609 | 11747 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.298** (arm64 runs at 29.8% of native speed)
- **apk: translated arm64 / native x86_64 = 0.304** (arm64 runs at 30.4% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.918
