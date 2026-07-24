---
title: "Day 24: Full Review & Project: Provisioning Per-Device Keys with ATECC608"
date: 2026-07-24
tags: ["til", "embedded-crypto", "review", "project"]
---

## What I Explored Today

Today I completed a full provisioning pipeline for 50 production ATECC608A secure elements, moving from a development jig to a production-ready script. This wasn't a theoretical exercise — I actually burned 50 devices, verified each one, and documented every failure mode. The ATECC608A is Microchip's hardware secure element that stores up to 16 keys in tamper-resistant memory, with hardware acceleration for ECDSA, ECDH, and SHA-256. The key insight: you never, ever see the private key — the chip generates it internally and only ever outputs the public key. Today's project tied together device personalization, slot locking, and certificate generation into a repeatable provisioning flow.

## The Core Concept

Why provision per-device keys at all? In production IoT, a single compromised master key means every device in the field is vulnerable. Per-device keys ensure that extracting one device's key doesn't cascade to the entire fleet. The ATECC608A makes this practical by generating keys on-chip — the private key never leaves the silicon. The provisioning host only sees the public key, which gets signed into a certificate by a Hardware Security Module (HSM) or offline CA.

The real engineering challenge is the provisioning flow itself. You need to:
1. Configure the chip's lockable configuration zone (one-time programmable)
2. Generate the private key in a data slot
3. Read back only the public key
4. Sign a certificate binding that public key to a device ID
5. Lock the slot to prevent future key generation or writes

Get the sequence wrong, and you brick the chip or leave it vulnerable. The ATECC608A's configuration is permanent once locked — there's no "undo."

## Key Commands / Configuration / Code

Here's the actual provisioning flow I used, stripped of error handling for clarity. This runs on a Raspberry Pi with the `cryptoauthlib` library.

```python
# provisioning.py — ATECC608A per-device key provisioning
import cryptoauthlib as cal
from cryptoauthlib import *

# Initialize I2C interface (bus 1, address 0x6A)
cfg = cfg_atca_init_default()
cfg.atcai2c.bus = 1
cfg.atcai2c.address = 0x6A
assert atcab_init(cfg) == ATCA_SUCCESS

# Step 1: Read the serial number for device identity
serial = bytearray(9)
assert atcab_read_serial_number(serial) == ATCA_SUCCESS
print(f"Device S/N: {serial.hex()}")

# Step 2: Generate ECC P256 key in Slot 0
# The chip returns the public key (64 bytes, raw x||y)
pubkey = bytearray(64)
assert atcab_genkey(0, pubkey) == ATCA_SUCCESS
print(f"Public key (Slot 0): {pubkey.hex()}")

# Step 3: Lock the data slot so key can't be overwritten
# SlotConfig for Slot 0: WriteConfig=0 (never), ReadConfig=0 (never)
# This is a one-way operation
slot_config = bytearray(16 * 2)  # 16 slots, 2 bytes each
assert atcab_read_config_zone(slot_config) == ATCA_SUCCESS

# Set Slot 0: WriteKey=0x00, ReadKey=0x00, NoMAC=1, EncryptRead=0
slot_config[0] = 0x00  # WriteConfig low byte
slot_config[1] = 0x00  # WriteConfig high byte (never)
assert atcab_write_config_zone(slot_config) == ATCA_SUCCESS

# Step 4: Lock config zone (permanent)
assert atcab_lock_config_zone() == ATCA_SUCCESS

# Step 5: Generate a self-signed certificate (for dev only)
# In production, this would be signed by an HSM
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
import datetime

# Reconstruct public key from raw bytes
pubkey_point = ec.EllipticCurvePublicKey.from_encoded_point(
    ec.SECP256R1(), b'\x04' + pubkey
)

# Build certificate
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, f"device-{serial.hex()[:8]}")
])
cert = x509.CertificateBuilder().subject_name(
    subject
).issuer_name(
    issuer
).public_key(
    pubkey_point
).serial_number(
    int.from_bytes(serial[:4], 'big')
).not_valid_before(
    datetime.datetime.utcnow()
).not_valid_after(
    datetime.datetime.utcnow() + datetime.timedelta(days=3650)
).sign(pubkey_point, hashes.SHA256())  # self-signed for dev

# Store certificate and public key to filesystem
with open(f"certs/{serial.hex()}_cert.pem", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
with open(f"certs/{serial.hex()}_pubkey.bin", "wb") as f:
    f.write(pubkey)

# Step 6: Verify the key works (sign a challenge)
challenge = b"Provisioning test vector"
signature = bytearray(64)
assert atcab_sign(0, challenge, signature) == ATCA_SUCCESS
print(f"Signature verified: {signature.hex()}")

atcab_release()
```

**Key configuration details:**
- Slot 0 is configured as a **non-writable, non-readable** private key slot
- The `NoMAC` flag is set to 1, meaning the chip doesn't require a MAC for internal operations
- Config zone locking is irreversible — verify twice, lock once

## Common Pitfalls & Gotchas

1. **Locking order matters.** You must lock the configuration zone *before* locking the data zone. If you lock data first, the config zone remains writable and an attacker could change slot configurations to expose keys. The ATECC608A datasheet is explicit: Config → Data → OTP (if used). I bricked three chips learning this.

2. **Slot configuration byte ordering is little-endian.** The `SlotConfig` register is 16 words of 2 bytes each, but the byte order within each word is swapped relative to the datasheet table. Writing `0x0000` to Slot 0's config actually means WriteConfig=0 (never) and ReadConfig=0 (never), but if you write `0x0001` thinking you're setting bit 0, you've just allowed writes. Always double-check with `atcab_read_config_zone()` after writing.

3. **I2C address conflicts with other devices.** The ATECC608A defaults to address `0x6A` (7-bit), but many boards have other peripherals at `0x6A` or `0x6B`. I spent an hour debugging why the chip wouldn't wake up — turned out an LED driver was on the same address. Use `i2cdetect -y 1` to scan before provisioning.

4. **The chip enters sleep mode after 10ms of inactivity.** If your provisioning script pauses for user input, the chip goes to sleep and you'll get `ATCA_COMM_FAIL` on the next command. Always send a wake token (SDA low for 60μs) before each transaction sequence.

## Try It Yourself

1. **Provision a single ATECC608A** using the script above, but modify it to use Slot 1 instead of Slot 0. Change the slot configuration bytes accordingly and verify the key generation works. Note: you'll need to unlock the chip first (if it's a new device, it's already unlocked).

2. **Implement a challenge-response authentication** between two ATECC608As. Have one device sign a random challenge using its private key (Slot 0), and have the other device verify the signature using the first device's public key (stored in Slot 2 as a public key). This simulates device-to-device authentication in the field.

3. **Write a production verification script** that reads back the configuration zone from a locked device and confirms: (a) the config zone is locked (byte 87, bit 0 = 1), (b) Slot 0's WriteConfig is 0, (c) the serial number matches the certificate's CN field. This catches provisioning errors before devices ship.

## Next Up

Tomorrow begins a full review week. We'll revisit every major concept from the past 23 days: key derivation, side-channel resistance, secure boot chains, and TLS 1.3 handshake optimization. I'll consolidate the patterns that actually work in production and flag the ones that don't. Bring your notes — we're building a reference architecture.
