# gapps-e2e-qemu: 28/28

## g-cli: 10/10
- PASS every expect step matched
- PASS SELinux enforcing
- PASS the USB drive with the packages is mounted by vold
- PASS gapps-check refuses the package that touches the framework
- PASS gapps-check accepts the package (on the live system, from the USB drive)
- PASS staged files labeled openbook_install_data_file
- PASS plan --gapps: product, vbmeta and check_gapps operations
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
