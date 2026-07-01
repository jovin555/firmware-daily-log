---
title: "Day 01: Wireless Protocol Landscape: Range, Power & Throughput Tradeoffs"
date: 2026-07-01
tags: ["til", "wireless-protocols", "wireless", "protocol-comparison"]
---

## What I Explored Today

I mapped the wireless protocol landscape for low-power IoT, focusing on the fundamental tradeoffs between range, power consumption, and data throughput. The key insight: no protocol excels at all three simultaneously. Bluetooth Low Energy (BLE) optimizes for low power at short range with moderate throughput, LoRaWAN sacrifices throughput for kilometer-range links, and Wi-Fi HaLow (802.11ah) attempts to bridge the gap. I ran real-world range tests with an nRF52840 DK running BLE 5.0 long-range mode (coded PHY) and compared link budgets against a LoRa SX1276 module at 868 MHz.

## The Core Concept

Every wireless link is governed by the **link budget equation**:

```
Received Power (dBm) = Tx Power (dBm) + Tx Antenna Gain (dBi) - Path Loss (dB) + Rx Antenna Gain (dBi) - Rx Sensitivity (dBm)
```

The tradeoff triangle emerges from three constraints:
- **Range** requires either higher transmit power (battery killer) or lower data rate (spreading gain)
- **Throughput** demands wider bandwidth or higher-order modulation (reduces sensitivity)
- **Power** is consumed by active radio time, which scales with data rate and retransmissions

For battery-operated sensors, the critical metric is **energy per bit** (J/bit). BLE at 1 Mbps consumes ~5 nJ/bit at 0 dBm Tx power. LoRa at SF12 (≈300 bps) consumes ~200 nJ/bit—40x worse per bit, but you get 10x the range. The choice depends entirely on your application's duty cycle and distance requirements.

## Key Commands / Configuration / Code

### BLE 5.0 Long Range (Coded PHY) on nRF52840

```c
// Configure BLE radio for coded PHY (125 kbps, 8x spreading gain)
// This gives ~4x range improvement over 1 Mbps uncoded

#include <nrfx_radio.h>

void ble_coded_phy_config(void) {
    // Set TX power to maximum (8 dBm for nRF52840)
    nrf_radio_txpower_set(NRF_RADIO_TXPOWER_POS8DBM);
    
    // Configure for BLE coded PHY (S=8 coding)
    nrf_radio_mode_set(NRF_RADIO_MODE_BLE_LR125KBIT);
    
    // Enable long-range preamble (80 μs instead of 8 μs)
    nrf_radio_preamble_set(NRF_RADIO_PREAMBLE_LONG_RANGE);
    
    // Set CRC length to 24-bit for robustness
    nrf_radio_crc_configure(NRF_RADIO_CRC_SKIP_ADDR, 0x100065, 0x555555);
}
```

### LoRaWAN Link Budget Calculation (Python)

```python
# Calculate maximum range for LoRa at 868 MHz
import math

def loora_link_budget(tx_power_dbm=14, tx_gain_dbi=2, rx_gain_dbi=2, 
                      freq_mhz=868, sf=12, bw_khz=125):
    # LoRa sensitivity at SF12, 125 kHz BW (typical SX1276)
    rx_sensitivity = -137  # dBm
    
    # Path loss using free-space model (optimistic)
    # Real-world: add 20-30 dB for urban clutter
    def free_space_path_loss(d_km):
        return 32.44 + 20 * math.log10(freq_mhz) + 20 * math.log10(d_km)
    
    # Solve for max distance
    max_path_loss = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - rx_sensitivity
    max_distance_km = 10 ** ((max_path_loss - 32.44 - 20 * math.log10(freq_mhz)) / 20)
    
    print(f"Max theoretical range: {max_distance_km:.1f} km")
    print(f"Data rate at SF12: {bw_khz * (2**sf) / (2**sf):.0f} bps")  # ~300 bps
    return max_distance_km

# Run calculation
loora_link_budget()
```

### Wi-Fi HaLow (802.11ah) Configuration Snippet

```bash
# On an Atheros AR9344-based HaLow access point
# Configure for 1 MHz channel, MCS0 (lowest rate)

iw dev wlan0 set channel 1 1  # Channel 1, 1 MHz bandwidth
iw dev wlan0 set bitrates legacy-2.4 1  # Force 1 Mbps (lowest)
iwconfig wlan0 txpower 10  # dBm (10 mW for battery savings)
```

## Common Pitfalls & Gotchas

1. **BLE Range Claims Are Deceptive**: BLE 5.0 "400m range" is quoted for coded PHY at 125 kbps with -103 dBm sensitivity, but that's in free space. Add 20 dB of building penetration loss, and you're down to 40m. Always test with your specific enclosure and environment.

2. **LoRa Duty Cycle Limits**: In EU 868 MHz band, LoRa is limited to 1% duty cycle per sub-band. At SF12 (≈300 bps), you can transmit only 36 seconds per hour. That's 13.5 kB of data per day. Many engineers forget this and design systems that violate regulations.

3. **Throughput ≠ Application Throughput**: BLE 2 Mbps PHY gives 1.4 Mbps raw, but after protocol overhead (preamble, access address, CRC, MIC, connection intervals), real application throughput is ~800 kbps. For LoRa, the overhead from preamble, header, and CRC reduces effective throughput by ~30%.

## Try It Yourself

1. **Calculate your link budget**: Pick a protocol (BLE, LoRa, or Zigbee). Measure the actual RSSI at 10m, 50m, and 100m in your office/house. Compare to the free-space path loss model. How much excess loss does your environment add?

2. **Energy per bit comparison**: Using datasheet current consumption numbers, calculate J/bit for BLE 1 Mbps (TX=8.5 mA @ 3V) vs LoRa SF12 (TX=120 mA @ 3.7V). Assume 1 ms transmit time per packet. Which is more efficient for sending 10 bytes every hour?

3. **Protocol selection matrix**: List three IoT applications: (a) a wearable heart rate monitor, (b) a soil moisture sensor in a 5-acre farm, (c) a security camera streaming 720p video. For each, rank BLE, LoRa, and Wi-Fi HaLow by suitability. Justify your choices using the tradeoff triangle.

## Next Up

Tomorrow: **BLE Fundamentals: GAP Roles, Advertising & Connections** — we'll dive into the Bluetooth LE stack, understand the Generic Access Profile (GAP) roles (Broadcaster, Observer, Peripheral, Central), and write code to set up advertising packets and establish connections on an nRF52840. Bring your logic analyzer.
