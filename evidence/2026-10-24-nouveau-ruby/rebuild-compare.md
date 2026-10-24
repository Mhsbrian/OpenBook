# Rebuilt kernel against the installed one

- vmlinux: 4721 -> 4751 exports; removed 0, CRC changed 0, flags changed 0; added 30; unprotected 3
- modules compared: 241; byte-identical: 0; only .BTF differs (beyond vermagic/scmversion/build ID/signature): 33; explained differences: 2; with problems: 0; only installed: 0; only new: 2
- Result: **PASS**

Added exports: `__drm_universal_plane_alloc`, `__mt_destroy`, `_raw_read_lock_irqsave`, `_raw_read_unlock_irqrestore`, `acpi_get_next_object`, `acpi_lid_open`, `dma_resv_fini`, `drm_atomic_helper_wait_for_fences`, `drm_debugfs_gpuva_info`, `drm_gem_handle_delete`, `drm_gem_object_init`, `drm_invalid_op`, `drm_mode_create_dvi_i_properties`, `drm_mode_create_tv_properties_legacy`, `drm_mode_debug_printmodeline`, `drm_plane_force_disable`, `drm_plane_helper_disable_primary`, `drm_plane_helper_update_primary`, `drm_property_add_enum`, `drm_property_create`, `drm_vblank_work_cancel_sync`, `led_classdev_resume`, `led_classdev_suspend`, `mas_erase`, `mas_store_gfp`, `mas_walk`, `pci_disable_rom`, `pci_enable_rom`, `refcount_dec_and_mutex_lock`, `schedule_hrtimeout`

Exports no longer protected: `iowrite16`, `mas_find`, `rb_first`

Only in the rebuilt set: `drm_gpuvm.ko`, `nouveau.ko`

Explained differences:

- `vendor_dlkm/amdgpu.ko`: only the kernel release string differs (and the string offsets it moves): .rela.codetag.alloc_tags, .rela.data, .rela.init.text, .rela.rodata, .rela.text, .rela__bug_table, .rela__dyndbg_classes, .rodata
- `system_dlkm/kheaders.ko`: embeds the kernel's own headers archive (/sys/kernel/kheaders.tar.xz)
