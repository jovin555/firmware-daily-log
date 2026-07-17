---
title: "Day 17: Wi-Fi Low Power: Wi-Fi HaLow & Power-Save Modes for IoT"
date: 2026-07-17
tags: ["til", "wireless-protocols", "wifi-halow", "power-save"]
---

## What I Explored Today

Today I dove into the intersection of Wi-Fi and ultra-low-power IoT—specifically Wi-Fi HaLow (802.11ah) and the power-save mechanisms that make traditional Wi-Fi viable for battery-operated sensors. While Bluetooth LE and Thread dominate the low-power narrative, Wi-Fi HaLow offers a compelling alternative for applications requiring longer range (up to 1 km) and higher throughput (up to 347 Mbps) while still achieving years of battery life. I also revisited the classic 802.11 power-save modes (PS-Poll, U-APSD) that engineers must understand when deploying Wi-Fi on constrained devices like the ESP32 or Pico W.

## The Core Concept

The fundamental tension in Wi-Fi for IoT is that standard Wi-Fi (802.11a/b/g/n/ac) was designed for high throughput, not low power. A typical Wi-Fi radio draws 100–300 mA in active receive mode—unacceptable for a sensor that must last a year on a coin cell. The solution comes in two flavors: **legacy power-save modes** that trade latency for battery life, and **Wi-Fi HaLow** which redefines the PHY and MAC layers from the ground up.

**Legacy Power-Save (PS-Poll and U-APSD):** In PS-Poll mode, the station tells the AP it’s entering doze state. The AP buffers incoming frames. The station wakes periodically (every beacon interval, typically 100 ms) to check the Traffic Indication Map (TIM) in the beacon. If traffic is pending, it sends a PS-Poll frame to retrieve one buffered frame at a time. This works but introduces high latency and overhead per frame. U-APSD (Unscheduled Automatic Power Save Delivery) improves this by allowing the AP to burst multiple frames after a trigger frame from the station, reducing the number of wake cycles.

**Wi-Fi HaLow (802.11ah):** This operates in sub-1 GHz bands (e.g., 868 MHz in Europe, 915 MHz in US), which inherently provides better propagation and lower path loss. The key power-saving innovation is **Target Wake Time (TWT)** —the station negotiates a specific schedule with the AP for when it will wake to exchange data. Outside these negotiated windows, the station can sleep with near-zero power draw. TWT is deterministic, unlike the probabilistic beacon-based wakeup in legacy modes. HaLow also supports shorter preambles and narrower channel widths (1/2/4/8 MHz) to reduce active time.

## Key Commands / Configuration / Code

### 1. ESP32 Power-Save Configuration (Legacy 802.11)

Using the ESP-IDF framework, you can enable modem sleep (the deepest power-save without disconnecting):

```c
#include "esp_wifi.h"
#include "esp_pm.h"

// Configure power management
esp_pm_config_t pm_config = {
    .max_freq_mhz = 80,          // CPU frequency when active
    .min_freq_mhz = 40,          // CPU frequency when idle
    .light_sleep_enable = true   // Enable light sleep during idle
};
esp_pm_configure(&pm_config);

// Enable Wi-Fi power save (modem sleep)
esp_wifi_set_ps(WIFI_PS_MIN_MODEM);  // Minimum modem power save
// Alternative: WIFI_PS_MAX_MODEM for maximum power save (higher latency)

// Set beacon interval (AP side) - default 100ms
// On the AP, you can increase to 300ms for less frequent wakeups
// esp_wifi_set_config(WIFI_IF_AP, &ap_config); // ap_config.beacon_interval = 300;
```

**Real power draw:** With `WIFI_PS_MIN_MODEM`, an ESP32 draws ~0.8 mA in DTIM3 sleep (waking every 3rd beacon). With `WIFI_PS_MAX_MODEM`, it drops to ~0.3 mA but latency jumps to ~300 ms.

### 2. Wi-Fi HaLow TWT Negotiation (Linux iw command)

On a HaLow-capable chipset (e.g., Newracom NRC7292), TWT is configured via `iw`:

```bash
# Set up TWT with a 5-second wake interval, 10ms service period
iw dev wlan0 twt setup 5000 10

# Check TWT agreement status
iw dev wlan0 twt status

# Tear down TWT
iw dev wlan0 twt teardown
```

The station sends a TWT setup request to the AP. The AP responds with a TWT flow ID and schedule. The station then wakes only at the agreed times.

### 3. U-APSD Configuration (ESP32)

U-APSD allows the AP to deliver multiple frames per wake cycle:

```c
// Enable WMM (required for U-APSD)
esp_wifi_set_config(WIFI_IF_STA, &sta_config); // sta_config.wmm_cap = true;

// Set U-APSD for all access categories
uint8_t uapsd_mask = BIT(AC_BK) | BIT(AC_BE) | BIT(AC_VI) | BIT(AC_VO);
esp_wifi_set_uapsd_mask(uapsd_mask);

// Now when the station sends a trigger frame (e.g., a QoS Null),
// the AP will burst all buffered data
```

## Common Pitfalls & Gotchas

1. **PS-Poll starvation under high load:** When multiple stations use PS-Poll, the AP can become overwhelmed servicing individual polls. Each PS-Poll requires a separate ACK and data frame exchange. In dense deployments (e.g., 50+ sensors), switch to U-APSD or TWT to reduce overhead. I’ve seen networks collapse with >30 PS-Poll stations on a consumer AP.

2. **TWT requires AP support:** Most consumer Wi-Fi routers do not support 802.11ah or TWT. HaLow is a separate radio—you need a HaLow AP (e.g., Newracom or Morse Micro reference designs). You cannot mix HaLow stations with a standard 2.4 GHz AP. For legacy Wi-Fi, U-APSD is more widely supported but still not universal—test with your specific AP.

3. **Beacon interval tuning is a double-edged sword:** Increasing the beacon interval from 100 ms to 300 ms reduces wake frequency but also delays association, DHCP, and ARP. If your sensor needs to respond quickly to a cloud command, a 300 ms sleep cycle adds unacceptable latency. Always measure round-trip time under power-save.

## Try It Yourself

1. **Measure ESP32 power-save current:** Flash an ESP32 with the modem sleep configuration above. Connect a current meter (e.g., INA219) between the USB 5V and the ESP32’s 3.3V regulator. Log current over 60 seconds while the device is connected to Wi-Fi but idle. Compare `WIFI_PS_MIN_MODEM` vs `WIFI_PS_MAX_MODEM`. Note the latency difference by pinging the device.

2. **Test U-APSD with a UDP burst:** Configure an ESP32 as a UDP server with U-APSD enabled. From a PC, send 10 UDP packets in rapid succession (e.g., using `socat` or a Python script). Capture the Wi-Fi traffic with Wireshark. Observe that with U-APSD, you see a single trigger frame followed by a burst of data frames. Without U-APSD, you’ll see 10 separate PS-Poll/data exchanges.

3. **Simulate TWT with a Linux machine (if no HaLow hardware):** Use the `iw` command to set up a TWT schedule on a standard Wi-Fi interface (the kernel will accept the command even if the hardware doesn’t support it—check `dmesg` for errors). This is useful for understanding the API and parsing the TWT information element in packet captures.

## Next Up

Tomorrow, we’ll move up the stack to **CoAP: Constrained Application Protocol Over UDP**—the HTTP equivalent for IoT, with retransmission, resource discovery, and observe patterns that keep your sensors sleeping longer. We’ll implement a CoAP server on an ESP32 and compare its efficiency against raw UDP and MQTT.
