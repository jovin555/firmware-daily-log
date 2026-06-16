---
title: "Day 04: TF-M: Trusted Firmware-M Architecture & Secure Services"
date: 2026-06-16
tags: ["til", "trustzone", "tfm", "secure-services"]
---

## What I Explored Today

Today I dove into the Trusted Firmware-M (TF-M) architecture—the reference implementation of the PSA (Platform Security Architecture) for Arm Cortex-M devices with TrustZone. I built TF-M from source for the MPS2 AN521 FPGA board, traced the boot flow from BL2 (the second-stage bootloader) into the Secure Partition Manager (SPM), and then exercised two secure services: the Internal Trusted Storage (ITS) and the Crypto service. The goal was to understand how TF-M partitions the secure world into isolated "secure partitions" and how non-secure callers invoke those services via the PSA Client API.

## The Core Concept

TF-M is not a monolithic secure firmware blob. It's a microkernel-like architecture where the Secure Partition Manager (SPM) runs in the highest privilege level (Secure EL3 on Cortex-A, or Secure privileged on Cortex-M) and hosts multiple isolated *secure partitions*. Each partition is a logical security domain with its own memory region, stack, and entry points. The key insight: even within the secure world, we enforce isolation. A compromise in the Crypto partition should not leak keys from the ITS partition.

Why does this matter? In production IoT devices, you need to guarantee that:
- Cryptographic keys never leak to non-secure code.
- Firmware update authentication cannot be bypassed.
- Secure storage (e.g., device certificates) is tamper-resistant.

TF-M achieves this through hardware-enforced memory protection (MPU/SAU) and a strict message-passing model. Non-secure callers use `psa_call()` to invoke secure functions; the SPM validates the message, routes it to the correct partition, and returns the result—all without shared memory or direct function pointers crossing the security boundary.

## Key Commands / Configuration / Code

### Building TF-M for MPS2 AN521

I used the TF-M v2.1.0 release with the GNU Arm Embedded toolchain (gcc-arm-none-eabi-10.3-2021.10).

```bash
# Clone and checkout
git clone https://git.trustedfirmware.org/TF-M/trusted-firmware-m.git
cd trusted-firmware-m
git checkout TF-Mv2.1.0

# Initialize submodules (mbedtls, mcuboot, etc.)
git submodule update --init --recursive

# Configure for AN521 with BL2 bootloader and ITS + Crypto services
cmake -S . -B build_an521 \
    -DTFM_PLATFORM=arm/mps2/an521 \
    -DTFM_TOOLCHAIN_FILE=toolchain_GNUARM.cmake \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DTFM_ISOLATION_LEVEL=2 \
    -DCONFIG_TFM_BOOTLOADER=ON \
    -DCONFIG_TFM_PARTITION_INTERNAL_TRUSTED_STORAGE=ON \
    -DCONFIG_TFM_PARTITION_CRYPTO=ON

# Build
cmake --build build_an521 -- -j$(nproc)
```

The resulting binaries land in `build_an521/install/outputs/AN521/`. The key files:
- `bl2.bin` — MCUboot second-stage bootloader (authenticates and loads SPM)
- `tfm_s.bin` — Secure image (SPM + partitions)
- `tfm_ns.bin` — Non-secure example application

### Invoking a Secure Service from Non-Secure (PSA Client API)

Here's a minimal non-secure caller that stores a key in ITS:

```c
#include "psa/client.h"
#include "psa/internal_trusted_storage.h"

// Handle to the ITS secure partition (pre-defined by TF-M)
psa_handle_t its_handle = PSA_HANDLE_FROM_SID(PSA_ITS_SID);

// Data to store
const uint8_t key_data[] = {0x01, 0x02, 0x03, 0x04};
psa_storage_uid_t uid = 42;  // Application-defined UID

// Prepare the message
psa_invec in_vec[] = {
    { .base = &uid, .len = sizeof(uid) },
    { .base = key_data, .len = sizeof(key_data) }
};

// Call the secure service (PSA_ITS_SET is the function ID)
psa_status_t status = psa_call(its_handle, PSA_ITS_SET, in_vec, 2, NULL, 0);
if (status != PSA_SUCCESS) {
    // Handle error — likely PSA_ERROR_CONNECTION_REFUSED if partition not loaded
}
```

The SPM receives this call, validates the invec pointers (they must point to non-secure memory), copies the data into the ITS partition's private buffer, and writes it to the flash-backed storage.

### Tracing the Boot Flow

I added debug UART output to `bl2/main.c` and `spm/init.c`:

```c
// In bl2/main.c (after image authentication)
LOG_INF("BL2: Authenticated SPM image at offset 0x%x", image_offset);

// In spm/init.c (after partition loading)
LOG_INF("SPM: Loaded %d secure partitions", partition_count);
```

On boot, the serial output shows:
```
[INF] BL2: Authenticated SPM image at offset 0x20000
[INF] SPM: Loaded 3 secure partitions (ITS, Crypto, TFM_SP_SERVICE)
[INF] SPM: Non-secure callable at 0x10000000
```

## Common Pitfalls & Gotchas

1. **Isolation Level Mismatch** — TF-M supports isolation levels 1, 2, and 3. Level 2 (peripheral isolation) requires the SAU to be configured correctly. If you set `-DTFM_ISOLATION_LEVEL=2` but your platform's SAU region definitions are wrong, the SPM will fault on partition context switch. Always verify `SAU_NS_REGION` settings in `platform/ext/target/<your_board>/partition/region_defs.h`.

2. **Invec/Outvec Buffer Alignment** — The PSA Client API requires that all buffer pointers in `psa_invec` and `psa_outvec` be aligned to 4 bytes. Passing a misaligned pointer (e.g., a packed struct field) causes `PSA_ERROR_PROGRAMMER_ERROR` silently. I wasted an hour debugging this—the SPM doesn't print a warning.

3. **BL2 Image Size Limits** — MCUboot has a hardcoded maximum image size (default 0x100000 bytes). If your SPM image exceeds this, BL2 will refuse to load it with "Image too large". Check `MCUBOOT_IMAGE_SLOT_SIZE` in `bl2/ext/mcuboot/boot/bootutil/include/bootutil/image.h` and increase if needed.

## Try It Yourself

1. **Build TF-M for your own board** — Pick a supported platform (e.g., `arm/mps3/an547` or `nuvoton/m2354`). Run the cmake command above with your `TFM_PLATFORM`. Flash the three binaries and observe the boot log. Verify that `BL2` authenticates the SPM image before jumping to it.

2. **Write a non-secure application that reads back the stored key** — Extend the code example above: after `psa_call(PSA_ITS_SET)`, call `psa_call(PSA_ITS_GET)` with an outvec to retrieve the data. Print the buffer and confirm it matches what you stored.

3. **Add a new secure partition** — Create a simple "Hello World" partition that returns a string. You'll need to:
   - Define a new SID in `interface/include/psa_manifest/sid.h`
   - Write a partition source file in `secure_fw/partitions/`
   - Add it to the build with `-DCONFIG_TFM_PARTITION_MY_PARTITION=ON`
   - Rebuild and call it from non-secure using `psa_connect()` + `psa_call()`

## Next Up

Tomorrow I'll dig into the **TF-M PSA Crypto API: Key Management & Crypto Ops** — how to generate, import, and use keys entirely within the secure partition, including hardware-backed key storage and authenticated encryption with GCM. We'll also cover the key policy system that prevents key extraction.
