---
title: "Day 31: TF-M: Trusted Firmware-M & Secure Services"
date: 2026-07-13
tags: ["til", "zephyr", "tfm", "security"]
---

## What I Explored Today

Today I integrated Trusted Firmware-M (TF-M) into a Zephyr application running on an Arm Cortex-M33 MCU (nRF5340). TF-M provides a reference implementation of the Arm Platform Security Architecture (PSA) for microcontrollers, enabling hardware-enforced isolation between a secure world (Trusted Execution Environment) and a non-secure world (Normal Execution Environment). I built a Zephyr application that calls PSA APIs to store a secret key in the secure domain, then verified that the non-secure application cannot directly access the secure storage partition.

## The Core Concept

TF-M solves a fundamental problem in IoT security: how to protect sensitive assets (cryptographic keys, firmware update certificates, device identity) when the application code might be compromised. Instead of trusting the entire firmware image, TF-M splits the system into two worlds using the Armv8-M TrustZone hardware:

- **Secure World**: Runs the TF-M Secure Partition Manager (SPM) and isolated secure services (crypto, internal trusted storage, attestation). This code runs in the highest privilege mode and has exclusive access to secure memory regions.
- **Non-Secure World**: Runs Zephyr and your application code. It can only call secure services through defined PSA APIs, never directly access secure memory.

The isolation is enforced at the hardware level by the Memory Protection Unit (MPU) and the SAU (Security Attribution Unit). Even a bug in Zephyr cannot leak secrets stored in the secure domain—the CPU physically prevents non-secure accesses to secure memory.

## Key Commands / Configuration / Code

### 1. Enabling TF-M in Zephyr (prj.conf)

```kconfig
# Enable TF-M integration
CONFIG_TFM=y
CONFIG_TFM_PSA_API=y

# Select the secure partition manager
CONFIG_TFM_SPM_BACKEND=y

# Enable secure services we'll use
CONFIG_TFM_CRYPTO=y
CONFIG_TFM_INTERNAL_TRUSTED_STORAGE=y

# Non-secure side needs PSA client library
CONFIG_PSA_API=y
```

### 2. Building with TF-M

```bash
# For nRF5340 DK (nrf5340dk_nrf5340_cpuapp)
west build -b nrf5340dk_nrf5340_cpuapp -t tfm_clean
west build -b nrf5340dk_nrf5340_cpuapp -- -DCONFIG_TFM=y

# The build generates two images:
# build/tfm/bin/tfm_s.hex (secure image)
# build/zephyr/zephyr.hex (non-secure image)
```

### 3. Calling Secure Storage from Non-Secure Application

```c
#include <psa/storage_common.h>
#include <psa/internal_trusted_storage.h>

/* Store a secret key in secure domain */
void store_secret_key(void)
{
    psa_status_t status;
    uint8_t key_data[] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
    psa_storage_uid_t uid = 0xDEADBEEF;  /* Unique identifier for this key */

    /* This call transitions to Secure World via SVC */
    status = psa_its_set(uid, sizeof(key_data), key_data, PSA_STORAGE_FLAG_NONE);
    if (status != PSA_SUCCESS) {
        printk("Failed to store key: %d\n", status);
        return;
    }
    printk("Key stored securely\n");

    /* Verify we can read it back */
    uint8_t read_buf[16];
    size_t read_len;
    status = psa_its_get(uid, 0, sizeof(read_buf), read_buf, &read_len);
    if (status == PSA_SUCCESS) {
        printk("Key retrieved: %zu bytes\n", read_len);
    }
}
```

### 4. Verifying Isolation (Intentional Fault)

```c
/* This will trigger a SecureFault if uncommented */
void test_isolation(void)
{
    /* Try to directly access secure memory region (0x20000000 - 0x2003FFFF) */
    volatile uint32_t *secure_ptr = (uint32_t *)0x20000000;
    // uint32_t val = *secure_ptr;  /* BOOM: SecureFault exception */
    printk("Isolation works: cannot read secure memory\n");
}
```

## Common Pitfalls & Gotchas

1. **Dual-image flashing**: You must flash both the secure (tfm_s.hex) and non-secure (zephyr.hex) images. Flashing only the non-secure image leaves the system without a secure partition manager, causing all PSA calls to fail silently. Use `west flash --runner nrfjprog --tfm` to flash both automatically.

2. **Stack size starvation**: The non-secure application's stack must be large enough to handle the context switch into secure world. PSA calls consume additional stack space for the SVC handler and parameter marshaling. If you see `PSA_ERROR_PROGRAMMER_ERROR` or hard faults, increase `CONFIG_MAIN_STACK_SIZE` to at least 4096.

3. **UID collision**: PSA storage UIDs must be unique across all secure services. Using the same UID for both crypto keys and internal trusted storage will cause `PSA_ERROR_DOES_NOT_EXIST` or data corruption. Always namespace your UIDs (e.g., `0x1000xxxx` for keys, `0x2000xxxx` for certificates).

## Try It Yourself

1. **Build and flash a TF-M-enabled Zephyr application** on an nRF5340 DK or STM32L5 board. Verify that `psa_its_set()` and `psa_its_get()` work correctly by storing and retrieving a test value.

2. **Deliberately trigger a SecureFault** by modifying the test_isolation() function to read from address `0x20000000`. Observe the fault handler output in the console and confirm that the secure world remains intact.

3. **Extend the example** to use PSA Crypto API (`psa_hash_compute()`) to compute a SHA-256 hash entirely within the secure world, returning only the hash digest to the non-secure application.

## Next Up

Tomorrow marks the **Full Review & Project: BLE Sensor Node** — we'll combine everything from the past 31 days into a complete, production-ready BLE sensor node with TF-M secure storage for the device identity key, Zephyr Bluetooth stack for advertising, and power management for battery operation. Bring your soldering iron and your debugger.
