---
title: "Day 11: Random Number Generation: TRNG vs PRNG & Entropy Sources"
date: 2026-07-11
tags: ["til", "embedded-crypto", "trng", "entropy"]
---

## What I Explored Today

Today I dug into the critical difference between True Random Number Generators (TRNGs) and Pseudo-Random Number Generators (PRNGs) in embedded systems. I focused on how entropy sources work at the hardware level, how to properly seed PRNGs, and why a weak RNG is the single fastest way to break your cryptographic system. I also tested entropy harvesting on a Cortex-M4 MCU using its on-chip TRNG peripheral and compared it to a software-only PRNG approach.

## The Core Concept

Randomness in cryptography isn't about "unpredictable" in the colloquial sense—it's about **computational indistinguishability** from true randomness. If an attacker can predict your key, your AES-256 might as well be ROT13.

**TRNGs** exploit physical phenomena: thermal noise in semiconductor junctions, clock jitter between independent oscillators, or radioactive decay. On an MCU, a typical TRNG peripheral amplifies analog noise from a reverse-biased PN junction, samples it, and passes it through a von Neumann debiasing circuit to remove bias. The output is true entropy—but it's slow. A typical STM32 TRNG yields about 72 Mbps of raw random data, but post-processing (health tests, conditioning) reduces that significantly.

**PRNGs** (specifically CSPRNGs—Cryptographically Secure PRNGs) are deterministic algorithms that expand a small seed into a long stream of bits that appear random. The gold standard is `CTR_DRBG` (NIST SP 800-90A), which uses AES in counter mode. Given the same seed, you get the same output—which is why seeding is everything. A PRNG without good entropy is just a complicated way to generate the same "random" numbers every boot.

The engineering reality: you almost always use **both**. The TRNG provides a high-entropy seed (say, 256 bits) to initialize a CSPRNG. The CSPRNG then provides fast, high-quality random numbers for session keys, nonces, and IVs. You reseed periodically (every N requests or every T seconds) to limit the damage if the internal state is ever leaked.

## Key Commands / Configuration / Code

Here's a practical example using an STM32L4's hardware TRNG to seed a software CTR_DRBG. I'm using Mbed TLS for the CSPRNG.

```c
#include "stm32l4xx_hal.h"
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/entropy.h"

RNG_HandleTypeDef hrng;

// Initialize STM32 hardware TRNG peripheral
void trng_init(void) {
    __HAL_RCC_RNG_CLK_ENABLE();
    hrng.Instance = RNG;
    HAL_RNG_Init(&hrng);
    
    // Run built-in health tests (NIST SP 800-90B compliant)
    // STM32 TRNG performs continuous checks: stuck fault detector,
    // and a 2-bit adjacency test on the raw noise output
    if (HAL_RNG_HealthTest(&hrng) != HAL_OK) {
        // In production: trigger error handler, never proceed
        Error_Handler();
    }
}

// Harvest 32 bytes of true entropy from hardware TRNG
int trng_get_entropy(void *data, size_t len, size_t *olen) {
    uint32_t random_word;
    uint8_t *buf = (uint8_t *)data;
    size_t collected = 0;
    
    while (collected < len) {
        // HAL_RNG_GenerateRandomNumber blocks until valid entropy is ready
        // Internal debiasing removes DC bias from the raw noise
        if (HAL_RNG_GenerateRandomNumber(&hrng, &random_word) != HAL_OK) {
            return MBEDTLS_ERR_ENTROPY_SOURCE_FAILED;
        }
        // Copy 4 bytes into output buffer
        buf[collected++] = (random_word >> 0) & 0xFF;
        buf[collected++] = (random_word >> 8) & 0xFF;
        buf[collected++] = (random_word >> 16) & 0xFF;
        buf[collected++] = (random_word >> 24) & 0xFF;
    }
    *olen = collected;
    return 0;
}

// Seed the CSPRNG with hardware entropy
void crypto_rng_init(mbedtls_ctr_drbg_context *drbg) {
    mbedtls_entropy_context entropy;
    uint8_t seed[32];  // 256-bit seed from TRNG
    
    mbedtls_entropy_init(&entropy);
    mbedtls_ctr_drbg_init(drbg);
    
    // Register our hardware entropy source with Mbed TLS
    mbedtls_entropy_add_source(&entropy, trng_get_entropy, NULL,
                               32,  // minimum entropy required
                               MBEDTLS_ENTROPY_SOURCE_STRONG);
    
    // Seed the CTR_DRBG with 32 bytes of true entropy
    // Personalization string adds domain separation
    const char *pers = "my_embedded_app_v1.0";
    mbedtls_ctr_drbg_seed(drbg, mbedtls_entropy_func, &entropy,
                          (const unsigned char *)pers, strlen(pers));
    
    // Generate first random bytes to verify the DRBG is working
    uint8_t test_buf[16];
    mbedtls_ctr_drbg_random(drbg, test_buf, sizeof(test_buf));
}
```

On Linux-based embedded systems (Raspberry Pi, BeagleBone), you can check entropy availability:

```bash
# Check available entropy pool (should be > 256 bits)
cat /proc/sys/kernel/random/entropy_avail

# Monitor entropy rate (useful for headless devices)
watch -n 1 cat /proc/sys/kernel/random/entropy_avail

# For devices with hardware TRNG, ensure the driver is loaded
# (e.g., on i.MX platforms with CAAM)
dmesg | grep -i rng
```

## Common Pitfalls & Gotchas

1. **Using `rand()` from libc for anything cryptographic.** This is the cardinal sin. `rand()` is typically a linear congruential generator (LCG) with a 32-bit state. An attacker can predict the entire sequence after observing just two outputs. I've seen production IoT devices use `srand(time(NULL))` for TLS key generation—don't be that engineer.

2. **Assuming hardware TRNG output is always good.** TRNGs can fail. A stuck-at fault (e.g., the noise source dies) produces constant output. Always run the manufacturer's health tests at boot and implement runtime continuous checks. The STM32 TRNG has a built-in "stuck fault detector" that flags if 64 consecutive bits are identical. If you ignore that error flag, you're back to deterministic output.

3. **Not reseeding the PRNG.** A CSPRNG that runs for months without reseeding is a ticking time bomb. If an attacker ever recovers the internal state (via a side-channel or memory dump), they can predict all future outputs. Reseed at least every 2^48 requests (NIST SP 800-90A recommendation) or every 24 hours—whichever comes first.

## Try It Yourself

1. **Audit your current project's RNG usage.** Find every call to `rand()`, `random()`, or `srand()`. Replace them with a CSPRNG (Mbed TLS `ctr_drbg`, OpenSSL `RAND_bytes`, or the Linux `getrandom()` syscall). Measure the performance difference.

2. **Test your hardware TRNG's entropy quality.** If you have an MCU with a TRNG, write a test that collects 1 MB of raw TRNG output and runs it through the `dieharder` or `PractRand` test suite. Look for bias patterns—if you see failures, your debiasing circuit may need tuning.

3. **Implement a reseed timer.** Add a periodic timer (e.g., every 10 minutes) that calls `mbedtls_ctr_drbg_reseed()` with fresh entropy from your hardware source. Verify that the reseed doesn't block your main application loop (use a separate low-priority task or interrupt).

## Next Up

Tomorrow: **Key Derivation Functions: HKDF & PBKDF2** — why you should never use a raw password as a key, how to derive multiple keys from a single master secret, and the right way to add salt and iteration counts for embedded devices with limited CPU.
