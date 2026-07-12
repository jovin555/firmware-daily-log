---
title: "Day 12: mender.io & RAUC: Open-Source OTA Framework Internals"
date: 2026-07-12
tags: ["til", "secure-ota", "mender", "rauc"]
---

## What I Explored Today

Today I dove deep into the internals of two dominant open-source OTA frameworks: **Mender** (by Northern.tech) and **RAUC** (by Pengutronix). While both solve the same fundamental problem—reliable, secure over-the-air updates for embedded Linux—they take radically different architectural approaches. I built a dual-boot A/B update scheme with RAUC on a BeagleBone Black, then compared its update bundle format and state machine against Mender’s artifact system. The goal was to understand not just *how* to use them, but *why* their internals are designed the way they are.

## The Core Concept

The fundamental challenge in OTA is **atomicity and rollback**. If power is lost mid-update, the device must boot into a known-good state. Both Mender and RAUC solve this with an **A/B (redundant rootfs) strategy**, but their philosophies diverge:

- **RAUC** is a *toolkit*: a lightweight C daemon with a D-Bus API. It gives you raw control over slot management, update bundles, and bootloader integration. You bring your own update server, signing infrastructure, and client logic. RAUC is the engine, not the car.
- **Mender** is a *platform*: a full-stack solution with a client daemon (Go), a management server (Go), a UI, and a cloud backend. It abstracts away slot management and provides end-to-end deployment workflows, including phased rollouts and device groups.

The critical internal difference: **RAUC bundles are raw disk images or tarballs with a manifest, while Mender artifacts are structured binary containers with metadata, checksums, and payloads**. Mender’s artifact format (`mender-artifact`) includes a header with artifact name, device type compatibility, and signed checksums—enabling server-side validation before deployment. RAUC’s `.raucb` bundles use a SquashFS filesystem containing a `manifest.raucm` file and the payload images, signed with CMS (Cryptographic Message Syntax).

## Key Commands / Configuration / Code

### RAUC: Building a Bundle and Triggering an Update

First, create a `manifest.raucm` for a dual-slot system:

```ini
[update]
compatible=beaglebone-black
version=2026-07-12

[bundle]
format=verity

[image.rootfs]
filename=rootfs.ext4
sha256=abc123...
size=256M

[image.bootloader]
filename=u-boot.img
sha256=def456...
```

Build the bundle:

```bash
# Create a RAUC bundle (SquashFS + CMS signature)
rauc --cert mycert.pem --key mykey.pem \
     --manifest manifest.raucm \
     --bundle-dir bundle-content/ \
     bundle.raucb

# Inspect the bundle
rauc info bundle.raucb
# Output: Compatible: beaglebone-black, Version: 2026-07-12, Slots: 2
```

Trigger an update from the device:

```bash
# Install bundle to inactive slot (determined by bootloader state)
rauc install /path/to/bundle.raucb

# Check status
rauc status
# Slot A (booted): rootfs.0 [active]
# Slot B: rootfs.1 [inactive, pending]
```

### Mender: Creating and Deploying an Artifact

Generate a Mender artifact from a rootfs image:

```bash
# Create a signed artifact for device type "beaglebone-black"
mender-artifact write rootfs-image \
    --device-type beaglebone-black \
    --artifact-name release-v2.1 \
    --file rootfs.ext4 \
    --output-path release-v2.1.mender \
    --key private.key

# Verify artifact integrity
mender-artifact validate release-v2.1.mender
# Output: Artifact valid, signed with key fingerprint: 12:34:56...
```

On the device, the Mender client polls the server automatically, but you can trigger manually:

```bash
# Force a check for pending deployments
mender check-update

# View current deployment state
mender show-artifact
# Output: release-v2.1
```

The Mender client stores state in `/var/lib/mender/` and uses a **three-phase commit**: download → install → commit. If the device fails to boot after install, the bootloader reverts to the previous slot automatically.

## Common Pitfalls & Gotchas

1. **Bootloader integration is the hardest part.** Both frameworks require modifying U-Boot or GRUB to support A/B slot switching. A common mistake is forgetting to update the bootloader environment variables (e.g., `bootargs` or `root` partition UUID). RAUC provides `rauc bootloader` commands to write slot status, but you must ensure the bootloader is compiled with the correct hooks. Without this, the update installs but the device boots from the old slot forever.

2. **Artifact compatibility mismatches.** Mender’s `device_type` field is a string match—if your artifact says `beaglebone-black` but the device reports `beaglebone-black-revC`, the update is rejected silently. Always standardize device type strings across your fleet. RAUC’s `compatible` field is more flexible (regex matching is possible), but misconfiguration leads to “no compatible slot” errors that are hard to debug without `rauc status --verbose`.

3. **Storage partition sizing.** RAUC bundles contain raw images; if your rootfs image is 300 MB but the slot partition is 256 MB, the update fails at install time. Mender artifacts can use sparse images or compressed payloads, but the decompressed size must still fit. Always run `rauc info --size` or `mender-artifact read` to verify payload sizes against your partition table.

## Try It Yourself

1. **Build a RAUC bundle from scratch.** Create a minimal `manifest.raucm` and a dummy rootfs image (use `dd` to create a 64 MB ext4 filesystem). Sign it with a self-signed certificate, then use `rauc info` to verify the bundle structure. Mount the `.raucb` file (it’s a SquashFS) and inspect the manifest.

2. **Simulate a failed update with Mender.** Set up a QEMU virtual device with Mender client (use the `mender-client` Docker image). Deploy an artifact that intentionally corrupts the rootfs (e.g., remove `/sbin/init`). Observe the automatic rollback: the client detects the boot failure, increments the `rollback_count` in U-Boot environment, and boots the previous slot.

3. **Compare artifact sizes.** Create the same rootfs image (e.g., a 128 MB ext4) as both a RAUC bundle and a Mender artifact. Use `ls -lh` and `du -sh` to compare sizes. Then inspect the bundle structure: `unsquashfs -l bundle.raucb` vs `mender-artifact read artifact.mender`. Note how Mender’s artifact includes a JSON header and checksum tables that RAUC’s SquashFS does not.

## Next Up

Tomorrow, we’ll leave the embedded device behind and look at the cloud side: **AWS IoT Device Management & Azure Device Update for IoT Hub**. We’ll compare how these managed platforms handle fleet-level OTA pipelines, including phased rollouts, device twins, and error reporting at scale.
