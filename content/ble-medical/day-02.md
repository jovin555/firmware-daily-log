---
title: "Day 02: BLE Physical Layer: 2.4 GHz Channels & the 1M, 2M and Coded PHYs"
date: 2026-10-12
tags: ["til", "ble-medical", "phy", "rf"]
---

# Day 02: BLE Physical Layer: 2.4 GHz Channels & the 1M, 2M and Coded PHYs

## What I Explored Today

Today I dug into the BLE physical layer — the part of the stack that actually pushes bits onto the 2.4 GHz ISM band. I mapped out the 40 RF channels (37 data + 3 advertising), looked at how GFSK modulation differs between the 1M, 2M, and Coded PHYs, and spent time with a Nordic nRF52840 DK and a spectrum analyzer confirming what the datasheet claims. The interesting part wasn't the channel map itself (that's well documented) — it was understanding *why* the spec gives us three PHYs and when a medical device should actually pick Coded over 1M.

## The Core Concept

BLE lives in the 2.4 GHz ISM band, from 2402 MHz to 2480 MHz, divided into 40 channels spaced 2 MHz apart. Channels 37 (2402 MHz), 38 (2426 MHz), and 39 (2480 MHz) are the advertising channels — deliberately placed to sit between Wi-Fi channels 1, 6, and 11, which are the only non-overlapping Wi-Fi channels in North America. The other 37 channels carry data and hop pseudo-randomly during a connection.

The modulation is Gaussian Frequency Shift Keying (GFSK) with a modulation index of 0.5 and a BT product of 0.5. The three PHYs differ in symbol rate and coding:

- **LE 1M** — 1 Msym/s, 1 bit per symbol. The baseline. Mandatory for every BLE device.
- **LE 2M** — 2 Msym/s, 1 bit per symbol. Same modulation, double the rate. Higher throughput, but roughly 3 dB less receiver sensitivity because the same energy is spread over half the symbol period.
- **LE Coded** — 1 Msym/s with forward error correction. Two variants: S=2 (500 kbps, 2× coding) and S=8 (125 kbps, 8× coding). The S=8 variant buys ~12 dB of link budget, which is why it's the PHY of choice for implantables and anything that has to punch through a body or a wall.

For medical devices, the PHY choice is a link-budget decision, not a throughput decision. A continuous glucose monitor transmitting every 5 minutes doesn't care about 2 Mbps — it cares about staying connected when the patient rolls over onto the sensor. That's a Coded PHY problem.

## Key Commands / Configuration / Code

On the nRF Connect SDK, PHY selection happens at connection time via the Link Layer. Here's how to request Coded PHY on a peripheral using Zephyr's Bluetooth stack:

```c
/* prj.conf — enable the PHY update procedure and coded PHY support */
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_USER_PHY_UPDATE=y
CONFIG_BT_CTLR_PHY_CODED=y
CONFIG_BT_CTLR_PHY_2M=y
```

```c
/* Request Coded PHY (S=8) on both TX and RX after connection */
static void request_coded_phy(struct bt_conn *conn)
{
    struct bt_conn_le_phy_param phy = {
        .options = BT_CONN_LE_PHY_OPT_CODED_S8,
        .pref_tx_phy = BT_GAP_LE_PHY_CODED,
        .pref_rx_phy = BT_GAP_LE_PHY_CODED,
    };
    int err = bt_conn_le_phy_update(conn, &phy);
    if (err) {
        printk("PHY update failed: %d\n", err);
    }
}
```

The peer can reject the request — PHY updates are negotiated, not commanded. Always check the resulting PHY in the `bt_conn_le_phy_info` callback:

```c
static void phy_updated(struct bt_conn *conn,
                        struct bt_conn_le_phy_info *param)
{
    printk("TX PHY: %d, RX PHY: %d\n", param->tx_phy, param->rx_phy);
    /* BT_GAP_LE_PHY_1M = 1, BT_GAP_LE_PHY_2M = 2, BT_GAP_LE_PHY_CODED = 3 */
}
```

To verify what's actually on the air, use the nRF Sniffer with Wireshark. The `btle` dissector shows the PHY in the packet metadata, and you can filter with `btle.phy == 3` to see only Coded traffic. On the RF side, a spectrum analyzer set to 2402 MHz with a 2 MHz span will show the GFSK hump — on 2M PHY the occupied bandwidth doubles, which is a quick sanity check that your stack actually switched.

## Common Pitfalls & Gotchas

**1. Assuming Coded PHY is always slower end-to-end.** The 125 kbps raw rate is misleading. Coded PHY's longer preamble and coding overhead mean connection events carry fewer payload bytes per unit time, but the *effective* throughput in a lossy environment can be higher than 1M because you're not retransmitting. For a body-worn ECG streaming at 1 kbps, Coded S=8 wins on reliability, not on raw speed.

**2. Forgetting that advertising PHYs and connection PHYs are separate.** You can advertise on Coded PHY (extended advertising only — legacy advertising is 1M-only) and then negotiate 2M for the connection. Many stacks default to 1M for both and engineers wonder why range is poor. Check `bt_le_ext_adv_create` parameters and the `BT_LE_ADV_OPT_*` flags.

**3. Ignoring the 2M sensitivity hit in regulatory testing.** FCC and ETSI limits are on conducted power, not sensitivity, but your link budget calculation must account for the ~3 dB sensitivity loss on 2M. If your medical device was designed with 6 dB margin on 1M, switching to 2M for throughput eats half of it. Measure, don't assume.

## Try It Yourself

1. **Measure the channel map.** Using an nRF52840 DK and the `radio_test` sample from nRF Connect SDK, sweep channels 0–39 and log RSSI with a nearby Wi-Fi AP active. Confirm that advertising channels 37/38/39 show lower interference than the data channels sitting on top of Wi-Fi 1/6/11.

2. **Force a PHY switch and observe it.** Build the peripheral_phy_update sample, connect with nRF Connect for Mobile, and use the "PHY" tab to request 2M, then Coded S=8. Watch the connection interval and throughput change in the app's live graph.

3. **Calculate your link budget.** Take your device's TX power (e.g., +4 dBm on nRF52840), antenna gain, path loss at 2.4 GHz for your worst-case distance, and receiver sensitivity for each PHY (1M: −96 dBm, 2M: −93 dBm, Coded S=8: −103 dBm typical). Determine which PHY closes the link with 10 dB margin.

## Next Up

Tomorrow: **Link Layer: States, Advertising Channels & Connection Events** — how the Link Layer state machine moves between standby, advertising, scanning, initiating, and connection, and why the connection event timing model matters for power budgeting in battery-powered medical devices.
