---
title: "Day 01: Why Firmware Needs Threat Modeling: Attackers vs Bugs"
date: 2026-07-01
tags: ["til", "threat-modeling", "threat-modeling"]
---

## What I Explored Today

I dove into why traditional bug-hunting falls short for firmware security. Most embedded engineers treat security like a QA problem: find the buffer overflow, patch it, move on. But firmware lives in a fundamentally different threat landscape. Today I explored how threat modeling shifts the mindset from "what can break" to "who wants to break it and how." The key insight: attackers don't care about your coding style—they care about your trust boundaries, your hardware-software interfaces, and the assumptions baked into your boot chain.

## The Core Concept

Here's the uncomfortable truth: **a bug is an accident; an attack is a plan.** When you fix a buffer overflow in a UART handler, you're fixing a mistake. But when an attacker exploits that overflow to inject a shellcode payload that re-flashes the bootloader, they're executing a strategy. Threat modeling is the discipline of thinking like that attacker *before* they show up.

In firmware, the stakes are higher than in web apps. Your code runs on bare metal or under a thin RTOS. There's no ASLR on an ARM Cortex-M0. No stack canary unless you explicitly add one. No memory protection unit (MPU) unless you configured it. And once the attacker has physical access—JTAG, UART, SPI flash probing—your software defenses crumble unless you've modeled those attack paths.

The core difference between bugs and threats:

- **Bugs** are implementation flaws: null pointer dereference, integer overflow, race condition.
- **Threats** are adversarial capabilities: "Can the attacker read the firmware image off the SPI flash?" "Can they downgrade the bootloader to a vulnerable version?" "Can they trigger a fault injection glitch to skip authentication?"

Threat modeling forces you to enumerate *assets* (cryptographic keys, firmware integrity, device identity), *attackers* (remote script kiddie, physical attacker with a logic analyzer, supply chain actor), and *trust boundaries* (where data crosses from untrusted to trusted zones). Only then do you prioritize which bugs actually matter.

## Key Commands / Configuration / Code

Let's make this concrete with a real-world example: a firmware update mechanism. Here's a naive implementation that has a bug, but the *threat* is far worse.

```c
// naive_firmware_update.c — DO NOT USE IN PRODUCTION
#include <string.h>
#include <stdint.h>

#define FLASH_BASE 0x08000000
#define MAX_IMAGE_SIZE 0x40000  // 256KB

// Vulnerability: no signature check, no version check, no rollback protection
int apply_firmware_update(uint8_t *data, uint32_t len) {
    // Bug 1: integer overflow if len > MAX_IMAGE_SIZE + something
    if (len > MAX_IMAGE_SIZE) {
        return -1;  // but what if len == 0? or len == 0xFFFFFFFF?
    }
    
    // Bug 2: no validation that data pointer is valid
    // Threat: attacker sends a crafted packet that overwrites bootloader region
    memcpy((void*)FLASH_BASE, data, len);  // writes to flash directly!
    
    // Bug 3: no integrity check before jumping to new code
    void (*reset)(void) = (void (*)(void))FLASH_BASE;
    reset();  // jumps to whatever we just wrote
    return 0;
}
```

Now, let's threat-model this:

1. **Asset**: Firmware integrity, device identity, cryptographic keys stored in flash.
2. **Attacker**: Remote attacker who can send malformed update packets; physical attacker with UART access.
3. **Trust boundary**: The update packet arrives over an untrusted network channel. The flash write happens in a privileged mode.

The threat model reveals we need:
- Authenticated encryption (not just CRC)
- Rollback protection (version counter in OTP)
- Write protection on bootloader region (RDP or MPU)

Here's a threat-model-aware refactor:

```c
// threat_modeled_update.c — still simplified, but better
#include "crypto.h"   // hypothetical hardware crypto engine
#include "flash_map.h" // defines protected regions

int apply_secure_firmware_update(uint8_t *packet, uint32_t pkt_len) {
    // Step 1: Validate packet structure before any flash write
    if (pkt_len < sizeof(firmware_header_t)) return -1;
    
    firmware_header_t *hdr = (firmware_header_t*)packet;
    
    // Step 2: Verify signature using hardware crypto (resists timing attacks)
    if (!hmac_verify(packet, pkt_len - HMAC_SIZE, 
                     packet + pkt_len - HMAC_SIZE, HMAC_SIZE)) {
        return -1;  // Threat: unauthorized firmware rejected
    }
    
    // Step 3: Check version against monotonic counter in OTP
    if (hdr->version <= read_otp_version_counter()) {
        return -1;  // Threat: rollback attack prevented
    }
    
    // Step 4: Write to staging area, not bootloader region
    // (flash_map ensures we can't overwrite protected sectors)
    if (flash_write_staging(hdr->payload, hdr->payload_len) != 0) {
        return -1;
    }
    
    // Step 5: Atomic swap only after verification
    return swap_staging_to_active();
}
```

## Common Pitfalls & Gotchas

1. **Assuming "no network" means "no threat"**  
   I've seen teams skip threat modeling because "the device is air-gapped." Then an attacker plugs into the debug UART, dumps the firmware, finds hardcoded credentials, and uses them to compromise the backend server. Physical access is a valid attack vector; model it.

2. **Treating threat modeling as a one-time paperwork exercise**  
   Threat models rot faster than code. When you add a new sensor, change the boot sequence, or switch from bare-metal to FreeRTOS, your attack surface changes. I've learned to keep the threat model as a living document in the repo, updated with each major feature.

3. **Forgetting the supply chain**  
   The most common firmware threat I've seen? A developer clones a third-party library with a known vulnerability (e.g., a vulnerable CRC implementation used for integrity checks). Threat modeling must include *where your code comes from*, not just what it does.

## Try It Yourself

1. **Draw a data flow diagram for your current project**  
   Grab a whiteboard or draw.io. Map every input (UART, I2C, SPI, radio, network), every storage location (flash, EEPROM, RAM), and every trust boundary. Label each arrow with "trusted" or "untrusted." You'll be surprised how many untrusted inputs you've been treating as trusted.

2. **Identify one asset and one attack path**  
   Pick a cryptographic key or firmware update mechanism in your system. Write down: "If I were an attacker with physical access, how would I extract this key?" Then write down: "If I were a remote attacker, how would I bypass the update check?" Don't code yet—just think.

3. **Review your boot sequence for rollback vulnerabilities**  
   Check if your bootloader checks a version counter before jumping to the application. If it doesn't, an attacker can flash an old, vulnerable firmware version and exploit known bugs. Add a monotonic counter check—even a simple one in OTP memory.

## Next Up

Tomorrow, we'll apply the **STRIDE methodology** to firmware: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege. We'll walk through each category with concrete embedded examples—from spoofing sensor data over I2C to elevation of privilege via unchecked interrupt handlers.
