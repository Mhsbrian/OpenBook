# engine-gapps-test: 89/89

## check: 43/43
- PASS openbook-synthetic-gapps-x86_64-37.zip: accepted
- PASS openbook-synthetic-gapps-x86_64-37: the 7 files, each with the source's sha256
- PASS openbook-synthetic-gapps-x86_64-37: three apps, privileged where in priv-app/, x86_64 code where they have code
- PASS openbook-synthetic-gapps-x86_64-37: version, SDK levels and signer as aapt2 and apksigner report them
- PASS openbook-synthetic-gapps-x86_64-37: staged files on disk match the manifest, which is staged by its sha256
- PASS openbook-synthetic-gapps-x86_64-37-xz.zip: accepted
- PASS openbook-synthetic-gapps-x86_64-37-xz: the 7 files, each with the source's sha256
- PASS openbook-synthetic-gapps-x86_64-37-xz: three apps, privileged where in priv-app/, x86_64 code where they have code
- PASS openbook-synthetic-gapps-x86_64-37-xz: version, SDK levels and signer as aapt2 and apksigner report them
- PASS openbook-synthetic-gapps-x86_64-37-xz: staged files on disk match the manifest, which is staged by its sha256
- PASS openbook-synthetic-gapps-x86_64-37-tar.zip: accepted
- PASS openbook-synthetic-gapps-x86_64-37-tar: the 7 files, each with the source's sha256
- PASS openbook-synthetic-gapps-x86_64-37-tar: three apps, privileged where in priv-app/, x86_64 code where they have code
- PASS openbook-synthetic-gapps-x86_64-37-tar: version, SDK levels and signer as aapt2 and apksigner report them
- PASS openbook-synthetic-gapps-x86_64-37-tar: staged files on disk match the manifest, which is staged by its sha256
- PASS neg-arm-lib-dir: refused (native_abi)
- PASS neg-arm-only: refused (native_abi)
- PASS neg-bad-elf: refused (native_abi)
- PASS neg-clash: passes the check (refused later, at plan: gapps_clash)
- PASS neg-corrupt: refused (not_a_package)
- PASS neg-empty: refused (empty)
- PASS neg-framework: refused (framework)
- PASS neg-init: refused (init)
- PASS neg-lib64: refused (native_lib)
- PASS neg-not-a-zip: refused (not_a_package)
- PASS neg-not-litegapps: refused (not_a_package)
- PASS neg-overlay: refused (framework)
- PASS neg-platform-uid: refused (platform_uid)
- PASS neg-selinux: refused (selinux)
- PASS neg-symlink: refused (link)
- PASS neg-system-ext: refused (outside_product)
- PASS neg-traversal: refused (unsafe_path)
- PASS neg-unsigned: refused (unsigned)
- PASS neg-vendor: refused (outside_product)
- PASS neg-wrong-arch: refused (wrong_arch)
- PASS neg-wrong-sdk: refused (wrong_sdk)
- PASS neg-wrong-sdk-tree: refused (wrong_sdk)
- PASS neg-xml-assign: refused (framework)
- PASS neg-xml-doctype: refused (xml_doctype)
- PASS neg-xml-group: refused (framework)
- PASS neg-xml-library: refused (framework)
- PASS neg-xml-unknown: refused (xml_element)
- PASS a refused package leaves nothing staged
## same-install: 7/7
- PASS plan without a package succeeds
- PASS the plan has no package key, operation, section or file
- PASS main's engine accepts this engine's plan (same plan sha256) and installs it
- PASS this engine installs the same plan
- PASS every partition but EFI identical (content digest)
- PASS partition tables identical (first and last MiB)
- PASS EFI partitions hold the same files, byte for byte (install logs aside)
## plan-gapps: 9/9
- PASS plan with the package succeeds
- PASS operations: check_source, check_gapps, ..., super, product, ..., vbmeta
- PASS request names the package and its confirmation
- PASS product section: product_a grows and moves; no FEC; unsigned vbmeta
- PASS gapps section: the package, 7 files, 3 apps with their signers
- PASS warnings: gapps_uncertified (and the image's privapp allowlist is not enforced)
- PASS the bootconfig is written after product is built (no sha256 in the plan yet)
- PASS vbmeta_a: rebuilt
- PASS the target was only read
## refuse-unknown: 1/1
- PASS an unknown package sha256: refused (no_gapps)
## refuse-clash: 1/1
- PASS a package that adds a file the image has: refused (gapps_clash)
## refuse-unconfirmed: 1/1
- PASS an unconfirmed package step: refused (gapps_not_confirmed), target unchanged
## refuse-staged: 2/2
- PASS a staged file changed after the plan: apply fails in check_source
- PASS nothing written to the target
## apply-gapps: 17/17
- PASS apply with the package succeeds and verifies
- PASS report: root digest, vbmeta digest, product sha256
- PASS verified items include the rebuilt product and vbmeta_a
- PASS lpdump: product_a at its new offset and size; every other partition where it was
- PASS product_a: AVB footer, hashtree descriptor for the new image, no FEC
- PASS avbtool verify_image recomputes product's hashtree and finds it correct
- PASS avbtool add_hashtree_footer over the same image and salt: same root digest and hashtree bytes
- PASS fsck.erofs extracts stick-product_a.img without errors
- PASS fsck.erofs extracts product.img without errors
- PASS every one of the stick's 314 product files is unchanged in the new image
- PASS the new image adds exactly the package's 7 files and the install manifest
- PASS /product/etc/openbook/gapps-manifest.json is the package check's manifest
- PASS new files and directories: root-owned, 0644/0755, labeled u:object_r:system_file:s0
- PASS vbmeta_a: unsigned; product's descriptor is the footer's; every other descriptor as on the stick
- PASS bootconfig: androidboot.vbmeta.digest = avbtool calculate_vbmeta_digest, size = the image's
- PASS bootconfig: the same keys as without the package
- PASS every other logical partition is byte-identical to the stick's
## alongside-gapps: 4/4
- PASS an alongside plan with the package: in the free space, product rebuilt
- PASS the install verifies
- PASS MSR, NTFS and recovery byte-identical (S7)
- PASS avbtool verify_image passes on its rebuilt product
## scale: 4/4
- PASS a 256 MiB package with a 256 MiB app: accepted (1.5 s)
- PASS its install verifies (15.8 s; steps {'check_source': 4.5, 'prepare_disk': 0.0, 'boot_images': 0.4, 'system': 6.5, 'boot_entry': 0.0, 'verify': 4.3, 'report': 0.0})
- PASS avbtool verify_image: the 533 MiB product's hashtree is correct
- PASS the 256 MiB app reads back from the image byte for byte
