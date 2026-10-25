---
title: "Day 15: Security Modes & Levels: Mode 1 Levels 1-4, Mode 2 & Attribute Permissions"
date: 2026-10-25
tags: ["til", "ble-medical", "security-levels", "permissions"]
---

## What I Explored Today

Today I dug into the BLE Security Manager's two-dimensional security model: **Security Modes** (what kind of protection) crossed with **Security Levels** (how strong that protection is). This is the part of the spec that trips people up because "Level 3" means different things depending on whether you're in Mode 1 or Mode 2, and the attribute permissions you set on a GATT characteristic are only *requests* — the actual enforcement depends on the negotiated security level of the link. For a medical device, getting this wrong means either a pulse-oximetry stream leaking to any unpaired phone in the room, or a legitimate clinician's app failing to read a characteristic because the peripheral demanded encryption the phone didn't have. I spent the day mapping the matrix and testing it against a real peripheral.

## The Core Concept

The Security Manager Protocol (SMP) defines two orthogonal axes:

- **Mode 1** protects against *passive eavesdropping* only. It's about encryption. Levels 1–4 escalate the key strength and authentication.
- **Mode 2** adds *data signing* (a 64-bit signature appended to the ATT PDU) for cases where you can't afford the latency of a full encrypted link — think a coin-cell sensor that wakes, sends one reading, and sleeps. Signing is unauthenticated by definition; it proves the sender holds the CSRK, not who they are.

The levels within Mode 1:

| Level | Requirement |
|-------|-------------|
| 1 | No security (open link) |
| 2 | Unauthenticated pairing with encryption (Just Works) |
| 3 | Authenticated pairing with encryption (Passkey / OOB / Numeric Comparison) |
| 4 | Authenticated LE Secure Connections pairing with encryption (ECDH P-256) |

The critical insight: **the peripheral doesn't decide the level — the attribute permissions do.** Each characteristic has a security requirement encoded in its permissions (e.g., `READ | ENCRYPT | AUTHENTICATE`). When a client tries to read it, the stack checks the current link's security level against that requirement. If the link is too weak, the stack returns `ATT_ERROR_INSUFFICIENT_ENCRYPTION` (0x0F) or `ATT_ERROR_INSUFFICIENT_AUTHENTICATION` (0x05), which triggers the client to initiate pairing/encryption. This is why you can't just "set the device to Level 4" — you set it per attribute, and the stack negotiates up on demand.

For medical devices this matters because a heart-rate characteristic and a device-firmware-update characteristic should not require the same level. HR is arguably fine at Level 2; firmware update must be Level 4 with authenticated LE Secure Connections, or you've built a remote code execution primitive.

## Key Commands / Configuration / Code

Zephyr's GATT API makes the permission-to-level mapping explicit. Here's a characteristic that demands authenticated LE Secure Connections encryption:

```c
/* Requires Level 4: authenticated LE Secure Connections */
BT_GATT_CHARACTERISTIC(&firmware_ctrl_uuid.uuid,
    BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
    BT_GATT_PERM_WRITE_AUTHEN | BT_GATT_PERM_WRITE_LESC,
    NULL, write_fw_ctrl, NULL),

/* Level 2 is enough for a live HR stream */
BT_GATT_CHARACTERISTIC(&hr_meas_uuid.uuid,
    BT_GATT_CHRC_NOTIFY,
    BT_GATT_PERM_NONE,   /* notify perms are on the CCCD */
    NULL, NULL, NULL),
```

The `BT_GATT_PERM_WRITE_AUTHEN` flag maps to Level 3+, and `BT_GATT_PERM_WRITE_LESC` forces Level 4. Note that `BT_GATT_PERM_NONE` on a notify characteristic is correct — you gate the CCCD write instead.

On the BlueZ side, you can inspect and set the required security per attribute in a GATT server using the D-Bus `Flags` property, but the more useful debugging tool is `btmon`:

```bash
# Watch SMP pairing and the resulting security level
sudo btmon -w capture.snoop
# In another shell, trigger a read that requires auth:
bluetoothctl
[bluetooth]# connect AA:BB:CC:DD:EE:FF
[bluetooth]# menu gatt
[bluetooth]# select-attribute /org/bluez/hci0/dev_AA.../service.../char...
[bluetooth]# read
```

In the `btmon` output you'll see the `SMP Pairing Request` with its `AuthReq` byte — bit 2 (`MITM`) and bit 3 (`SC`) are the ones that determine whether you land at Level 3 or 4. If `SC` is clear, you're capped at Level 3 even with MITM set.

To force a minimum on the peripheral side in Zephyr, you can also gate at the connection level:

```c
static void auth_cancel(struct bt_conn *conn) { /* ... */ }

static struct bt_conn_auth_cb auth_cb = {
    .cancel = auth_cancel,
    /* passkey_display, etc. */
};

/* In the connection callback, request security explicitly: */
bt_conn_set_security(conn, BT_SECURITY_L4);
```

`BT_SECURITY_L4` here requests authenticated LE Secure Connections; if the peer can't do it, the callback fires with an error and you should disconnect.

## Common Pitfalls & Gotchas

**1. Mode 2 signing is not encryption, and the level numbering is separate.** People assume "Mode 2 Level 2" is stronger than "Mode 1 Level 2." It isn't — Mode 2 Level 2 means *unauthenticated data signing*, which provides integrity and replay protection but zero confidentiality. A signed PDU is readable by anyone sniffing. For a medical device transmitting PHI, Mode 2 is almost never the right answer unless you're layering your own application encryption on top.

**2. `BT_GATT_PERM_READ_ENCRYPT` does not mean "authenticated."** It means Level 2. If you write `BT_GATT_PERM_READ_ENCRYPT` on a characteristic holding patient identifiers, a Just Works pairing satisfies it — and Just Works is trivially MITM-able. You want `BT_GATT_PERM_READ_AUTHEN` (Level 3) at minimum, and `_LESC` for Level 4.

**3. The CCCD inherits nothing automatically.** If you set `BT_GATT_PERM_WRITE_AUTHEN` on a notify characteristic but leave the CCCD at default permissions, an unauthenticated peer can enable notifications and receive data. In Zephyr the CCCD permissions come from the characteristic's `BT_GATT_CCC` definition — set them explicitly with `BT_GATT_CCC_MANAGED` and a matching permission mask, or you've left the back door open.

## Try It Yourself

1. **Map your own device's matrix.** Enumerate every characteristic in your GATT table and write down its current permission flags. For each, decide the *minimum* Mode 1 level it actually needs. You'll almost certainly find at least one characteristic at Level 1 that shouldn't be.

2. **Trigger the error path deliberately.** Using `bluetoothctl` against your peripheral, read an authenticated characteristic *before* pairing. Confirm you see `ATT_ERROR_INSUFFICIENT_AUTHENTICATION` in `btmon`, then pair and read again. This is the exact flow a clinician's app will hit on first connection.

3. **Break Level 4 on purpose.** Configure a peer to pair with Just Works (clear the `MITM` bit in `AuthReq`) and attempt to write your firmware-control characteristic. Verify the write is rejected. If it succeeds, your `_LESC` flag isn't actually set.

## Next Up

Tomorrow: **Privacy: Resolvable Private Addresses, IRK & the Filter Accept List** — how a medical wearable can stop broadcasting a static MAC that lets anyone track a patient through a hospital, and why the Filter Accept List is the only sane way to reconnect without leaking identity.
