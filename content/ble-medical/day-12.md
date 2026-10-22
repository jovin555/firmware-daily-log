---
title: "Day 12: BLE Security Overview: Pairing, Bonding & the Security Manager Protocol"
date: 2026-10-22
tags: ["til", "ble-medical", "smp", "pairing"]
---

## What I Explored Today

Today I dug into the Security Manager Protocol (SMP), the fixed L2CAP channel (CID 0x0006) that handles pairing, key distribution, and encryption setup on every BLE link. My goal was to stop treating "pairing" as a black box and understand exactly what happens on the wire when a medical peripheral asks a phone to bond. I traced the full sequence — Pairing Request/Response, key exchange, key distribution, and the encryption procedure — and mapped each step to what a firmware engineer actually configures on the peripheral side. This is the foundation everything else in BLE security builds on, so getting the mental model right now pays off when I look at LE Secure Connections tomorrow.

## The Core Concept

The critical distinction: **pairing** is a one-time process that establishes keys; **bonding** is the act of storing those keys so the link can be re-encrypted later without pairing again. Pairing without bonding means you redo the whole dance on every reconnect. For a medical device — a glucose meter, a wearable ECG patch — you almost always want bonding, because the patient shouldn't re-pair every session, and you want the link encrypted from the first byte of data.

SMP has three jobs: (1) agree on a temporary key (TK) or use a key-exchange method, (2) derive and distribute the long-term keys (LTK, IRK, CSRK), and (3) drive encryption on the link. The security level you get depends on the pairing method chosen, which in turn depends on the IO capabilities both sides advertise. This is why a device with `NoInputNoOutput` IO capability can only ever get "Just Works" pairing — unauthenticated, vulnerable to a man-in-the-middle. If your medical device has a display, use it: Passkey or Numeric Comparison gives you authenticated pairing, which is what regulators and threat models actually want.

The security properties are negotiated, not assumed. The Pairing Request carries an auth-req bitmask (bonding flag, MITM protection, Secure Connections, keypress) and the maximum encryption key size. The responder answers with its own capabilities, and the *intersection* determines the outcome. If either side doesn't request MITM, you silently fall back to Just Works.

## Key Commands / Configuration / Code

On Zephyr, the peripheral's security posture is set through `bt_conn_auth_cb` and the security parameters. Here's the practical configuration:

```c
/* Advertised IO capability — this drives the pairing method.
 * A device with a display + yes/no buttons can do Numeric Comparison
 * (LE Secure Connections) or Passkey Entry (legacy). */
static struct bt_conn_auth_cb auth_cb = {
    .passkey_display = passkey_display,   /* show 6-digit passkey */
    .passkey_entry   = passkey_entry,     /* if we have a keypad */
    .cancel          = auth_cancel,
};

/* Request security on connect: level 3 = authenticated + encrypted,
 * bond = persist keys to NVS so reconnect re-encrypts silently. */
static void request_security(struct bt_conn *conn)
{
    int err = bt_conn_set_security(conn, BT_SECURITY_L3 | BT_SECURITY_FORCE_PAIR);
    if (err) {
        LOG_ERR("set_security failed (%d)", err);
    }
}

/* Register callbacks once at init. */
bt_conn_auth_cb_register(&auth_cb);
```

The `BT_SECURITY_L3` constant maps to an authenticated, encrypted link (LESC or legacy with MITM). `BT_SECURITY_L4` adds a 128-bit LE Secure Connections key requirement. `BT_SECURITY_FORCE_PAIR` forces a fresh pairing even if a bond exists — useful during development, dangerous in production.

To inspect what actually got negotiated on a Linux host, `btmon` is the tool:

```bash
# Capture SMP traffic on the HCI interface
sudo btmon -w smp_capture.snoop

# Then filter for SMP opcodes (0x03 = Pairing Request, 0x04 = Response,
# 0x0C = Encryption Information, 0x11 = Identity Information)
```

The SMP opcode field is the first byte of the SMP PDU. Pairing Request is `0x01`, Pairing Response `0x02`, Pairing Confirm `0x03`, Pairing Random `0x04`, Encryption Information `0x06`, Master Identification `0x07`, Identity Information `0x08`, Identity Address Information `0x09`, Signing Information `0x0A`, Security Request `0x0B`. Watching these in order tells you exactly which method was used.

## Common Pitfalls & Gotchas

**1. Bonding silently disabled by the peer.** If the central's auth-req doesn't set the bonding flag, no LTK is stored and you re-pair on every reconnect. Symptom: the phone prompts "Pair with device?" repeatedly. Check the auth-req byte in the Pairing Request — bit 0 is Bonding_Flags.

**2. Key size truncation.** The Pairing Request carries a max encryption key size (7–16 bytes). If a peer requests 7 bytes, you get a 56-bit key — technically valid, cryptographically weak. Reject anything below 16 for medical data; enforce it in your `auth_cb` or by checking the negotiated parameters.

**3. Stale bonds after firmware update.** If you regenerate the IRK or change the device identity during a firmware update without clearing the peer's bond store, reconnection fails with an encryption failure. Always provide a "forget device" path, and version your bond storage so an update can invalidate old bonds cleanly.

## Try It Yourself

1. **Capture a pairing.** Run `sudo btmon -w pair.snoop`, then pair a phone to your dev board. Open the capture and identify the Pairing Request/Response, then confirm which pairing method was selected from the IO capability bytes.

2. **Force a security level.** In your firmware, call `bt_conn_set_security(conn, BT_SECURITY_L3)` on connect and log the return value. Then connect with a central that only supports Just Works and observe the failure — this is your MITM gate.

3. **Break bonding on purpose.** Clear the bond store on the peripheral (`bt_unpair(BT_ID_DEFAULT, NULL)`) while keeping the phone's bond, then reconnect. Watch the encryption failure in `btmon` and note the SMP error code returned.

## Next Up

Tomorrow: **LE Legacy Pairing vs LE Secure Connections (ECDH P-256)** — why the legacy TK-based pairing is fundamentally broken against passive eavesdroppers, and how the P-256 ECDH exchange in LE Secure Connections fixes it. I'll walk through the actual key derivation and show what changes in your firmware config.
