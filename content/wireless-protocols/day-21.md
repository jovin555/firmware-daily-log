---
title: "Day 21: Network Selection Strategy: Choosing a Protocol for Your Product"
date: 2026-07-21
tags: ["til", "wireless-protocols", "protocol-selection"]
---

## What I Explored Today

Today I dug into the decision matrix that separates successful wireless products from field failures: network selection strategy. It's not about which protocol is "best" — it's about which protocol best fits your power budget, data rate, range, and deployment topology. I worked through a structured comparison of BLE, Wi-Fi, Thread/Matter, LoRaWAN, and Zigbee, mapping each to real product constraints. The key takeaway: your protocol choice locks in your hardware bill of materials, antenna design, and certification path before you write a single line of application code.

## The Core Concept

Network selection is a multi-constraint optimization problem. You cannot maximize range, data rate, and battery life simultaneously — physics forbids it. The Shannon-Hartley theorem and Friis transmission equation are not negotiable. Every protocol represents a specific trade-off point on the power-bandwidth-distance curve.

The real mistake I see engineers make is starting with a protocol they "know" (usually BLE or Wi-Fi) and then forcing the product to fit. Instead, you should start with three hard constraints:

1. **Power budget**: How many µA can you spend per transmission? A coin-cell device (CR2032, ~225 mAh) cannot sustain Wi-Fi for more than a few days of continuous operation. BLE advertising at 1-second intervals draws ~20 µA average — that's years of life.
2. **Latency requirement**: Does the device need sub-10 ms response (e.g., a game controller) or can it tolerate seconds of delay (e.g., a soil moisture sensor reporting every hour)?
3. **Infrastructure dependency**: Can you assume a smartphone gateway (BLE), a Wi-Fi access point, a Thread border router, or a LoRaWAN base station? Each adds deployment complexity.

The decision tree looks like this:
- **Need high throughput (>1 Mbps) and have mains power?** → Wi-Fi (802.11n or better).
- **Need low power, short range, and smartphone interaction?** → BLE (Bluetooth 5.x LE).
- **Need mesh networking with low power and interoperability?** → Thread (over 802.15.4) with Matter application layer.
- **Need kilometers of range and sub-50-byte payloads?** → LoRaWAN (sub-GHz, Class A for battery life).
- **Need mature, proven mesh for home automation?** → Zigbee (3.0, also 802.15.4, but no native IP).

## Key Commands / Configuration / Code

When evaluating a protocol, I always build a minimal power-profiling test. Here's how I measured BLE advertising current on an nRF52840 using the Zephyr RTOS:

```c
/* prj.conf for BLE power measurement */
CONFIG_BT=y
CONFIG_BT_LL_SW_SPLIT=y
CONFIG_BT_CTLR_TX_PWR_ANTENNA=0   /* 0 dBm output */
CONFIG_BT_CTLR_ADV_INTERVAL=100   /* 100 ms advertising interval */
CONFIG_SYS_CLOCK_TICKS_PER_SEC=1000
CONFIG_PM=y                        /* Enable power management */
CONFIG_PM_DEVICE=y

/* main.c - minimal BLE advertiser for power profiling */
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>

#define DEVICE_NAME CONFIG_BT_DEVICE_NAME
#define DEVICE_NAME_LEN (sizeof(DEVICE_NAME) - 1)

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, DEVICE_NAME, DEVICE_NAME_LEN),
};

void main(void)
{
    int err;

    printk("BLE advertiser starting (0 dBm, 100 ms interval)\n");
    err = bt_enable(NULL);
    if (err) {
        printk("Bluetooth init failed (err %d)\n", err);
        return;
    }

    /* Start undirected advertising */
    err = bt_le_adv_start(BT_LE_ADV_NCONN, ad, ARRAY_SIZE(ad),
                          NULL, 0);
    if (err) {
        printk("Advertising failed to start (err %d)\n", err);
        return;
    }

    printk("Advertising... measure current on VDD pin\n");
    while (1) {
        k_sleep(K_FOREVER);  /* Keep alive, PM handles sleep */
    }
}
```

To profile, connect a 10-ohm shunt resistor in series with VDD and measure voltage drop with an oscilloscope. At 0 dBm, 100 ms interval, I measured ~5.4 mA peaks for 1.2 ms, yielding ~65 µA average — well within coin-cell budget.

For a LoRaWAN comparison, here's a TTN-compatible join command using the LMIC library on an STM32WL:

```c
/* LoRaWAN OTAA join with DR0 (SF12, 125 kHz) for maximum range */
void lora_join_network(void)
{
    LMIC_setDrTxpow(DR_SF12, 14);  /* SF12, 14 dBm */
    LMIC_startJoining();
    /* Current draw: ~25 mA during TX, 1.5 µA sleep */
    /* Expect join time: 5-30 seconds depending on gateway */
}
```

## Common Pitfalls & Gotchas

1. **Ignoring the idle current**: Many engineers optimize TX current but forget that the radio's sleep current dominates lifetime. A Wi-Fi module in DTIM10 sleep still draws ~1 mA — that's 225 hours on a CR2032. BLE in deep sleep draws <1 µA. Always check the datasheet's "deep sleep" or "shutdown" current, not just the active TX current.

2. **Assuming symmetric link budgets**: LoRaWAN uplink (end device to gateway) can be 20 dB better than downlink because the gateway has higher TX power and better antenna. If your application needs reliable downlink commands (e.g., OTA updates), you may need Class B or C LoRaWAN, which kills battery life. I've seen products fail because they assumed symmetric performance.

3. **Overlooking regulatory certification**: BLE and Wi-Fi share the 2.4 GHz ISM band but have different emission masks and spurious limits. A module that passes FCC for BLE may fail for Wi-Fi due to higher peak currents causing supply rail noise. Always budget for separate certification runs — or use pre-certified modules (e.g., u-blox, Espressif, Nordic) to save 8-12 weeks.

## Try It Yourself

1. **Power budget calculation**: Take your product's battery capacity (e.g., 1000 mAh for a Li-Po). Calculate how many transmissions per day you can support with BLE (advertising at 100 ms, 5.4 mA peak, 1.2 ms pulse) vs. Wi-Fi (DTIM10, 1 mA idle, 150 mA TX for 50 ms). Plot the battery life vs. transmission interval for both.

2. **Range test with RSSI logging**: Flash two nRF52840 DKs with the BLE beacon example above. Walk 10, 30, 50, and 100 meters with line-of-sight and log the RSSI (use `bt_le_adv_start` with scan response). Compare the path loss exponent you measure against the free-space Friis equation (n=2). Repeat with a LoRaWAN module at SF12 — note the range difference.

3. **Protocol selection matrix**: For a hypothetical product (battery-powered temperature sensor, 10 readings/day, 2-year battery life, 50-meter range, smartphone app), build a decision matrix with rows for BLE, Thread, and LoRaWAN. Score each on power, data rate, latency, infrastructure cost, and certification effort. Which wins?

## Next Up

Tomorrow, I'll dive into the Zephyr Networking Stack: Connection Manager & Sockets API — how to manage network interfaces, handle connectivity events, and write portable socket code across Wi-Fi, Ethernet, and cellular.
