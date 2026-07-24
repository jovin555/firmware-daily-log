---
title: "Day 24: Full Review & Project: Threat Model for a Connected Door Lock"
date: 2026-07-24
tags: ["til", "threat-modeling", "review", "project"]
---

## What I Explored Today

Today I completed a full threat model for a real embedded product: a Wi-Fi connected door lock with a mobile app, cloud backend, and physical keypad. This isn't a theoretical exercise — I walked through the entire STRIDE process, enumerated attack surfaces, and documented mitigations for a system that could be deployed in a smart home. The goal was to synthesize everything from the past 23 days into a single, coherent security analysis that an engineering team could actually use during a design review.

## The Core Concept

A connected door lock is a high-value target because it bridges the physical and digital worlds. Compromise the lock, and an attacker gains physical access. The threat model must account for three distinct trust boundaries: the lock hardware (constrained MCU, BLE/Wi-Fi radio, motor driver), the mobile app (user's phone, potentially jailbroken), and the cloud backend (API, database, push notifications). The "why" behind this exercise is that a single vulnerability — like a replayable unlock command or a hardcoded credential — can invalidate every other security control. Threat modeling forces you to ask: "If this component is fully compromised, what else breaks?" For a door lock, the answer is often "everything."

## Key Commands / Configuration / Code

I started by documenting the data flow diagram (DFD) as a Mermaid diagram, then enumerated threats using STRIDE. Below is the DFD and a snippet of the threat list I generated.

### Data Flow Diagram (Mermaid)
```mermaid
graph TD
    subgraph User
        A[Mobile App]
        B[Physical Keypad]
    end
    subgraph Lock Hardware
        C[MCU (ESP32)]
        D[BLE Radio]
        E[Wi-Fi Radio]
        F[Motor Driver]
        G[Flash Storage]
    end
    subgraph Cloud
        H[API Gateway]
        I[Database]
        J[Push Notification Service]
    end
    A -->|BLE/Wi-Fi| D
    B -->|I2C| C
    D --> C
    E -->|TLS 1.3| H
    H --> I
    H --> J
    C --> F
    C --> G
```

### Threat Enumeration (STRIDE per Element)
I used a simple Python script to generate a structured threat list from the DFD. Here's the output for the MCU:

```python
# threat_model_generator.py
# Generates STRIDE threats for each DFD element
threats = {
    "MCU (ESP32)": {
        "Spoofing": "Attacker clones lock's BLE MAC address to impersonate lock",
        "Tampering": "Attacker modifies firmware via UART or JTAG if exposed",
        "Repudiation": "No audit log on MCU; cannot prove who sent unlock command",
        "Information Disclosure": "Flash dump reveals Wi-Fi credentials or encryption keys",
        "Denial of Service": "Flood BLE connection requests to drain battery or hang stack",
        "Elevation of Privilege": "Buffer overflow in BLE command parser yields code execution"
    },
    "Cloud API Gateway": {
        "Spoofing": "Attacker forges JWT token with weak secret",
        "Tampering": "Man-in-the-middle on TLS downgrade to HTTP",
        "Repudiation": "No request signing; API logs can be altered",
        "Information Disclosure": "Verbose error messages leak stack traces or DB schema",
        "Denial of Service": "Unthrottled unlock endpoint allows brute force",
        "Elevation of Privilege": "IDOR in lock ID parameter allows unlocking other users' locks"
    }
}

for element, striden in threats.items():
    print(f"\n=== {element} ===")
    for s, desc in striden.items():
        print(f"  {s}: {desc}")
```

### Mitigation Configuration (ESP32 IDF)
For the lock firmware, I configured secure boot and flash encryption:

```c
// sdkconfig fragment for ESP32 secure boot v2
CONFIG_SECURE_BOOT_V2_ENABLED=y
CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES=y
CONFIG_SECURE_FLASH_ENC_ENABLED=y
CONFIG_SECURE_FLASH_ENCRYPTION_MODE_DEVELOPMENT=n  // production only
CONFIG_SECURE_BOOT_VERIFICATION_ALGORITHM_ECDSA_V2
```

## Common Pitfalls & Gotchas

1. **Assuming BLE is secure by default.** Many engineers think BLE pairing handles authentication. In practice, "Just Works" pairing is vulnerable to MITM. For a door lock, always use BLE Secure Connections with numeric comparison or passkey entry. I've seen production locks ship with `IO_CAPABILITY_NO_INPUT_NO_OUTPUT`, which disables MITM protection.

2. **Hardcoding cloud credentials in flash.** Even with flash encryption, the key must be provisioned at manufacturing. If you use the same key for all devices, a single dump breaks the fleet. Use per-device unique keys stored in eFuse or a secure element (e.g., ATECC608A). The ESP32's flash encryption key is stored in eFuse, but the application key must still be derived per device.

3. **Ignoring physical tampering.** A door lock is physically accessible. Attackers can probe UART pins, desolder flash, or inject glitches on the power rail. Your threat model must include physical attacks: disable JTAG, remove test points in production, and use tamper-detection circuits that wipe keys on enclosure opening.

## Try It Yourself

1. **Extend the threat model** to include the mobile app's local storage. What happens if an attacker has root access on the phone? List three threats using STRIDE for the app's keychain/keystore.

2. **Write a mitigation** for the "IDOR in lock ID parameter" threat from the API Gateway. Implement a check in pseudocode that ensures the authenticated user owns the lock before processing an unlock command.

3. **Simulate a replay attack** on the BLE channel. Using a BLE sniffer (e.g., nRF Sniffer + Wireshark), capture an unlock command from a test lock. Try to replay it using `gatttool` or `bluetoothctl`. Document whether the lock accepts it — if it does, you've found a vulnerability.

## Next Up

Tomorrow is the final day of this series: a full review of all 24 days, a consolidated checklist you can print and pin on your wall, and a look at how to integrate threat modeling into your CI/CD pipeline. We'll also cover the top three mistakes I see in embedded security reviews and how to avoid them.

---
