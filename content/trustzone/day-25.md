---
title: "Day 25: TF-M: Trusted Firmware-M Architecture & Secure Services"
date: 2026-07-07
tags: ["til", "trustzone", "tfm", "secure-services"]
---

## What I Explored Today

Today I dug into the Trusted Firmware-M (TF-M) architecture, specifically how it structures secure services and manages the secure/non-secure boundary on Arm Cortex-M33 and M55 devices. I built TF-M from source for the Musca-B1 reference platform, traced the boot flow through the Secure Partition Manager (SPM), and wrote a minimal secure service that exposes a cryptographic hash via a veneer function. The key takeaway: TF-M is not a monolithic blob — it's a partitioned secure world runtime where each service runs in its own isolated partition with controlled access to hardware resources.

## The Core Concept

TF-M solves a fundamental tension in TrustZone-M systems: how do you provide multiple secure services (crypto, storage, attestation) without letting a bug in one service compromise all of them? The answer is the Secure Partition (SP) model. Each SP is a statically-defined execution context with its own stack, heap, and memory permissions. The SPM acts as a microkernel — it enforces isolation between SPs and mediates all calls from the non-secure world.

Why does this matter? In a naive TrustZone implementation, you'd put all secure logic in a single "secure world" binary. One buffer overflow in the crypto service could let an attacker read the secure storage keys. TF-M's SP model means each service is sandboxed: the crypto SP can't touch the storage SP's memory unless explicitly granted via the partition manifest.

The communication model is equally important. Non-secure callers use a veneer (a secure gateway function) that switches to secure mode. Inside TF-M, the SPM routes the call to the correct SP using a message-passing protocol called PSA Client API. The SP processes the request and returns results through the same veneer. This is not a simple function call — it involves saving/restoring secure context and validating every pointer crossing the boundary.

## Key Commands / Configuration / Code

### Building TF-M for Musca-B1

```bash
# Clone TF-M (v2.1.0 LTS)
git clone --depth 1 --branch TF-Mv2.1.0 https://git.trustedfirmware.org/TF-M/trusted-firmware-m.git
cd trusted-firmware-m

# Set up toolchain (ARM GCC 11.2)
export CROSS_COMPILE=arm-none-eabi-
export TFM_PLATFORM=arm/musca_b1

# Configure with Crypto + Internal Trusted Storage + Attestation
cmake -S . -B build_musca_b1 \
    -DTFM_PLATFORM=$TFM_PLATFORM \
    -DCMAKE_BUILD_TYPE=Release \
    -DTFM_PROFILE=profile_medium \
    -DCONFIG_TFM_SPM_BACKEND=IPC \
    -DTFM_PARTITION_CRYPTO=ON \
    -DTFM_PARTITION_INTERNAL_TRUSTED_STORAGE=ON \
    -DTFM_PARTITION_ATTESTATION=ON

# Build (takes ~5 minutes)
cmake --build build_musca_b1 -- -j$(nproc)

# Output binaries in build_musca_b1/install/outputs/
ls -la build_musca_b1/install/outputs/
# tfm_s_ns_signed.bin  (combined secure + non-secure image)
```

### Secure Partition Manifest (crypto_sp.yaml)

```yaml
# File: secure_fw/partitions/crypto/crypto_sp.yaml
{
  "psa_framework_version": 1.1,
  "name": "TFM_CRYPTO",
  "type": "PSA-ROT",
  "priority": 255,
  "entry_point": "crypto_main",
  "stack_size": 0x800,       # 2KB stack
  "heap_size": 0x400,        # 1KB heap
  "services": [
    {
      "name": "TFM_CRYPTO_SHA256",
      "sid": 0x00000001,
      "non_secure_clients": true,
      "connection_based": false,
      "version": 1,
      "version_policy": "strict"
    }
  ],
  "memory_regions": [
    {
      "name": "CRYPTO_DATA",
      "permissions": "READ-WRITE",
      "start": 0x3000,
      "size": 0x1000
    }
  ],
  "irq": [
    {
      "line_num": 10,
      "signal": "crypto_irq_signal"
    }
  ]
}
```

### Calling a Secure Service from Non-Secure (C code)

```c
// non_secure_app.c
#include "psa/crypto.h"
#include "tfm_ns_interface.h"

int main(void) {
    psa_status_t status;
    uint8_t hash[32];
    const uint8_t msg[] = "Hello TrustZone!";

    // Initialize PSA Crypto API
    status = psa_crypto_init();
    assert(status == PSA_SUCCESS);

    // Compute SHA-256 via TF-M secure service
    size_t hash_len;
    status = psa_hash_compute(
        PSA_ALG_SHA_256,      // algorithm
        msg, sizeof(msg),     // input
        hash, sizeof(hash),   // output buffer
        &hash_len             // actual length
    );
    assert(status == PSA_SUCCESS);

    // hash now contains the SHA-256 digest
    // This call went through:
    //   NS code -> veneer -> SPM -> Crypto SP -> hardware crypto accelerator
    return 0;
}
```

## Common Pitfalls & Gotchas

**1. Stack overflow in secure partitions is silent death.** TF-M partitions have fixed stack sizes (configured in the YAML manifest). If your service exceeds its stack, the SPM will trigger a secure fault with no debug output unless you've enabled `CONFIG_TFM_SPM_BACKEND=SFN` (function call mode) with stack canaries. Always add 20% headroom to your stack size and test with worst-case recursion.

**2. Non-secure callers must use the PSA Client API, not direct function calls.** I've seen engineers try to call secure functions by address after reading the linker map. This fails because the SPM enforces that all secure entry points go through the veneer table. The veneer address is randomized at build time (ASLR for secure world). Use `psa_call()` or the generated NS interface headers — never hardcode addresses.

**3. Partition manifest changes require a full rebuild, not just re-linking.** The SPM uses the manifest to generate memory protection unit (MPU) configurations at compile time. If you add a new service or change memory regions, `cmake --build` will detect the change, but I've seen stale object files cause subtle bugs. Always do `rm -rf build_* && cmake ...` when modifying partition manifests.

## Try It Yourself

1. **Add a custom secure partition** that exposes a "get_device_id" service. Create a new YAML manifest under `secure_fw/partitions/`, implement the service handler that reads a unique ID from a hardware register (e.g., the MCU's UID), and register it in the partition list. Build and verify the service is callable from non-secure.

2. **Enable stack overflow detection** by setting `-DCONFIG_TFM_SPM_BACKEND=SFN -DCONFIG_TFM_STACK_OVERFLOW_CHECK=ON` in your cmake command. Then intentionally overflow a partition's stack (e.g., by deep recursion) and observe the fault handler output on UART.

3. **Profile the IPC overhead** of a secure service call. Use a DWT cycle counter in non-secure code to measure the round-trip time for `psa_hash_compute()` with a 1KB input. Compare against a software SHA-256 running entirely in non-secure world. Document the cycle cost of the SPM context switch.

## Next Up

Tomorrow we dive into the **TF-M PSA Crypto API: Key Management & Crypto Ops** — how to generate, import, and use cryptographic keys entirely within the secure partition, including persistent key storage and hardware-backed key derivation. We'll also cover the PSA key ID lifecycle and the gotchas of key policy enforcement.
