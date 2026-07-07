---
title: "Day 25: OTA Updates: SWUpdate, RAUC & A/B Partitions"
date: 2026-07-07
tags: ["til", "embedded-linux", "ota", "swupdate"]
---

## What I Explored Today

Today I dug into the two dominant open-source frameworks for over-the-air (OTA) updates in Embedded Linux: **SWUpdate** (by SB Solutions) and **RAUC** (by Pengutronix). Both rely on the same fundamental hardware strategy—A/B (redundant) partitions—but differ in philosophy, configuration, and deployment complexity. I built a minimal A/B partition layout on a BeagleBone Black, generated update bundles for both tools, and tested a full update cycle including fallback on failure.

## The Core Concept

Why A/B partitions? Because an update that bricks the device during a power loss is unacceptable in production. With A/B, you have two root filesystem partitions (rootfs_A and rootfs_B) and a small, stable bootloader partition. The bootloader tracks which slot is "active" and which is "inactive." An update writes to the inactive slot, then marks it as the new active slot. If the new system fails to boot, the bootloader increments a "boot count" and falls back to the previous slot after N attempts.

Both SWUpdate and RAUC abstract this logic, but they differ in how you describe the update:

- **SWUpdate** uses a Lua or YAML-based configuration and a `.swu` archive (cpio + metadata). It handles the full pipeline: image verification, writing to block devices, and triggering the bootloader switch.
- **RAUC** uses a manifest file (`.raucm`) and a signed bundle (`.raucb`). It integrates tightly with systemd and expects a bootloader that supports `rauc` commands (U-Boot or GRUB).

The key takeaway: choose SWUpdate if you need maximum flexibility (custom scripts, multiple image types, complex partitioning). Choose RAUC if you want a cleaner, more opinionated system with strong signing and systemd integration.

## Key Commands / Configuration / Code

### 1. A/B Partition Layout (U-Boot environment example)

```bash
# Set up U-Boot environment variables for A/B boot
# On target device, from U-Boot prompt:
setenv bootpart 1:2          # rootfs_A on mmcblk0p2
setenv rootfs_a_part 2
setenv rootfs_b_part 3
setenv bootcount 0
setenv bootlimit 3            # fallback after 3 failed boots
setenv altbootcmd "run bootcmd_b"
setenv bootcmd "run bootcmd_a"
saveenv
```

### 2. SWUpdate: Build a `.swu` bundle

```bash
# Create a software descriptor file (sw-description)
cat > sw-description << 'EOF'
software:
  version: "1.0.0"
  hardware-compatibility: ["revC"]
  images:
    - filename: rootfs.ext4.gz
      device: /dev/mmcblk0p3   # inactive slot
      compressed: true
      sha256: "abcdef..."
  scripts:
    - filename: post_update.sh
      type: postinstall
EOF

# Create the cpio archive (must be in this order)
# sw-description must be first
echo sw-description > files.list
echo rootfs.ext4.gz >> files.list
echo post_update.sh >> files.list

# Build the .swu file
cpio -ov -H crc < files.list > update_v1.0.0.swu
```

### 3. RAUC: Build a `.raucb` bundle

```bash
# Create manifest file (system.conf on target, manifest.raucm for bundle)
cat > manifest.raucm << 'EOF'
[update]
compatible=my-board-revC
version=1.0.0

[bundle]
format=verity

[image.rootfs]
filename=rootfs.ext4
sha256=abcdef...
EOF

# Sign and bundle (requires a certificate)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
rauc bundle --cert=cert.pem --key=key.pem manifest.raucm update_v1.0.0.raucb
```

### 4. Triggering the update

```bash
# SWUpdate: push via HTTP or local file
swupdate -i /path/to/update_v1.0.0.swu -e stable,production

# RAUC: install and reboot
rauc install /path/to/update_v1.0.0.raucb
rauc status   # verify slot status
```

### 5. Bootloader fallback logic (U-Boot + RAUC)

```bash
# In U-Boot, RAUC provides a script to manage bootcount
# Add to board config:
# CONFIG_BOOTCOUNT_LIMIT=y
# CONFIG_BOOTCOUNT_ENV=y

# After RAUC marks slot B as active:
# U-Boot will:
#   1. Increment bootcount
#   2. Try to boot from slot B
#   3. If boot fails (kernel panic, init crash), bootcount > bootlimit
#   4. U-Boot runs altbootcmd → boots slot A
#   5. RAUC marks slot B as bad
```

## Common Pitfalls & Gotchas

1. **Bootloader environment size limits.** U-Boot's environment is typically 16KB or 32KB. If you store large A/B slot metadata (multiple bootcounts, slot status strings), you can overflow it. Always check `env print -a` and use `CONFIG_ENV_SIZE` to increase if needed. RAUC's `rauc status` output can be surprisingly large.

2. **Filesystem UUID collisions.** If both rootfs partitions have the same UUID (common when cloning from a single image), the kernel may mount the wrong one. Always regenerate the UUID after writing the update image:
   ```bash
   tune2fs -U random /dev/mmcblk0p3
   ```
   Or use `PARTUUID` in the kernel cmdline instead of `root=UUID=...`.

3. **SWUpdate: cpio archive order.** The `sw-description` file *must* be the first file in the cpio archive. If you use `find` or `ls` to generate the file list, the order is not guaranteed. Always explicitly list `sw-description` first. A corrupted order will cause SWUpdate to silently fail with a generic "invalid format" error.

## Try It Yourself

1. **Set up A/B partitions on a Raspberry Pi.** Create two 4GB ext4 partitions (`/dev/mmcblk0p2` and `/dev/mmcblk0p3`), copy a minimal rootfs to both, and configure U-Boot to alternate between them using `bootpart` and `bootcount`. Verify fallback by corrupting the kernel on the active slot.

2. **Build a SWUpdate bundle with a post-install script.** Write a script that sets a GPIO high after a successful update. Include it in the `.swu` archive and verify it runs after the image is written. Use `swupdate -v` to see the full log.

3. **Sign a RAUC bundle and test rollback.** Generate a self-signed certificate, create a `.raucb` bundle with a dummy rootfs, install it on a QEMU ARM system, then manually corrupt the new rootfs and confirm the bootloader falls back to the old slot after 3 failed boots.

## Next Up

Tomorrow: **Full Review & Bring-up Checklist** — a comprehensive, battle-tested checklist for bringing a new Embedded Linux board from first power-on to production-ready, covering bootloader, kernel, rootfs, networking, and OTA readiness.
