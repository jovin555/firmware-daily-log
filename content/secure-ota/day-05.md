---
title: "Day 05: Anti-Rollback Policies: Manifest Versioning & Fleet-Wide Enforcement"
date: 2026-07-05
tags: ["til", "secure-ota", "anti-rollback", "versioning"]
---

## What I Explored Today

Today I dug into the practical mechanics of anti-rollback enforcement—specifically how to embed version counters into OTA manifests and enforce them across a fleet without bricking devices. I focused on the interplay between hardware-backed monotonic counters (like TPM NVRAM or eFuse banks) and software-manifest version fields, and how to handle fleet-wide version bumps when some devices are offline or in deep sleep.

## The Core Concept

Anti-rollback isn't about preventing downgrades—it's about preventing *reversion to vulnerable code*. The fundamental idea is simple: each firmware image carries a monotonically increasing version number, and the bootloader refuses to install any image with a version lower than the one currently recorded in secure storage. But the devil is in the fleet-wide enforcement.

The key insight I internalized today: **version enforcement must be decoupled from the update payload**. You don't embed the anti-rollback version in the firmware binary itself (that would require re-signing for every version bump). Instead, you put it in the *update manifest*—a signed metadata blob that accompanies the firmware image. The manifest contains:

- `minimum_version`: the lowest version this device must currently be at to accept the update
- `target_version`: the version this update will set after successful installation
- `firmware_hash`: SHA-256 of the payload
- `signature`: ECDSA or Ed25519 signature over the above fields

The bootloader checks: `current_version >= manifest.minimum_version` and `manifest.target_version > current_version`. If either fails, the update is rejected before any flash write occurs.

Fleet-wide enforcement means you maintain a *global version floor* in your backend. When a critical vulnerability is patched in version 42, you set the floor to 42. All manifests generated after that point carry `minimum_version: 42`. Devices stuck on version 41 must first install a special "bridge update" that brings them to 42 before they can receive any subsequent update. This prevents the classic "skip the security patch" attack.

## Key Commands / Configuration / Code

Here's a concrete manifest structure and verification flow I implemented today:

```c
// manifest.h — Anti-rollback manifest structure
typedef struct {
    uint32_t magic;             // 0xOTA1
    uint32_t target_version;    // e.g., 42
    uint32_t minimum_version;   // e.g., 40 (device must be >= 40)
    uint8_t  firmware_hash[32]; // SHA-256 of payload
    uint8_t  signature[64];     // Ed25519 signature
    uint32_t crc32;             // over all preceding fields
} __attribute__((packed)) ota_manifest_t;

// bootloader_verify.c — Core anti-rollback check
bool verify_anti_rollback(const ota_manifest_t *manifest) {
    // Read current version from TPM NVRAM index 0x01C00001
    uint32_t current_version;
    tpm_nv_read(0x01C00001, &current_version, sizeof(current_version));

    // Check 1: Device must be at or above minimum_version
    if (current_version < manifest->minimum_version) {
        // Device too old — needs bridge update
        log_error("Device version %u < minimum %u",
                  current_version, manifest->minimum_version);
        return false;
    }

    // Check 2: Target must be strictly greater than current
    if (manifest->target_version <= current_version) {
        log_error("Target %u not > current %u",
                  manifest->target_version, current_version);
        return false;
    }

    // If we get here, anti-rollback passes
    return true;
}

// After successful update, atomically increment the TPM counter
void commit_version(uint32_t new_version) {
    // Write new version to TPM NVRAM (write-locked after boot)
    tpm_nv_write(0x01C00001, &new_version, sizeof(new_version));
    // Lock the NVRAM index to prevent further writes until next boot
    tpm_nv_write_lock(0x01C00001);
}
```

For fleet-wide enforcement, the backend generates manifests with a dynamic `minimum_version`:

```bash
# Backend script to generate manifest with fleet floor
FLEET_FLOOR=$(curl -s https://ota.example.com/v1/fleet/floor)
TARGET_VERSION=42
PAYLOAD_HASH=$(sha256sum firmware.bin | cut -d' ' -f1)

# Build manifest JSON
cat <<EOF > manifest.json
{
  "target_version": $TARGET_VERSION,
  "minimum_version": $FLEET_FLOOR,
  "firmware_hash": "$PAYLOAD_HASH"
}
EOF

# Sign with HSM
openssl dgst -sha256 -sign fleet_key.pem -out manifest.sig manifest.json
```

## Common Pitfalls & Gotchas

**1. The "Bridge Update" Trap**
If you set `minimum_version` too aggressively (e.g., jump from 40 to 50), devices on version 39 are permanently stuck—they can never accept any update because every manifest requires `>= 40`. Always maintain a linear upgrade path. I now keep a "bridge update" slot in my release pipeline: a minimal image that only bumps the version counter without changing functionality.

**2. TPM NVRAM Write-Lock Ordering**
If you write the new version to TPM NVRAM *before* verifying the firmware hash, a power loss during verification leaves the device with a bumped version but corrupted firmware. The device is bricked—it thinks it's on version 42 but can't boot. Always verify the entire payload hash *first*, then write the version, then reboot.

**3. Clock-Free Version Comparison**
Never use wall-clock time for anti-rollback. Attackers can set the RTC back. Always use a monotonically increasing integer stored in tamper-resistant NVRAM. I use a 32-bit counter that wraps at 4 billion—enough for daily updates for 11 million years.

## Try It Yourself

1. **Implement a TPM NVRAM version read/write** on your dev board (e.g., Raspberry Pi with TPM 2.0). Write a test that simulates a rollback attempt and verify the bootloader rejects it.

2. **Build a bridge update pipeline**: Create two firmware images—one at version 10, one at version 20. Set `minimum_version: 15` on the version 20 manifest. Observe that devices on version 10 must first install a bridge update to version 15 before they can accept version 20.

3. **Write a fleet floor script** that queries your backend for the current floor, generates a manifest, and signs it. Then simulate an offline device that misses three floor bumps—verify it needs a bridge update.

## Next Up

Tomorrow I'll dive into **A/B Slot Swap Algorithms: Bank Swap vs Scratch-Area Swap**—the low-level flash management strategies that determine whether your device can survive a power loss mid-update. We'll compare dual-bank NOR flash swaps with single-bank scratch-area approaches, and I'll show you the exact flash controller registers to toggle for each method.
