# gapps-e2e-qemu: 79/79

## g-cut-1: 10/10
- PASS the expect steps up to the cut matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
- PASS the cut came at its point (source super: \d+ bytes, sha256 ok)
- PASS the disk afterwards: old-table (S9)
- PASS the Windows-like partitions are unchanged
## g-cut-2: 9/9
- PASS the expect steps up to the cut matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
- PASS the cut came at its point (product: building product_a)
- PASS the disk afterwards: blank (S9)
## g-cut-3: 9/9
- PASS the expect steps up to the cut matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
- PASS the cut came at its point (product: \d+ bytes \(image)
- PASS the disk afterwards: blank (S9)
## g-cut-4: 9/9
- PASS the expect steps up to the cut matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
- PASS the cut came at its point (vbmeta_a: rebuilt vbmeta)
- PASS the disk afterwards: blank (S9)
## g-cut-5: 9/9
- PASS the expect steps up to the cut matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
- PASS the cut came at its point ("step":"verify","state":"running")
- PASS the disk afterwards: new-not-activated (S9)
## g-ui: 12/12
- PASS every expect step matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS screenshot g4-disk-advanced-on
- PASS screenshot g4b-package-page
- PASS screenshot g4b-package-checked
- PASS screenshot g5-confirm
- PASS screenshot g7-done
- PASS the wizard streamed the package to the daemon and the daemon checked it
- PASS the install with the package verified
- PASS the report has the root digest and vbmeta digest
- PASS no SELinux denial involves the installer's daemon, its files or the package's apps
## g-installed: 18/18
- PASS every expect step matched
- PASS SELinux enforcing, orange state, the installed system
- PASS the loader passed the rebuilt vbmeta's digest (bootconfig)
- PASS product is a dm-verity device with the report's root digest
- PASS /product is mounted from that device
- PASS every product file reads back through dm-verity
- PASS the package's files in /product, labeled system_file
- PASS the three apps installed from /product
- PASS the privileged app is PRIVILEGED, on product, x86_64, with WRITE_SECURE_SETTINGS granted
- PASS its runtime permissions are granted by default (default-permissions XML)
- PASS the stand-in GSF is a privileged app; the ordinary app is not privileged
- PASS SystemConfig read the package's privapp allowlist
- PASS ... its feature
- PASS ... and its sysconfig (power-save allowlist)
- PASS OpenBook setup shows the GSF Android ID (the stand-in's fake one) and the registration steps
- PASS Settings > About's entry: the activity answers Settings' EXTRA_SETTINGS and is enabled (the package is installed)
- PASS tapping About's last row opens the registration page (screenshots g-settings-about-end, g-settings-register)
- PASS no SELinux denial involves the installer's daemon, its files or the package's apps
## g-verity: 3/3
- PASS an intact package file reads
- PASS the read never completed: the system restarted (restart_on_corruption)
- PASS reading the corrupted package file trips dm-verity on product, at the corrupted block
