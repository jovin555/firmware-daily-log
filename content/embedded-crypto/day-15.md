---
title: "Day 15: Key Rotation & Lifecycle Management in the Field"
date: 2026-07-15
tags: ["til", "embedded-crypto", "key-rotation", "lifecycle"]
---

## What I Explored Today

Today I dug into the operational reality of key rotation and lifecycle management for devices already deployed in the field. Unlike development-stage key provisioning, field rotation must handle constrained bandwidth, potential power loss mid-update, and the absolute requirement that the device never enters a state where no valid key exists. I worked through the full lifecycle stages—from injection through active use, rotation, and finally revocation—and implemented a two-phase commit pattern for secure key replacement on a Cortex-M4 target.

## The Core Concept

Key rotation is not simply "write a new key over the old one." The core problem is atomicity: you must guarantee that at any point during the rotation, the device can still authenticate or decrypt. A power failure at the wrong moment can brick the device if the old key is erased before the new key is fully written and verified.

The lifecycle model I use has five states:

1. **Injection** – Key is provisioned at manufacturing or first boot (often via a secure element or HSM-signed blob).
2. **Active** – Key is in use for cryptographic operations.
3. **Rotation Pending** – A new key has been received and stored in a staging slot, but the old key is still active.
4. **Active (New)** – After verification, the new key becomes active; the old key is moved to a "retired" slot.
5. **Revoked** – Key is marked invalid and removed from all operational slots.

The critical transition is from "Active" to "Rotation Pending" to "Active (New)." Never go directly from Active to Active (New) without a staging step.

## Key Commands / Configuration / Code

Below is a simplified but functional implementation of a two-phase key rotation for an AES-128 key stored in internal flash (emulated EEPROM). The device uses a bootloader that checks a "key slot valid" flag before allowing normal operation.

```c
// key_lifecycle.h
typedef enum {
    KEY_STATE_EMPTY = 0,
    KEY_STATE_ACTIVE,
    KEY_STATE_STAGED,   // new key received but not yet activated
    KEY_STATE_RETIRED   // old key after successful rotation
} key_state_t;

typedef struct {
    uint8_t key[16];        // AES-128 key material
    key_state_t state;      // lifecycle state
    uint32_t version;       // monotonic version counter
    uint32_t crc32;         // integrity check over key + state + version
} key_slot_t;

// Must be placed in a flash page that can be erased/written atomically
// (e.g., a dedicated 4KB flash page with two slots)
#define KEY_SLOT_A_ADDR   0x0803F000
#define KEY_SLOT_B_ADDR   0x0803F100
```

```c
// key_rotation.c
#include "key_lifecycle.h"
#include "flash_driver.h"   // assumes flash_write(), flash_erase_page()
#include "crc32_hw.h"       // hardware CRC32 peripheral

static volatile uint32_t rotation_in_progress = 0;

/**
 * @brief  Stage a new key for rotation.
 *         Writes the new key to the staging slot (the inactive slot).
 *         Does NOT affect the active key.
 * @param  new_key: 16-byte AES key
 * @param  new_version: must be > current active version
 * @return 0 on success, -1 on failure
 */
int key_rotation_stage(const uint8_t *new_key, uint32_t new_version) {
    key_slot_t current_active;
    key_slot_t staged;
    uint32_t active_version;

    // Read current active key to check version monotonicity
    flash_read(KEY_SLOT_A_ADDR, (uint8_t*)&current_active, sizeof(key_slot_t));
    if (current_active.state == KEY_STATE_ACTIVE) {
        active_version = current_active.version;
    } else {
        // Check slot B
        flash_read(KEY_SLOT_B_ADDR, (uint8_t*)&current_active, sizeof(key_slot_t));
        if (current_active.state == KEY_STATE_ACTIVE) {
            active_version = current_active.version;
        } else {
            return -1; // No active key found — cannot rotate
        }
    }

    if (new_version <= active_version) {
        return -1; // Version must increase monotonically
    }

    // Determine which slot to use for staging (the one NOT currently active)
    uint32_t staging_addr = (current_active.state == KEY_STATE_ACTIVE) ?
                            KEY_SLOT_B_ADDR : KEY_SLOT_A_ADDR;

    // Prepare staged slot
    memset(&staged, 0, sizeof(key_slot_t));
    memcpy(staged.key, new_key, 16);
    staged.state = KEY_STATE_STAGED;
    staged.version = new_version;
    staged.crc32 = crc32_calculate((uint8_t*)&staged, offsetof(key_slot_t, crc32));

    // Erase the staging page (must be done before write)
    flash_erase_page(staging_addr & ~0xFFF); // 4KB page alignment
    flash_write(staging_addr, (uint8_t*)&staged, sizeof(key_slot_t));

    // Verify the write
    key_slot_t verify;
    flash_read(staging_addr, (uint8_t*)&verify, sizeof(key_slot_t));
    if (verify.crc32 != staged.crc32) {
        return -1; // Write verification failed
    }

    return 0;
}

/**
 * @brief  Commit the staged key, making it the active key.
 *         This is the atomic "point of no return."
 *         Old active key is marked RETIRED.
 * @return 0 on success, -1 if no staged key exists
 */
int key_rotation_commit(void) {
    if (rotation_in_progress) return -1;
    rotation_in_progress = 1;

    key_slot_t slot_a, slot_b;
    flash_read(KEY_SLOT_A_ADDR, (uint8_t*)&slot_a, sizeof(key_slot_t));
    flash_read(KEY_SLOT_B_ADDR, (uint8_t*)&slot_b, sizeof(key_slot_t));

    // Find staged slot
    key_slot_t *staged = NULL;
    uint32_t staged_addr = 0;
    if (slot_a.state == KEY_STATE_STAGED) {
        staged = &slot_a;
        staged_addr = KEY_SLOT_A_ADDR;
    } else if (slot_b.state == KEY_STATE_STAGED) {
        staged = &slot_b;
        staged_addr = KEY_SLOT_B_ADDR;
    } else {
        rotation_in_progress = 0;
        return -1; // No staged key
    }

    // Find active slot and mark it RETIRED
    key_slot_t *active = (staged_addr == KEY_SLOT_A_ADDR) ? &slot_b : &slot_a;
    uint32_t active_addr = (staged_addr == KEY_SLOT_A_ADDR) ? KEY_SLOT_B_ADDR : KEY_SLOT_A_ADDR;

    if (active->state == KEY_STATE_ACTIVE) {
        active->state = KEY_STATE_RETIRED;
        active->crc32 = crc32_calculate((uint8_t*)active, offsetof(key_slot_t, crc32));
        flash_erase_page(active_addr & ~0xFFF);
        flash_write(active_addr, (uint8_t*)active, sizeof(key_slot_t));
    }

    // Promote staged to ACTIVE
    staged->state = KEY_STATE_ACTIVE;
    staged->crc32 = crc32_calculate((uint8_t*)staged, offsetof(key_slot_t, crc32));
    flash_erase_page(staged_addr & ~0xFFF);
    flash_write(staged_addr, (uint8_t*)staged, sizeof(key_slot_t));

    rotation_in_progress = 0;
    return 0;
}
```

**Bootloader check (simplified):**

```c
// In bootloader main()
key_slot_t slot_a, slot_b;
flash_read(KEY_SLOT_A_ADDR, (uint8_t*)&slot_a, sizeof(key_slot_t));
flash_read(KEY_SLOT_B_ADDR, (uint8_t*)&slot_b, sizeof(key_slot_t));

if (slot_a.state == KEY_STATE_ACTIVE || slot_b.state == KEY_STATE_ACTIVE) {
    // At least one valid key exists — proceed to application
    jump_to_app();
} else {
    // No valid key — enter recovery mode (e.g., USB DFU)
    enter_recovery_mode();
}
```

## Common Pitfalls & Gotchas

1. **Power loss during flash erase/write** – Flash erase is not atomic on most MCUs; a power cut mid-erase can leave the page in an indeterminate state. Mitigation: use a dual-slot scheme (A/B) and always verify CRC after write. Never erase the active slot before the staged slot is verified.

2. **Version rollback attacks** – An attacker could try to force a device to accept an older, compromised key. Always enforce monotonic version numbers. Store the version in a separate monotonic counter (e.g., a one-time programmable region) if possible.

3. **Stale staged keys** – If a staged key is never committed (e.g., due to a failed network request), it sits in flash indefinitely. Implement a timeout: if a staged key is older than N hours, mark it as invalid and allow a new staging attempt. Otherwise, the staging slot is blocked.

## Try It Yourself

1. **Implement a dual-slot key manager** on your dev board (STM32, nRF52, or similar). Use two flash pages as key slots. Write a test that stages a key, then simulates a power failure by resetting before commit. Verify the device still boots with the old key.

2. **Add a monotonic version counter** to your key slot structure. Write a test that attempts to stage a key with a version equal to or less than the current active version. Confirm the API returns an error.

3. **Extend the bootloader** to check for a "staged but not committed" key on boot. If found, automatically commit it (with a CRC check) before jumping to the application. This handles the case where a commit was interrupted.

## Next Up

Tomorrow we move from software key management to hardware acceleration. I'll explore **Hardware Crypto Accelerators: CryptoCell, SE05x & ATECC608** — how to offload AES/ECC operations, secure key storage in tamper-resistant silicon, and the API differences between these common secure elements.
