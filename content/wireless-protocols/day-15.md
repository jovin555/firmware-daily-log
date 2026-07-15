---
title: "Day 15: PSM & eDRX: Cellular Power-Saving Modes Explained"
date: 2026-07-15
tags: ["til", "wireless-protocols", "psm", "edrx"]
---

## What I Explored Today

Today I dug into the two power-saving modes that make LTE-M and NB-IoT viable for battery-operated devices: Power Saving Mode (PSM) and Extended Discontinuous Reception (eDRX). While both reduce current consumption, they operate on fundamentally different principles—PSM lets the device sleep for hours or days with no network reachability, while eDRX extends paging cycles to allow periodic but still reachable deep sleep. I tested both on a Quectel BG96 module with a Thingy:91 dev board, measuring current draw with a Nordic PPK2 and logging network registration parameters.

## The Core Concept

The problem is simple: cellular modems are power-hungry. A standard LTE modem in connected mode draws 200-500 mA, and even in idle mode with normal DRX (1.28s paging cycle), it must wake every 1.28 seconds to check for pages. For a sensor that transmits once per day, that's 67,000 unnecessary wake-ups.

PSM solves this by allowing the device to register with the network, then signal that it will enter deep sleep for a requested duration (T3412 extended TAU timer). During PSM, the modem is effectively off—no paging reception, no cell reselection. The network buffers any downlink data until the device wakes for its next Tracking Area Update (TAU). This is ideal for uplink-heavy applications like water meters or soil sensors.

eDRX takes a different approach. Instead of going completely dark, the device negotiates a longer paging cycle with the network—up to 40.96 seconds for LTE-M, and up to 2621.44 seconds (43.7 minutes!) for NB-IoT. The modem wakes only at the negotiated paging window (PTW) to check for pages, then returns to deep sleep. This preserves network reachability while dramatically reducing average current.

The key tradeoff: PSM gives lower power consumption but zero reachability during sleep. eDRX gives tunable reachability at the cost of higher average current. Many designs use both: eDRX for periodic check-ins, then PSM for extended sleep between transmissions.

## Key Commands / Configuration / Code

Here's the actual AT command sequence to configure PSM and eDRX on a u-blox SARA-R5 or Quectel BG96. These are 3GPP-specified commands, so they work across most LTE-M/NB-IoT modules.

```bash
# Step 1: Check current network registration and capabilities
AT+CGREG?          # Check GPRS registration status
AT+CPSI?           # Get cell info (band, RSRP, RSRQ)

# Step 2: Configure PSM parameters
# Requested TAU timer (T3412) = 24 hours (value "10101100" in hex)
# Active time (T3324) = 10 seconds (value "00001010" in hex)
# Format: <Requested_Periodic_TAU>,<Requested_Active_Time>
AT+CPSMS=1,,,"10101100","00001010"
# Response: OK

# Step 3: Configure eDRX parameters
# For LTE-M (eDRX type 5), cycle = 40.96s (value "0101")
# For NB-IoT (eDRX type 4), cycle = 2621.44s (value "1111")
# Format: <eDRX_Type>,<Requested_eDRX_Value>,<PTW_Value>
# LTE-M: eDRX 40.96s, PTW 5.12s
AT+CEDRXS=1,5,"0101","0010"
# NB-IoT: eDRX 2621.44s, PTW 10.24s
AT+CEDRXS=1,4,"1111","0011"

# Step 4: Verify settings took effect
AT+CEDRXR?         # Read current eDRX settings
AT+CPSMS?          # Read current PSM settings

# Step 5: Force re-attach to apply new parameters
AT+CFUN=0          # Set to minimum functionality
AT+CFUN=1          # Full functionality (re-attach)

# Step 6: Monitor PSM entry
# After active time expires, modem should enter PSM
AT+CSQ            # Check signal (modem still awake)
# Wait 15 seconds (active time = 10s + margin)
AT+CSQ            # If in PSM, this returns ERROR or no response
```

For firmware integration, here's a C snippet for configuring PSM on attach:

```c
// Configure PSM with 24h TAU timer, 10s active time
void configure_psm(void) {
    char response[128];
    
    // Set PSM: enable, no specific request for TAU, TAU=24h, Active=10s
    // T3412 encoding: 24h = 0x10101100 (bit 3=1: unit is hours, value=24)
    // T3324 encoding: 10s = 0x00001010 (bit 3=0: unit is seconds, value=10)
    if (send_at_command("AT+CPSMS=1,,,\"10101100\",\"00001010\"", 
                        response, sizeof(response)) == AT_OK) {
        LOG_INFO("PSM configured: TAU=24h, Active=10s");
    } else {
        LOG_ERROR("PSM config failed: %s", response);
    }
    
    // Force re-attach to apply
    send_at_command("AT+CFUN=0", NULL, 0);
    delay_ms(1000);
    send_at_command("AT+CFUN=1", NULL, 0);
}
```

## Common Pitfalls & Gotchas

1. **Network support is not guaranteed.** PSM and eDRX are optional features. Many networks (especially roaming partners) don't support them, or support only one. Always check `AT+CEDRXR?` after attach to see what the network actually granted. If the response shows `+CEDRXR: 0` or no eDRX parameters, the network rejected your request. Fall back to normal DRX.

2. **Active time (T3324) must be long enough for your application.** If you request 2 seconds but your application needs 5 seconds to complete a transaction, the modem will enter PSM mid-transaction. I've seen devices go unreachable because the active time expired before the server acknowledged the uplink. Rule of thumb: set active time to your worst-case transaction time plus 10 seconds margin.

3. **PSM and eDRX interact in confusing ways.** When both are enabled, the modem first uses eDRX during the active time window, then enters PSM. If you configure eDRX with a 40-second cycle and a 10-second active time, the modem will only use eDRX for 10 seconds, then go dark. This wastes the eDRX configuration. Either use eDRX alone (for reachability) or PSM alone (for maximum sleep), but combining them requires careful timing design.

## Try It Yourself

1. **Measure PSM current draw.** Configure PSM with a 30-second TAU timer and 5-second active time on your module. Use a current profiler (Nordic PPK2, Otii, or even a multimeter in uA mode) to capture the current profile. You should see: ~200mA during attach, ~50mA during active time, then <10uA in PSM. Compare this to normal idle mode (~2-5mA).

2. **Test eDRX reachability.** Configure eDRX for LTE-M with a 40.96s cycle. Send a UDP packet from your server to the device's IP address. Time how long it takes for the device to receive it (measure from server send to device ACK). With eDRX, expect 0-40s latency. With normal DRX, expect 0-1.28s. Document the tradeoff.

3. **Implement a fallback strategy.** Write firmware that attempts PSM first, then falls back to eDRX if the network rejects PSM, then falls back to normal DRX. Use `AT+CPSMS?` and `AT+CEDRXR?` to detect what the network granted. Log the fallback chain for debugging.

## Next Up

Tomorrow: **Modem AT Commands & Cellular Firmware Integration Patterns** — we'll move from power management to the messy reality of integrating a cellular modem into a real-time firmware stack. I'll cover AT command queuing, response parsing with state machines, handling URCs (Unsolicited Result Codes), and the "three-second rule" for modem initialization that most datasheets don't tell you.
