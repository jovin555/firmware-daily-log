---
title: "Day 17: mbedTLS & wolfSSL: Embedded TLS Stack Internals"
date: 2026-07-17
tags: ["til", "embedded-crypto", "mbedtls", "wolfssl"]
---

## What I Explored Today

Today I dove into the internal architectures of the two dominant embedded TLS stacks: mbedTLS (formerly PolarSSL, now part of Arm) and wolfSSL (formerly CyaSSL). I focused on how each handles hardware crypto acceleration, memory allocation strategies, and session management in constrained environments. The key takeaway: both libraries expose hardware crypto hooks, but their design philosophies differ significantly—mbedTLS favors modularity through configurable compile-time options, while wolfSSL prioritizes a smaller footprint with tighter integration hooks for hardware accelerators.

## The Core Concept

When you’re building a TLS stack for a microcontroller with 256KB of flash and 64KB of RAM, you can’t just drop in OpenSSL. The core challenge is balancing cryptographic agility with resource constraints. Both mbedTLS and wolfSSL solve this by providing abstraction layers for hardware crypto engines (like AES-GCM accelerators on STM32 or NXP LPC parts), but they do it differently.

**mbedTLS** uses a PSA (Platform Security Architecture) abstraction layer. You define `MBEDTLS_AES_ALT` to replace software AES with your hardware driver. The library then calls your `mbedtls_aes_*` functions instead of its own. This is clean but requires you to implement the entire API surface.

**wolfSSL** takes a more aggressive approach with its `wolfSSL_Init` and `wolfCrypt_Init` hooks. It provides a `wolfSSL_CTX_set_crypto_operations` callback that lets you intercept individual operations (like `AES_encrypt`) without replacing entire modules. This is lighter for partial acceleration.

Both libraries support hardware RNG, but wolfSSL’s `WC_RNG` structure allows direct injection of hardware entropy via `wc_RNG_GenerateBlock` callbacks, while mbedTLS expects you to implement `mbedtls_hardware_poll()`.

## Key Commands / Configuration / Code

### mbedTLS: Hardware AES Acceleration via ALT Implementation

```c
// In your mbedtls_config.h, enable ALT implementation
#define MBEDTLS_AES_ALT

// Then implement the hardware-specific functions
#include "mbedtls/aes.h"
#include "stm32h7_hal.h"  // Example: STM32 hardware crypto

int mbedtls_aes_setkey_enc(mbedtls_aes_context *ctx,
                           const unsigned char *key,
                           unsigned int keybits) {
    // Configure STM32 AES peripheral
    HAL_CRYP_Init(&ctx->hcryp);
    HAL_CRYP_SetKey(&ctx->hcryp, key, keybits);
    return 0;
}

int mbedtls_aes_crypt_ecb(mbedtls_aes_context *ctx,
                          int mode,
                          const unsigned char input[16],
                          unsigned char output[16]) {
    HAL_CRYP_AESECB(&ctx->hcryp, input, 16, output, 1000);
    return 0;
}
```

### wolfSSL: Hardware Crypto via wolfCrypt Callbacks

```c
// Enable hardware acceleration in user_settings.h
#define WOLFSSL_CRYPT_HW_MUTEX
#define HAVE_AES_ACCELERATION

// Register hardware callbacks at runtime
#include <wolfssl/wolfcrypt/settings.h>
#include <wolfssl/wolfcrypt/aes.h>

static int my_aes_encrypt(Aes* aes, byte* out, const byte* in,
                          word32 sz) {
    // Call your hardware AES engine
    hw_aes_encrypt(aes->key, aes->rounds, in, out, sz);
    return 0;
}

void init_hardware_crypto(void) {
    wolfCrypt_Init();
    wolfSSL_SetAesEncryptCb(my_aes_encrypt);
}
```

### Memory Allocation Strategy Comparison

```c
// mbedTLS: Static memory pools via MBEDTLS_MEMORY_BUFFER_ALLOC_C
#define MBEDTLS_MEMORY_BUFFER_ALLOC_C
static unsigned char memory_buf[64 * 1024];  // 64KB pool

int main() {
    mbedtls_memory_buffer_alloc_init(memory_buf, sizeof(memory_buf));
    // All subsequent mbedtls_* allocations come from this pool
}

// wolfSSL: Fixed-size heap with XMALLOC override
#define WOLFSSL_NO_MALLOC
#define WOLFSSL_STATIC_MEMORY
#define WOLFSSL_STATIC_MEMORY_SIZE 32768  // 32KB

int main() {
    wolfSSL_Init();
    wolfSSL_SetAllocators(my_malloc, my_free, my_realloc);
    // Or use static memory pools:
    wolfSSL_CTX* ctx = wolfSSL_CTX_new_ex(my_static_memory);
}
```

## Common Pitfalls & Gotchas

**1. Hardware crypto context alignment.** Both libraries assume aligned buffers for hardware DMA operations. On Cortex-M4/M7, if your input buffer isn’t 32-bit aligned, the hardware crypto peripheral will silently fail or corrupt data. Always use `malloc` or aligned attribute: `__attribute__((aligned(4))) uint8_t buffer[16]`.

**2. Thread safety with hardware crypto.** Hardware crypto peripherals are often shared resources. mbedTLS’s ALT implementation doesn’t add mutexes—you must handle concurrency yourself. wolfSSL’s `WOLFSSL_CRYPT_HW_MUTEX` macro enables internal mutexes, but only if you provide `wolfSSL_MutexInit/Free/Lock/Unlock` implementations. Forgetting this on a multi-threaded RTOS will cause intermittent AES failures.

**3. Session cache size mismatch.** mbedTLS defaults to a 50-session cache (`MBEDTLS_SSL_CACHE_DEFAULT_TIMEOUT`). On a device with 32KB RAM, 50 sessions at ~1KB each will exhaust memory. Set `MBEDTLS_SSL_CACHE_DEFAULT_MAX_ENTRIES` to 5 or use `mbedtls_ssl_cache_set_max_entries()`. wolfSSL’s session cache is smaller by default (10 entries), but its `wolfSSL_CTX_set_session_cache_mode` with `SSL_SESS_CACHE_NO_INTERNAL` disables it entirely—useful for one-shot IoT connections.

## Try It Yourself

1. **Profile memory usage.** Build mbedTLS with `MBEDTLS_MEMORY_DEBUG` and wolfSSL with `WOLFSSL_DEBUG_MEMORY`. Connect to a TLS 1.2 server and log peak heap usage. Compare the two stacks on your target MCU.

2. **Implement a hardware RNG hook.** Write a `mbedtls_hardware_poll()` that reads from your MCU’s TRNG peripheral. Test with `mbedtls_entropy_self_test()`. Then do the same for wolfSSL using `wc_RNG_GenerateBlock` with a custom callback.

3. **Measure TLS handshake time.** Use `MBEDTLS_TIMING_C` in mbedTLS or `wolfSSL_GetTime()` in wolfSSL to measure handshake duration with software vs. hardware crypto. On a Cortex-M4 at 200MHz, you should see AES-GCM handshakes drop from ~2 seconds to ~200ms.

## Next Up

Tomorrow: **TLS 1.3 Handshake on a Microcontroller: Constraints & Optimizations** — we’ll dissect the 1-RTT handshake, pre-shared key (PSK) resumption, and how to fit ECDHE key exchange into 16KB of RAM without breaking a sweat.
