# openbook-addons host tests: 37/37

| Case | Check | Result |
|---|---|---|
| absent | exit 0 | pass |
| absent | result absent | pass |
| absent | the EFI partition was found | pass |
| absent | no cmd call | pass |
| absent | no state written | pass |
| no-uuid | exit 0, result absent, no cmd call | pass |
| install | exit 0 | pass |
| install | result installed | pass |
| install | all three packages installed at the pinned versions | pass |
| install | the exact pinned bytes were streamed, in catalogue order | pass |
| install | --bypass-low-target-sdk-block only for the package that asks for it | pass |
| install | the catalogue's permissions granted | pass |
| install | app-ops set | pass |
| install | battery-optimisation exemption for GmsCore only | pass |
| install | state: installed, this version | pass |
| install | the disk image is unchanged (read-only) | pass |
| install | a log was written | pass |
| again | exit 0, already installed, no cmd call | pass |
| uninstalled | an app the user uninstalled stays uninstalled | pass |
| kept | exit 0, installed | pass |
| kept | newer and equal versions kept, the missing one installed | pass |
| kept | grants still applied to kept packages | pass |
| upgrade | exit 0, installed, state at the new version | pass |
| upgrade | the older package upgraded, the removed one left out, the current one kept | pass |
| upgrade | no permission, app-op or exemption applied again | pass |
| tampered | exit 1, refused | pass |
| tampered | nothing installed, no write call at all | pass |
| tampered | the reason names the file | pass |
| tampered | state: refused | pass |
| missing | exit 1, refused, nothing installed | pass |
| commit-fails | exit 1, failed | pass |
| commit-fails | stops at the failing package | pass |
| commit-fails | the next run tries again and completes | pass |
| grant-fails | installed; the failed grant is reported | pass |
| bad-catalogue | exit 1, bad_catalog, no cmd call | pass |
| from-dir | exit 0, installed from the directory | pass |
| status | would_install, nothing written, no state | pass |
