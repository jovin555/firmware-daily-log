---
title: "Day 02: STRIDE Methodology: Spoofing, Tampering, Repudiation & More"
date: 2026-07-02
tags: ["til", "threat-modeling", "stride"]
---

## What I Explored Today

Today I dug into the STRIDE threat classification framework, originally developed at Microsoft, which gives us a structured way to enumerate threats against an embedded system. Instead of brainstorming random "what ifs," STRIDE forces us to consider six specific threat categories: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege. I applied it to a real CAN bus telematics gateway firmware project and found gaps I'd missed in three previous design reviews.

## The Core Concept

STRIDE exists because unstructured threat brainstorming is unreliable. Engineers naturally focus on the threats they've seen before (buffer overflows, authentication bypasses) and miss entire categories. STRIDE is a mnemonic and a checklist — you walk through each letter and ask: *"How could an attacker do this to my system?"*

The key insight: STRIDE is **per-element**, not per-system. You apply it to every trust boundary you've drawn in your data flow diagram. A USB port, a UART debug header, a cloud API endpoint — each gets its own STRIDE analysis. This prevents you from saying "the system is secure" when you've only analyzed the network interface.

For embedded systems, the categories map directly to hardware realities:

- **Spoofing** – Can an attacker impersonate a legitimate ECU on the CAN bus? (Yes, if there's no message authentication.)
- **Tampering** – Can they modify firmware in flash via a JTAG port left enabled in production?
- **Repudiation** – Can a sensor node deny having sent a critical alert because there's no signed audit log?
- **Information Disclosure** – Does the debug UART on the production board still spit out memory addresses?
- **Denial of Service** – Can a single malformed MQTT packet crash the TCP/IP stack on your RTOS?
- **Elevation of Privilege** – Can an unauthenticated user on the web interface escalate to root via a command injection in the firmware update endpoint?

The "why" is simple: STRIDE makes threat modeling systematic. You stop guessing and start auditing.

## Key Commands / Configuration / Code

Here's a practical STRIDE worksheet template I use for embedded firmware review. Save this as `stride_review.yaml` and fill it per trust boundary:

```yaml
# stride_review.yaml — per trust boundary analysis
trust_boundary: "CAN bus interface (ISO 11898)"
element: "CAN message reception ISR"

threats:
  spoofing:
    - threat: "Attacker injects forged CAN frames with valid IDs"
    - mitigation: "CAN-FD with authentication (SecOC / AUTOSAR)"
    - status: "not_implemented"
  tampering:
    - threat: "Attacker modifies DLC field to cause buffer overflow in ISR"
    - mitigation: "Validate DLC against expected length before memcpy"
    - status: "implemented"
  repudiation:
    - threat: "ECU denies sending a diagnostic request"
    - mitigation: "Log all CAN TX frames with monotonic counter + CRC"
    - status: "partial — counter implemented, CRC missing"
  information_disclosure:
    - threat: "Unencrypted diagnostic responses leak firmware version"
    - mitigation: "Encrypt diagnostic session (ISO 15765-2 with TLS)"
    - status: "not_implemented"
  denial_of_service:
    - threat: "Flood CAN bus with high-priority frames, starving lower IDs"
    - mitigation: "Rate limiting per CAN ID in hardware filter"
    - status: "implemented"
  elevation_of_privilege:
    - threat: "Attacker uses diagnostic session to flash unsigned firmware"
    - mitigation: "Require signed firmware image + secure boot"
    - status: "implemented"
```

For a quick CLI audit of your firmware's exposed interfaces, use `objdump` to find all string references to debug ports:

```bash
# Find all UART/SPI/I2C debug strings in the firmware binary
arm-none-eabi-objdump -s -j .rodata firmware.elf | grep -iE '(uart|serial|debug|printf|log)' | head -20
# Output example:
# 08001234 55415254 5f444542 55475f53 5452494e  "UART_DEBUG_STRIN"
# 08001244 4700       ...                        "G."
```

Then cross-reference those addresses with the linker map to see if they're accessible from production code paths.

## Common Pitfalls & Gotchas

1. **Applying STRIDE to the whole system, not per trust boundary.** I've seen teams say "we have TLS, so Spoofing is handled." But TLS protects the network pipe, not the local JTAG port or the SD card slot. Each trust boundary gets its own STRIDE pass. Miss one, and you've got a blind spot.

2. **Confusing Tampering with Spoofing.** Tampering is about modifying *existing* data (e.g., corrupting a firmware image in flash). Spoofing is about *pretending to be* something else (e.g., sending a fake CAN message). They require different mitigations — authentication for spoofing, integrity checks (HMAC, CRC) for tampering. Mixing them up leads to wrong countermeasures.

3. **Ignoring Repudiation in embedded systems.** Most embedded firmware has zero audit logging. If a sensor sends a false alarm, you can't prove it didn't. For safety-critical systems (ISO 26262 ASIL-D), repudiation is a showstopper. Add a monotonic counter and signed log entries early — retrofitting them is a nightmare.

## Try It Yourself

1. **Map your current project's trust boundaries.** List every interface (UART, SPI, I2C, CAN, Ethernet, USB, JTAG, SD card). For each, write down one STRIDE threat you haven't considered before. I bet you'll find at least one "Information Disclosure" from a debug port left enabled.

2. **Audit your firmware's debug strings.** Run the `objdump` command above on your latest build. Count how many `printf`/`debug` strings exist. Then check if those functions are compiled out in the release build (`#ifdef DEBUG`). If they're not, you have an Information Disclosure threat.

3. **Write a STRIDE worksheet for your CAN bus interface.** Use the YAML template above. Be honest about the "status" field — mark what's actually implemented, not what's planned. Share it with a colleague and ask them to find a threat you missed.

## Next Up

Tomorrow: **Data Flow Diagrams for Embedded Systems Threat Models** — how to draw trust boundaries around MCU peripherals, RTOS tasks, and hardware accelerators, and why a bad DFD guarantees a bad threat model.
