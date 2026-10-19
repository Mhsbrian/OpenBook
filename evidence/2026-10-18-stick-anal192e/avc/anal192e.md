# SELinux denials in 12 logs

266 enforcing denial records in 10 groups; 0 groups involve an openbook type.

| permissive | source | target | class | perms | count | logs |
|---|---|---|---|---|---|---|
| 0 | mediaprovider_app | shell_data_file | dir | search | 139 | e2e-anal192e/al-console/sections/avc.txt, e2e-anal192e/inst-stick/sections/avc.txt, e2e-anal192e/live-a/sections/avc.txt, e2e-anal192e/reinstall/sections/avc.tx |
| 0 | mediaprovider_app | shell_data_file | dir | getattr | 70 | e2e-anal192e/al-console/sections/avc.txt, e2e-anal192e/inst-stick/sections/avc.txt, e2e-anal192e/live-a/sections/avc.txt, e2e-anal192e/reinstall/sections/avc.tx |
| 0 | keystore | hal_gatekeeper_service | service_manager | find | 24 | e2e-anal192e/al-console/sections/avc.txt, e2e-anal192e/inst-stick/sections/avc.txt, e2e-anal192e/install/sections/avc.txt, e2e-anal192e/live-a/sections/avc.txt, |
| 0 | platform_app | bluetooth_lea_prop | file | read | 24 | e2e-anal192e/al-console/sections/avc.txt, e2e-anal192e/inst-stick/sections/avc.txt, e2e-anal192e/install/sections/avc.txt, e2e-anal192e/live-a/sections/avc.txt, |
| 0 | shell | metadata_file | dir | getattr | 3 | live-20261018-anal192e/first/sections/logcat.txt.gz |
| 0 | shell | linkerconfig_file | dir | getattr | 2 | live-20261018-anal192e/first/sections/logcat.txt.gz |
| 0 | shell | proc | file | read | 1 | live-20261018-anal192e/first/sections/logcat.txt.gz |
| 0 | shell | system_dlkm_file | dir | getattr | 1 | live-20261018-anal192e/first/sections/logcat.txt.gz |
| 0 | shell | vm_data_file | dir | getattr | 1 | live-20261018-anal192e/first/sections/logcat.txt.gz |
| 0 | shell | mirror_data_file | dir | getattr | 1 | live-20261018-anal192e/first/sections/logcat.txt.gz |
