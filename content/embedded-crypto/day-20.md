---
title: "Day 20: Certificate Chains & X.509 for Device Identity"
date: 2026-07-20
tags: ["til", "embedded-crypto", "x509", "pki"]
---

## What I Explored Today

Today I dug into how X.509 certificate chains actually work in embedded device identity — not just the theory of PKI hierarchies, but the gritty details of chain validation, trust anchor storage, and the specific ASN.1 fields that matter when your device has only 64KB of flash. I built a minimal chain validator for an ARM Cortex-M target and discovered why most embedded TLS stacks silently skip path length constraints unless you explicitly check them.

## The Core Concept

A certificate chain is a sequence of X.509 certificates where each certificate (except the root) is signed by the next one in the chain. The root is self-signed — it's the trust anchor. For embedded devices, the chain typically looks like:

```
Root CA (self-signed, pre-loaded in firmware)
  └── Intermediate CA (signed by Root)
       └── Device Certificate (signed by Intermediate)
```

The *why* is critical: you never want the root CA's private key on the device. If an attacker dumps flash, they get the device cert and intermediate, but not the root key. The root key stays in an HSM at the factory. This means your device must store the *entire chain* (except root) and validate it against a root certificate that's burned into read-only storage.

On constrained devices, the validation logic must check:
- **Signature validity** at each link (ECDSA or RSA verify)
- **Validity period** (notBefore/notAfter) for each cert
- **Key usage** extensions (digitalSignature for device certs)
- **Path length constraints** (often forgotten — see pitfalls)
- **Subject/Issuer name matching** (exact byte comparison, not string comparison)

The chain terminates when the issuer of the current certificate matches the subject of the next, and the next is self-signed (or we've reached a configured trust anchor).

## Key Commands / Configuration / Code

### 1. Inspecting a certificate chain with OpenSSL

```bash
# Download a real device certificate chain (example: AWS IoT)
openssl s_client -connect a3xyz12345.iot.us-east-1.amazonaws.com:8883 \
  -showcerts </dev/null 2>/dev/null | openssl crl2pkcs7 -nocrl | \
  openssl pkcs7 -print_certs -text -noout

# Extract each certificate to separate files
openssl s_client -connect example.com:443 -showcerts </dev/null 2>/dev/null | \
  awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > chain.pem

# Split chain into individual PEMs (CSplit approach)
csplit -f cert- chain.pem '/-----BEGIN CERTIFICATE-----/' '{*}'
```

### 2. Minimal chain validation in C (for embedded targets)

```c
#include <mbedtls/x509_crt.h>
#include <mbedtls/error.h>

// Trust anchor stored in read-only flash (pre-flashed at manufacturing)
static const unsigned char root_ca_der[] = { /* DER bytes */ };
static const size_t root_ca_len = sizeof(root_ca_der);

// Chain: device cert + intermediate(s), concatenated DER
int validate_device_chain(const unsigned char *chain_der, size_t chain_len) {
    mbedtls_x509_crt chain;
    mbedtls_x509_crt root;
    uint32_t flags;
    int ret;

    mbedtls_x509_crt_init(&chain);
    mbedtls_x509_crt_init(&root);

    // Parse the root trust anchor
    ret = mbedtls_x509_crt_parse_der(&root, root_ca_der, root_ca_len);
    if (ret != 0) return -1;

    // Parse the device chain (multiple certs in one buffer)
    ret = mbedtls_x509_crt_parse_der(&chain, chain_der, chain_len);
    if (ret != 0) {
        mbedtls_x509_crt_free(&chain);
        mbedtls_x509_crt_free(&root);
        return -2;
    }

    // Verify chain against root with default profile
    ret = mbedtls_x509_crt_verify(&chain, &root, NULL, NULL, &flags,
                                  NULL, NULL);
    if (ret != 0) {
        // flags contains detailed failure reasons
        char buf[256];
        mbedtls_x509_crt_verify_info(buf, sizeof(buf), "  ! ", flags);
        printf("Chain validation failed:\n%s\n", buf);
    }

    mbedtls_x509_crt_free(&chain);
    mbedtls_x509_crt_free(&root);
    return ret;
}
```

### 3. Generating a device certificate with proper constraints

```bash
# Create device key and CSR with key usage for TLS client auth
openssl ecparam -genkey -name prime256v1 -out device.key
openssl req -new -key device.key -out device.csr \
  -subj "/CN=device-001.acme.com" \
  -addext "keyUsage=digitalSignature" \
  -addext "extendedKeyUsage=clientAuth" \
  -addext "subjectAltName=DNS:device-001.acme.com"

# Sign with intermediate CA, setting path length constraint
openssl x509 -req -in device.csr -CA intermediate.pem -CAkey intermediate.key \
  -CAcreateserial -out device.pem -days 3650 -sha256 \
  -extfile <(echo "basicConstraints=CA:FALSE\npathlen:0")
```

## Common Pitfalls & Gotchas

### 1. Path length constraints are silently ignored by many embedded stacks
The `pathLenConstraint` in the Basic Constraints extension limits how many intermediate CAs can follow. If your intermediate CA has `pathLenConstraint=0`, it cannot sign another intermediate. Many embedded TLS stacks (including older mbedTLS versions) skip this check entirely. Always verify with `mbedtls_x509_crt_verify_with_profile` using a profile that enforces `MBEDTLS_X509_BADCERT_BAD_KEY_USAGE` and `MBEDTLS_X509_BADCERT_BAD_MD`.

### 2. Name comparison is byte-by-byte, not string comparison
X.509 Distinguished Names (DNs) are ASN.1 SEQUENCEs of Relative Distinguished Names (RDNs). Two DNs that look identical as strings may differ in encoding (e.g., PrintableString vs UTF8String). Always use the library's comparison function (`mbedtls_x509_dn_gets` for display, but the internal comparison is raw DER). I've seen devices accept a certificate where the issuer DN had a trailing space in one field — the library rejected it because the DER bytes differed.

### 3. Certificate revocation is almost never checked in embedded systems
CRLs (Certificate Revocation Lists) are large and rarely downloaded on constrained devices. OCSP (Online Certificate Status Protocol) requires network access and a real-time clock. Most embedded systems simply rely on short-lived certificates (e.g., 30-90 days) and a secure renewal mechanism. If you must support revocation, consider using a bloom filter or a compact CRL format (e.g., the one proposed in RFC 8608 for constrained environments).

## Try It Yourself

1. **Build a chain validator for your dev board**: Using mbedTLS or WolfSSL, write a function that takes a DER-encoded certificate chain and a trust anchor, then validates it. Print the reason for failure if validation fails. Test with a chain where the intermediate has expired.

2. **Inspect a real IoT device certificate**: Connect to a public IoT endpoint (e.g., `a3xyz.iot.region.amazonaws.com:8883`) and capture the certificate chain. Parse each certificate with `openssl x509 -text -noout` and identify the Basic Constraints, Key Usage, and Subject/Issuer fields. Verify the chain manually.

3. **Generate a chain with an invalid path length**: Create a root CA, an intermediate CA with `pathLenConstraint=0`, and then try to sign a second intermediate with that first intermediate. Attempt to validate the resulting chain. Observe how your embedded library handles it (or doesn't).

## Next Up

Tomorrow: **PSA Crypto API: Vendor-Neutral Crypto Abstraction** — we'll explore how Arm's Platform Security Architecture defines a standard API for cryptographic operations that works across STM32, NXP, and Silicon Labs MCUs, and how to write portable crypto code that doesn't lock you into a single vendor's HAL.
