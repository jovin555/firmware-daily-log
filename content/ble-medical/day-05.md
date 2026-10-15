---
title: "Day 05: Advertising Deep Dive: AD Types, Scan Response & Extended Advertising"
date: 2026-10-15
tags: ["til", "ble-medical", "advertising", "scan-response"]
---

# Day 05: Advertising Deep Dive: AD Types, Scan Response & Extended Advertising

## What I Explored Today

Today I dug into the actual bytes that go out over the air during advertising. Up until now I've been treating advertising as "just set a name and a UUID and go." But for a medical device, the advertising payload is often the *only* thing a phone or gateway sees before deciding whether to connect — so what's in those 31 bytes (or 255 with extended advertising) matters a lot. I spent the day mapping out AD (Advertising Data) types, how scan response lets you effectively double your payload, and when it's worth jumping to Extended Advertising on Bluetooth 5.

## The Core Concept

Legacy advertising packets are capped at **31 bytes** of payload. That's it. Your flags, your name, your service UUIDs, and any manufacturer-specific data all have to fit in that budget. The reason scan response exists is simple: a broadcaster can respond to an active scan with a *second* 31-byte packet. So in practice you get up to 62 bytes total — but only if the scanner is actively scanning, not passively.

The AD structure itself is a length-type-value (LTV) format. Each field starts with a length byte, then an AD type byte, then the data. If you miscount the length, the whole packet is malformed and many stacks will silently drop it. This is the #1 reason I've seen "my device doesn't show up in nRF Connect."

Extended Advertising (Bluetooth 5.0+) breaks the 31-byte ceiling by moving the payload to secondary channels and using a pointer in the primary packet. You get up to 255 bytes per advertising set, and you can run multiple sets in parallel. For a medical device that wants to broadcast a device ID, a firmware version, and a rolling sensor value without a connection, this is the right tool.

## Key Commands / Configuration / Code

Here's a minimal example using the Zephyr Bluetooth stack (common on nRF52 medical prototypes):

```c
/* Advertising data: flags + 16-bit service UUID + name */
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS,
                  BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, 0x0D, 0x18), /* Health Thermometer */
    BT_DATA(BT_DATA_NAME_COMPLETE, "MedTemp-01", 10),
};

/* Scan response: manufacturer data with a rolling sensor value */
static uint8_t mfg_data[] = { 0x59, 0x00, /* Company ID (example) */
                              0x01,       /* payload version */
                              0x00, 0x00 }; /* placeholder for temp */
static struct bt_data sd[] = {
    BT_DATA(BT_DATA_MANUFACTURER_DATA, mfg_data, sizeof(mfg_data)),
};

/* Start legacy advertising with scan response enabled */
int err = bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad),
                          sd, ARRAY_SIZE(sd));
```

For Extended Advertising on the same stack:

```c
static struct bt_le_ext_adv *adv;

/* Create an extended advertising set (up to 255 bytes payload) */
bt_le_ext_adv_create(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_EXT_ADV |
                                     BT_LE_ADV_OPT_CONN,
                                     0x0030 /* 30ms */,
                                     0x0060 /* 60ms */,
                                     NULL),
                     NULL, &adv);

/* Set data — can exceed 31 bytes */
bt_le_ext_adv_set_data(adv, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));

/* Start advertising */
bt_le_ext_adv_start(adv, BT_LE_EXT_ADV_START_DEFAULT);
```

On the Linux side, `btmgmt` lets you inspect what's actually being broadcast:

```bash
# Enable advertising debug output
sudo btmgmt add-adv -d 0x0001 -c 0x00  # instance 1, connectable
sudo btmgmt advinfo 1                   # dump current AD payload
```

And `hcitool lescan --duplicates` or `bluetoothctl scan on` will show you the parsed AD fields in real time.

## Common Pitfalls & Gotchas

**1. Length byte off-by-one.** The length byte counts the AD type byte *plus* the data, not the whole field. `BT_DATA(BT_DATA_NAME_COMPLETE, "MedTemp-01", 10)` is correct because the string is 10 bytes and the macro handles the type byte. If you hand-roll the buffer, one wrong count and the parser stops reading at that field.

**2. Scan response is not guaranteed.** Passive scanners (some gateways, some Android background scan modes) never send a scan request, so they never see your scan response data. If a field is critical — like a device ID — put it in the main advertising packet, not the scan response.

**3. Extended advertising isn't universally supported.** Many older phones and cheap BLE gateways only do legacy advertising. If your medical device needs to work with a hospital's existing infrastructure, test legacy first. Also, extended advertising on the primary channel still uses the same 31-byte budget for the *header* — the payload moves to secondary channels, which some sniffers won't capture.

## Try It Yourself

1. **Dump your own AD payload.** Run `sudo btmon` in one terminal and `bluetoothctl scan on` in another. Find your device's advertising report and decode the AD types by hand. Confirm the length bytes match what you intended.

2. **Move a field from scan response to advertising data.** Take a device that currently puts its name in the scan response and move it into the main packet. Rescan with a passive scanner (e.g., `hcitool lescan --passive`) and confirm the name still appears.

3. **Enable extended advertising on an nRF52 DK.** Flash the Zephyr `ext_adv` sample, then scan with a Bluetooth 5-capable phone using nRF Connect. Note the "Extended" flag in the scan result and compare the payload size to a legacy advertisement.

## Next Up

Tomorrow: **Connection Parameters: Interval, Peripheral Latency & Supervision Timeout** — how to pick values that keep a medical sensor responsive without draining the coin cell in a week.
