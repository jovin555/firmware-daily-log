---
title: "Day 20: Implementing Pairing, Bonding & Secured Characteristics in Zephyr"
date: 2026-10-30
tags: ["til", "ble-medical", "zephyr", "bonding"]
---

## What I Explored Today

Today I moved past "just get a GATT service advertising" and wired up real security: LE Secure Connections pairing, persistent bonding, and per-characteristic security requirements in Zephyr. The goal was a pulse-oximeter-style service where the measurement characteristic is readable by anyone but the spot-check control point requires an encrypted, authenticated link. I spent most of the day fighting the difference between *pairing* (one-time key exchange) and *bonding* (persisting those keys so reconnection is silent), and learning where Zephyr stores bond data on nRF52 with the settings subsystem. The payoff: a peripheral that pairs once, survives a reboot, and rejects unauthenticated writes with `ATT error 0x05 (Insufficient Authentication)`.

## The Core Concept

BLE security has three separable properties, and conflating them is the #1 source of "why won't it connect" bugs:

1. **Encryption** — the link is encrypted with a key derived during pairing. Without it, anyone with a sniffer reads your medical data.
2. **Authentication** — the pairing method proved both sides know a secret (via passkey, numeric comparison, or OOB). This is what defeats a man-in-the-middle. Encryption without authentication is MITM-able.
3. **Bonding** — the LTK/IRK/CSRK are written to non-volatile storage so the next connection re-encrypts without re-pairing.

For medical devices, you almost always want **LE Secure Connections + bonding + MITM protection** (i.e., authenticated). Legacy pairing (Just Works) gives you encryption but *no* MITM protection — fine for a toy, not for anything touching PHI.

Zephyr's model: you declare a **security level** per characteristic in the GATT attribute (`BT_GATT_PERM_READ_ENCRYPT`, `..._AUTHEN`, etc.), and separately configure the **GAP security callbacks** that drive the pairing procedure. The stack enforces the per-attribute requirement at access time — if the link isn't at that level, the client gets an "Insufficient Encryption/Authentication" error and is expected to trigger pairing. You don't manually gate reads in your handler; the attribute permissions do it for you.

## Key Commands / Configuration / Code

**1. Kconfig — enable the security stack and persistent storage:**

```kconfig
# prj.conf
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_SMP=y                    # Security Manager Protocol (pairing)
CONFIG_BT_SMP_SC_ONLY=y            # LE Secure Connections only, reject legacy
CONFIG_BT_PRIVACY=y                # resolvable private addresses for bonded peers
CONFIG_BT_BONDABLE=y               # persist keys
CONFIG_BT_SETTINGS=y               # route bond data to settings backend
CONFIG_SETTINGS=y
CONFIG_SETTINGS_NVS=y              # NVS backend on flash (nRF52)
CONFIG_BT_KEYS_OVERWRITE_OLDEST=y  # evict oldest bond when store is full
CONFIG_BT_L2CAP_TX_MTU=247
```

**2. GATT attribute permissions — the enforcement point:**

```c
/* Anyone can read the measurement (it's broadcast-ish data). */
BT_GATT_SERVICE_DEFINE(plx_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_PLX),
    BT_GATT_CHARACTERISTIC(BT_UUID_PLX_MEASUREMENT,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ,                 /* open read */
        read_measurement, NULL, NULL),
    /* Control point: encrypted AND authenticated (MITM) to write. */
    BT_GATT_CHARACTERISTIC(BT_UUID_PLX_CONTROL,
        BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
        BT_GATT_PERM_WRITE_ENCRYPT | BT_GATT_PERM_WRITE_AUTHEN,
        NULL, write_control, NULL),
);
```

**3. GAP callbacks — accept pairing, require bonding + MITM:**

```c
static void auth_cancel(struct bt_conn *conn) { /* log */ }

static struct bt_conn_auth_cb auth_cb = {
    .cancel = auth_cancel,
    /* .passkey_display / .passkey_entry set if you have an IO capability */
};

static void pairing_complete(struct bt_conn *conn, bool bonded)
{
    printk("Pairing complete, bonded=%d\n", bonded);
}

static void pairing_failed(struct bt_conn *conn, enum bt_security_err err)
{
    printk("Pairing failed: %d\n", err);
}

static struct bt_conn_auth_info_cb auth_info_cb = {
    .pairing_complete = pairing_complete,
    .pairing_failed   = pairing_failed,
};

/* In main(): */
bt_conn_auth_cb_register(&auth_cb);
bt_conn_auth_info_cb_register(&auth_info_cb);
```

**4. Request security on connect (or let the attribute trigger it):**

```c
static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) return;
    /* Ask for authenticated, bonded link. Stack runs pairing if needed. */
    int rc = bt_conn_set_security(conn, BT_SECURITY_L3); /* L3 = MITM */
    if (rc) printk("set_security failed: %d\n", rc);
}
```

`BT_SECURITY_L3` = encrypted + authenticated (MITM). `L2` = encrypted only. `L4` = L3 + 128-bit key (Secure Connections always gives this, so L3 is usually enough).

## Common Pitfalls & Gotchas

- **`CONFIG_BT_SETTINGS=y` without `CONFIG_SETTINGS=y`** — bonds appear to work in a session but vanish on reboot. The SMP layer silently has nowhere to persist. Always pair these two, and call `settings_load()` in `main()` *before* `bt_enable()`.
- **Forgetting `CONFIG_BT_KEYS_OVERWRITE_OLDEST`** — the default bond store is small (a handful of peers). A device that gets re-paired during testing fills the store and then *silently fails* new pairings with `BT_SECURITY_ERR_...`. Enable overwrite or bump `CONFIG_BT_MAX_PAIRED`.
- **Mismatch between attribute perms and requested security level** — if a characteristic demands `_AUTHEN` but your `bt_conn_set_security()` only asks for `L2`, the client gets `Insufficient Authentication` and may not know to re-pair. Keep the requested level ≥ the strictest attribute permission in your service.

## Try It Yourself

1. **Break it on purpose.** Flash the config above, pair from nRF Connect, then comment out `CONFIG_BT_SETTINGS=y`, rebuild, and reconnect after a reboot. Watch the bond disappear and note the exact `pairing_complete`/re-pair behavior — this is the failure mode you'll debug in the field.
2. **Add a passkey.** Give your device `BT_IO_CAPABILITY_DISPLAY_ONLY` and implement `.passkey_display` in `auth_cb` to print a 6-digit code. Confirm nRF Connect prompts for it and that a wrong code yields `pairing_failed` with an auth error.
3. **Probe the permission gate.** With an unpaired client, attempt a write to the control point and capture the ATT error (`0x05`). Then pair and retry — the same write should now succeed. This proves the attribute-level enforcement is doing the work, not your handler.

## Next Up

Tomorrow: **Power Optimization for BLE Medical Wearables** — connection interval tuning, slave latency, the cost of a 7.5 ms interval on a coin cell, and how to keep notifications snappy without burning the battery.
