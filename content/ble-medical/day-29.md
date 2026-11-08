---
title: "Day 29: Full Review & Project: Secure BLE Pulse Oximeter Peripheral to Mobile App"
date: 2026-11-08
tags: ["til", "ble-medical", "review", "project"]
---

# Day 29: Full Review & Project: Secure BLE Pulse Oximeter Peripheral to Mobile App

## What I Explored Today

Today I pulled the entire 28-day arc together into a single, buildable reference design: a secure BLE pulse oximeter peripheral that streams SpO₂ and heart rate to a mobile app. Rather than introduce new concepts, I re-verified every layer end-to-end — the GATT service layout, the pairing/bonding flow, the encrypted characteristic permissions, the notification pacing, and the disconnect/reconnect behavior — and confirmed they compose correctly. This is the "does it actually work as a system" day, and the answer is: only if you get the security handshake and the connection parameters right. Everything else is plumbing.

## The Core Concept

A medical peripheral is not just a GATT server that emits numbers. The *why* behind this project is that a pulse oximeter carries protected health information, so the transport must guarantee three properties simultaneously: **confidentiality** (SpO₂ values must not be readable by an unpaired sniffer), **authenticity** (the app must know it's talking to the real sensor, not a spoofed peripheral), and **integrity** (measurements can't be tampered with in flight). BLE gives you all three through LE Secure Connections pairing with bonding, but only if the characteristic permissions enforce encryption and authentication at the attribute layer — not just at the app layer.

The second core idea is **pacing**. Pulse oximeters update roughly once per second, but the PPG waveform and the computed SpO₂/HR values have different latency tolerances. You want notifications at a stable cadence the phone can rely on, which means negotiating a connection interval that balances latency against radio-on time (battery). Get this wrong and you either drain the coin cell or drop packets.

## Key Commands / Configuration / Code

**GATT service definition (Zephyr/nRF-style, but the UUIDs and flags are standard):**

```c
/* Pulse Oximeter Service — 16-bit assigned number 0x1822 */
BT_GATT_SERVICE_DEFINE(plx_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_PLX),

    /* PLX Spot-Check Measurement — 0x2A5E, notify + encrypted + authenticated */
    BT_GATT_CHARACTERISTIC(BT_UUID_PLX_SPOT_CHECK_MEASUREMENT,
        BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_NONE,          /* no read/write, notify only */
        NULL, NULL, NULL),
    BT_GATT_CCC(plx_ccc_changed,
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_ENCRYPT),

    /* PLX Continuous Measurement — 0x2A5F */
    BT_GATT_CHARACTERISTIC(BT_UUID_PLX_CONTINUOUS_MEASUREMENT,
        BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_NONE,
        NULL, NULL, NULL),
    BT_GATT_CCC(plx_ccc_changed,
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_ENCRYPT),
);
```

**Enforce LE Secure Connections + bonding in the advertising/security config:**

```c
static struct bt_le_conn_param conn_param = {
    .interval_min = BT_GAP_MS_TO_CONN_INTERVAL(30),   /* 30 ms */
    .interval_max = BT_GAP_MS_TO_CONN_INTERVAL(50),   /* 50 ms */
    .latency      = 0,
    .timeout      = BT_GAP_MS_TO_CONN_TIMEOUT(4000),
};

static void auth_cb(enum bt_security_err err) {
    if (err) printk("Pairing failed: %d\n", err);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .security_changed = auth_cb,
};

/* Require LESC with MITM protection and bonding */
static const struct bt_security sec = {
    .level = BT_SECURITY_L3,   /* encrypted + authenticated */
};
bt_conn_set_security(conn, &sec);
```

**Notification pacing — send once per second from a work item:**

```c
/* Encode per Bluetooth SIG PLX spec: flags byte, then SFLOAT SpO2, PR, etc. */
static void send_measurement(struct k_work *w) {
    uint8_t buf[5];
    buf[0] = 0x00;                       /* flags: spot-check, no optional fields */
    sys_put_le16(sfloat_encode(spo2), &buf[1]);  /* SpO2 as SFLOAT */
    buf[3] = pulse_rate;                 /* PR, 8-bit */
    buf[4] = 0x00;
    bt_gatt_notify(NULL, &plx_svc.attrs[1], buf, sizeof(buf));
    k_work_schedule(&meas_work, K_SECONDS(1));
}
```

**Verify on the phone side (Android):**

```bash
# Confirm the characteristic requires encryption before you can subscribe
adb shell dumpsys bluetooth_manager | grep -i "0x2A5E"
# Expect: properties=NOTIFY, permissions=ENCRYPTED
```

## Common Pitfalls & Gotchas

1. **Setting `BT_GATT_PERM_NONE` on the characteristic but forgetting the CCC permission.** The value characteristic can be notify-only, but the Client Characteristic Configuration Descriptor still needs `WRITE_ENCRYPT` — otherwise an unpaired device can subscribe and the stack will happily queue notifications it can't legally deliver. The pairing prompt appears at CCC-write time, not at connect time.

2. **Using `BT_SECURITY_L2` when you need `L3`.** L2 is encrypted-but-unauthenticated, which permits a MITM during pairing. For PHI you want L3 (authenticated), which forces a passkey or numeric comparison. If you only set L2, iOS may still bond but Android's `createBond()` will succeed without MITM and your "secure" claim is hollow.

3. **Connection interval too aggressive for the radio.** A 7.5 ms interval looks great for latency but triples the peripheral's average current draw versus 30–50 ms. For a 1 Hz oximeter, 30–50 ms with latency 0 is the sweet spot; going below 20 ms buys nothing and costs battery.

## Try It Yourself

1. **Build the GATT table and dump it.** Flash the service definition above to an nRF52 DK, connect with nRF Connect, and confirm the CCC descriptor shows an encrypted-write requirement before pairing. Try subscribing pre-pairing and watch it fail.

2. **Break the security level on purpose.** Change `BT_SECURITY_L3` to `BT_SECURITY_L2`, re-pair, and observe that the phone no longer prompts for a passkey. Then revert and confirm the numeric-comparison prompt returns.

3. **Measure the current draw.** With a PPK2 or similar, compare average current at 7.5 ms vs 50 ms connection intervals while notifying at 1 Hz. Log the delta — you should see a meaningful multiplier.

## Next Up

Tomorrow is the **Full Review** — a consolidated retrospective of the entire 29-day series, the architecture decisions that aged well, the ones I'd reverse, and a checklist you can hand to a firmware team starting a BLE medical device from scratch.
