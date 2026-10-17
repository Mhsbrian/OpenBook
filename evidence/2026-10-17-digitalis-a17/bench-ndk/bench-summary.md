| mode | ABI | median it/s | min | max | n | valid |
|---|---|---|---|---|---|---|
| host | x86_64 | 43885 | 43828 | 43917 | 3 | yes |
| exe | x86_64 | 40532 | 40134 | 40620 | 3 | yes |
| exe | arm64-v8a | 18516 | 18488 | 18603 | 3 | yes |
| apk | x86_64 | 39293 | 39262 | 39648 | 3 | yes |
| apk | arm64-v8a | 17932 | 17843 | 17986 | 3 | yes |

- **exe: translated arm64 / native x86_64 = 0.457** (arm64 runs at 45.7% of native speed)
- **apk: translated arm64 / native x86_64 = 0.456** (arm64 runs at 45.6% of native speed)
- VM overhead: emulator x86_64 / host x86_64 = 0.924
