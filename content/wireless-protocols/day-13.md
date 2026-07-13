---
title: "Day 13: LoRaWAN Classes A/B/C & Adaptive Data Rate"
date: 2026-07-13
tags: ["til", "wireless-protocols", "lorawan", "adr"]
---

## What I Explored Today

Today I dug into the three device classes defined by the LoRaWAN specification (A, B, and C) and the Adaptive Data Rate (ADR) mechanism that optimizes link performance. While the classes determine when a device can receive downlink traffic, ADR dynamically adjusts spreading factor, bandwidth, and transmit power based on link quality. Understanding both is essential for designing a LoRaWAN end device that balances battery life, latency, and throughput.

## The Core Concept

LoRaWAN’s class system exists because a LoRa radio is half-duplex — it cannot transmit and listen simultaneously. The class defines the *receive window schedule*, which directly impacts power consumption and downlink latency.

**Class A** is mandatory for every LoRaWAN device. After each uplink transmission, the device opens two short receive windows (RX1 and RX2) at fixed delays. The network can send a downlink message only during these windows. This is the most power-efficient mode because the radio sleeps between transmissions. But it also means the network cannot reach the device unless it first sends an uplink — high latency for downlink.

**Class B** adds scheduled receive windows (ping slots) at periodic intervals synchronized to a beacon from the gateway. The device wakes up at these times even without an uplink. This reduces downlink latency to seconds or minutes, at the cost of periodic GPS or network time synchronization and slightly higher average current.

**Class C** keeps the receiver on nearly continuously, closing the receive window only when transmitting. This gives the lowest possible downlink latency (milliseconds) but drains the battery fastest — often unsuitable for battery-powered sensors.

**Adaptive Data Rate (ADR)** is a link optimization algorithm. The network server measures the signal-to-noise ratio (SNR) of incoming uplinks and commands the device to change its data rate (spreading factor, bandwidth, coding rate) and transmit power. The goal is to use the highest possible data rate (lowest spreading factor) while maintaining a reliable link. For mobile devices, ADR is typically disabled because link conditions change too quickly.

## Key Commands / Configuration / Code

### 1. Configuring Device Class in LoRaWAN Stack (using LMIC)

```c
// LMIC (Arduino-LMIC) class configuration
// Set device class after joining

// Class A is default — no extra configuration needed
LMIC_setDrTxpow(DR_SF7, 14);  // data rate SF7, TX power 14 dBm

// Switch to Class B (requires beacon synchronization)
LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);  // 1% clock error tolerance
LMIC_enableTracking();  // start listening for beacon
// After beacon lock, device will open ping slots

// Switch to Class C
LMIC_setRxConf(0, 0);  // disable RX1 and RX2 windows
LMIC_setRxConf(1, 0);  // (not standard — actually set continuous RX mode)
// In LMIC, Class C is enabled by:
LMIC_setLinkCheckMode(0);  // disable link check
// Then set the radio to continuous receive after TX
```

**Real-world note:** Most LoRaWAN stacks (Mbed-OS, Zephyr, STM32WL) have a dedicated function:

```c
// Zephyr RTOS example
#include <zephyr/lorawan/lorawan.h>

// Set class after join
lorawan_set_class(CLASS_A);  // or CLASS_B, CLASS_C

// For Class B, also configure ping slot periodicity
struct lorawan_ping_slot_info ping_info = {
    .periodicity = 7,  // 2^7 = 128 seconds between ping slots
};
lorawan_set_ping_slot(&ping_info);
```

### 2. ADR Configuration

ADR is controlled by the network server, but the device must signal whether it supports ADR.

```c
// In LMIC, enable ADR request in uplink
LMIC_setAdrMode(1);  // 1 = enable ADR, 0 = disable

// In Zephyr, set ADR flag per uplink
struct lorawan_uplink_config uplink_cfg = {
    .adr_enabled = true,
    .confirmed = false,
    .port = 1,
};
lorawan_send(port, data, len, &uplink_cfg);

// For mobile devices, disable ADR
uplink_cfg.adr_enabled = false;
```

The device can also request an ADR parameter update by setting the `ADRACKReq` bit in the uplink frame header. If the network doesn't respond within a few uplinks, the device should increase its spreading factor (fallback).

### 3. Manual Data Rate Override (for testing)

```c
// Force a specific data rate (bypass ADR)
// DR0 = SF12/125kHz, DR1 = SF11/125kHz, ..., DR5 = SF7/125kHz
// DR6 = SF7/250kHz, DR7 = FSK 50kbps
LMIC_setDrTxpow(DR_SF10, 14);  // SF10, 14 dBm

// In Zephyr:
lorawan_set_data_rate(DR_0);  // DR_0 through DR_5
```

## Common Pitfalls & Gotchas

1. **Class C on battery is a death sentence.** A Class C device draws ~10-15 mA continuously (receiver on). A 2000 mAh battery lasts ~150 hours — less than a week. Class A with one uplink per hour can last years. Only use Class C for mains-powered or high-capacity battery packs.

2. **ADR can destabilize a link if enabled for mobile devices.** The network server assumes link conditions are stable. If a device moves from a good to a poor coverage area, ADR may have already commanded a high data rate (SF7), causing repeated frame loss. Always disable ADR for moving sensors (trackers, livestock collars).

3. **Class B beacon lock is fragile.** The beacon requires precise timing (±1.5 ms). Temperature drift, crystal aging, or poor initial calibration can cause the device to lose sync. Many production deployments avoid Class B because of this reliability issue.

## Try It Yourself

1. **Measure current draw for each class.** Configure a LoRaWAN end device (e.g., STM32WL or RFM95 + MCU) to send one uplink per 10 minutes. Measure average current for Class A, then Class C. Calculate battery life for a 2400 mAh cell.

2. **Test ADR behavior with signal attenuation.** Place a device at close range (SF7, good SNR). Add 20 dB of attenuation (or move far away). Observe how the network server commands a lower data rate (higher SF). Then disable ADR and repeat — note the packet error rate.

3. **Implement a Class B ping slot receiver.** Using a LoRaWAN stack that supports Class B (e.g., Semtech SX1302 gateway + LR1110 device), configure the device to join and enable Class B. Send a downlink from the network server and verify it arrives during a ping slot (not after an uplink).

## Next Up

Tomorrow: **Cellular IoT: NB-IoT vs LTE-M Tradeoffs for Battery-Powered Devices** — we’ll compare power consumption profiles, coverage enhancement modes, and real-world deployment considerations for LPWAN over licensed spectrum.
