# Cuttlefish run of run.sh's two app parts (ANAL-177), 2026-10-17
Device: our anybook_vsoc_x86_64 build (CF_DEVICE=anybook_vsoc_x86_64), cvd 1.57, CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle, 6 vCPUs.
GLES (SurfaceFlinger): ANGLE (AMD, Vulkan 1.4.305 (Virtio-GPU GFXStream (AMD Radeon Graphics (RADV RAPHAEL_MENDOCINO)))): ANGLE in the guest on gfxstream's virtual Vulkan, which forwards to the host's RADV on the 610M. Not the G14's stack.
SELinux set permissive by hand (adb root; setenforce 0), as the live stick's graphics entry boots.
Payload pushed with adb to /data/local/tmp/openbook-gfx; run.sh run as root: GFX_PARTS='egl angle' (egl/), then GFX_PARTS=angle with the final FUSE-safe runner (angle/).

ro.build.fingerprint=AnyBook/anybook_cf_x86_64_pc/anybook_vsoc_x86_64:17/CP2A.260605.016/eng.builde:userdebug/test-keys
vendor.anybook.gpu.hal=virtio
ro.hardware.egl=angle
ro.hardware.vulkan=ranchu
persist.graphics.egl=
