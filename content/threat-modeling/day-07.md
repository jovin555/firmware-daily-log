---
title: "Day 07: OWASP Embedded/IoT Top 10: Overview & Mapping to Firmware"
date: 2026-07-07
tags: ["til", "threat-modeling", "owasp", "top10"]
---

## What I Explored Today

Today I mapped the OWASP Embedded/IoT Top 10 (2020) against real firmware attack surfaces. While the web-focused OWASP Top 10 is well-known, the embedded variant targets the unique constraints of MCU-based systems: limited flash, no MMU, bare-metal or RTOS environments, and physical attacker access. I walked through each category, identified where it manifests in firmware code, and noted which mitigations actually fit within a 256 KB flash budget.

## The Core Concept

The OWASP Embedded/IoT Top 10 exists because embedded systems violate nearly every assumption web security makes. There’s no OS to isolate processes, no filesystem permissions, no user context. An attacker with a JTAG probe or UART access is effectively root. The list prioritizes threats that are either unique to embedded (e.g., insecure OTA updates, physical interfaces) or amplified by resource constraints (e.g., lack of crypto agility, no secure boot).

The key insight: **every item on this list maps to a firmware binary**. You can’t patch a cloud API after deployment if the firmware has hardcoded credentials and no OTA mechanism. You can’t rotate a key if it’s compiled into `.rodata` as a plaintext string. The mapping forces you to treat the firmware image itself as an attack surface — not just the network services it exposes.

## Key Commands / Configuration / Code

### 1. Firmware Binary Analysis for Top 10 Indicators

Use `binwalk` and `strings` to find hardcoded credentials (I2), insecure storage (I8), and lack of crypto agility (I6):

```bash
# Extract filesystem and scan for plaintext secrets
binwalk -Me firmware.bin
strings firmware.bin | grep -iE '(password|secret|key|token|psk)' | sort -u

# Check for known vulnerable library versions (I9: Use of Insecure Components)
strings firmware.bin | grep -i 'openssl\|mbedtls\|lwip' | sort -u
```

### 2. Secure Boot Chain Verification (I10: Lack of Secure Update Mechanism)

On a real STM32H7 with TF-A and MCUboot, verify the image signature before boot:

```c
// MCUboot image header validation (simplified)
struct image_header {
    uint32_t magic;         // Must be IMAGE_MAGIC
    uint32_t image_size;    // Total image size
    uint32_t flags;         // Encryption/authentication flags
    uint8_t  sha256[32];    // Hash of image payload
    uint8_t  signature[64]; // ECDSA P-256 signature
};

int verify_firmware(const struct image_header *hdr) {
    // 1. Check magic to prevent random flash being booted
    if (hdr->magic != IMAGE_MAGIC) return -1;

    // 2. Verify hash before signature (cheap fail-fast)
    uint8_t computed_hash[32];
    mbedtls_sha256(hdr + 1, hdr->image_size, computed_hash, 0);
    if (memcmp(computed_hash, hdr->sha256, 32) != 0) return -2;

    // 3. Verify ECDSA signature (expensive, only if hash matches)
    mbedtls_ecdsa_context ctx;
    mbedtls_ecdsa_init(&ctx);
    mbedtls_ecp_group_load(&ctx.grp, MBEDTLS_ECP_DP_SECP256R1);
    // Load public key from OTP fuses, NOT from flash
    mbedtls_ecp_point_read_binary(&ctx.grp, &ctx.Q, otp_pubkey, 64);

    int ret = mbedtls_ecdsa_read_signature(&ctx, hdr->sha256, 32,
                                           hdr->signature, 64);
    mbedtls_ecdsa_free(&ctx);
    return (ret == 0) ? 0 : -3;
}
```

### 3. Network Service Hardening (I1: Insecure Network Services)

Disable unnecessary services and enforce TLS 1.3 with certificate pinning:

```c
// lwIP configuration to minimize attack surface
// lwipopts.h
#define LWIP_TCP               1       // Only if needed
#define LWIP_UDP               0       // Disable UDP entirely
#define LWIP_DNS               0       // No DNS if IPs are static
#define LWIP_SNMP              0       // SNMP is a common RCE vector
#define LWIP_HTTPD             0       // No built-in HTTP server

// MQTT client with certificate pinning (not just CA verification)
static const uint8_t server_pubkey_der[] = {
    // DER-encoded ECDSA P-256 public key of your MQTT broker
    0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2A, 0x86, ...
};

int mqtt_connect_secure(mqtt_client_t *client) {
    mbedtls_ssl_config conf;
    mbedtls_ssl_config_defaults(&conf, MBEDTLS_SSL_IS_CLIENT,
                                MBEDTLS_SSL_TRANSPORT_STREAM,
                                MBEDTLS_SSL_PRESET_DEFAULT);

    // Pin the server's public key, not just the CA
    mbedtls_ssl_conf_own_cert(&conf, &clicert, &pkey);
    mbedtls_ssl_conf_authmode(&conf, MBEDTLS_SSL_VERIFY_REQUIRED);

    // Custom verification callback that checks pinned key
    mbedtls_ssl_conf_verify(&conf, verify_pinned_key, NULL);
    return mbedtls_ssl_handshake(&client->ssl);
}
```

## Common Pitfalls & Gotchas

1. **Assuming flash is read-protected**: Many engineers rely on STM32 RDP (Readout Protection) Level 1 as a security boundary. Level 1 is trivially bypassed with voltage glitching or decapping. Treat all flash contents as public once the device is in an attacker’s hands. Never store secrets that must remain confidential after physical compromise.

2. **Using the same key for signing and encryption**: The OWASP list warns about insecure OTA (I10) and lack of crypto agility (I6). A common mistake is using a single RSA key for both signing firmware images and encrypting the update channel. If the encryption is broken, the signing key is also compromised. Always use separate key pairs for authentication and confidentiality.

3. **Ignoring the bootloader as an attack surface**: The bootloader is the most privileged code on the device. If it doesn’t validate the application image’s signature (I10), an attacker can flash arbitrary code via SWD or USB DFU. Even if the application has perfect network security, the bootloader is the root of trust. Verify it first.

## Try It Yourself

1. **Audit a firmware binary for I2 (Insecure Default Credentials)**: Download any open-source IoT firmware (e.g., ESP32-based). Run `strings` and `binwalk` to find hardcoded Wi-Fi credentials, API tokens, or MQTT passwords. Document how many secrets you found and whether they are in plaintext.

2. **Implement a secure boot chain on a dev board**: Using an STM32 Nucleo or Raspberry Pi Pico, set up MCUboot with ECDSA P-256 signing. Write a Python script that signs a firmware update and verify the bootloader rejects an unsigned image. Measure the boot time impact.

3. **Map your own project to the OWASP Embedded Top 10**: Take a firmware project you’ve worked on. For each of the 10 categories, write a one-sentence assessment of whether your code is vulnerable. Pay special attention to I1 (Network Services), I6 (Lack of Crypto Agility), and I10 (Secure Updates). Share the results with your team.

## Next Up

Tomorrow we dive into **Insecure Network Services (I1)** and **Weak Default Credentials (I2)** — the two most exploited entry points in IoT botnets. We’ll analyze real Mirai-style attack vectors, show how to disable unnecessary services in FreeRTOS+lwIP, and implement a credential rotation mechanism that survives OTA updates.
