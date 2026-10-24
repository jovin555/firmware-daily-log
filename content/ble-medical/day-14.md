---
title: "Day 14: Pairing Methods: Just Works, Passkey Entry, Numeric Comparison & OOB"
date: 2026-10-24
tags: ["til", "ble-medical", "just-works", "passkey"]
---

# Day 14: Pairing Methods: Just Works, Passkey Entry, Numeric Comparison & OOB

## What I Explored Today

Today I dug into the four association models defined by the BLE Secure Connections pairing procedure: Just Works, Passkey Entry, Numeric Comparison, and Out-of-Band (OOB). These aren't just UI variations — each one maps to a different threat model and a different bit of the pairing state machine. For a medical device, picking the wrong one is the difference between a glucose monitor that's trivially impersonated and one that isn't. I traced through how the IO Capability exchange drives the selection, then exercised each method against a Nordic nRF52 dev kit and a Linux BlueZ host to see what actually happens on the wire and in the logs.

## The Core Concept

BLE pairing has two jobs: establish an encrypted link, and distribute keys so the link can be re-established later without pairing again. The encryption itself is fine — AES-128 CCM with a Diffie-Hellman key exchange (ECDH on P-256 in LE Secure Connections). The hard problem is **authentication**: how do two devices that have never met prove they're talking to the right peer and not a man-in-the-middle?

That's what the association model solves. During the Pairing Request/Response, each side advertises its IO capabilities (NoInputNoOutput, DisplayOnly, DisplayYesNo, KeyboardOnly, KeyboardDisplay). The spec's table then picks a method:

- **Just Works** — no user interaction, no MITM protection. The ECDH exchange still happens, but nobody verifies the resulting keys. An attacker who relays packets between the two devices can complete pairing with each side independently. Fine for a heart-rate strap streaming to a phone in your pocket; unacceptable for anything that writes therapy parameters.
- **Passkey Entry** — one device displays a 6-digit number, the user types it into the other. The passkey is mixed into the confirm values, so a MITM can't produce matching confirms without knowing it. 20 bits of entropy — brute-forceable offline in theory, but the protocol rate-limits attempts.
- **Numeric Comparison** — both devices display the same 6-digit number and the user confirms they match. This is the strongest of the interactive methods because the number is derived from both public keys; a MITM would produce two different numbers. Requires both sides to have a display and at least one button.
- **OOB** — the confirm values are exchanged over a separate channel (NFC, a QR code, a pre-shared secret). Highest security if the OOB channel is trustworthy, and the only method that works with NoInputNoOutput on both sides while still giving MITM protection.

The key insight: **the association model is chosen by the IO capabilities, not by you directly.** You influence it by declaring the right capabilities and by setting the authentication requirements in the Pairing Request. If you want MITM protection, you set the MITM bit — and if the peer can't satisfy it, pairing fails rather than silently downgrading. That fail-closed behavior is what you want in a medical device.

## Key Commands / Configuration / Code

On Zephyr (nRF52), the IO capabilities and auth requirements are set at init:

```c
/* main.c — declare capabilities BEFORE advertising */
static struct bt_conn_auth_cb auth_cb = {
    .passkey_display = passkey_display,   /* show 6-digit code */
    .passkey_entry   = passkey_entry,     /* prompt user to type */
    .numeric_compare = numeric_compare,   /* yes/no on matching digits */
    .cancel          = auth_cancel,
};

/* Require MITM + bonding + LE Secure Connections */
static struct bt_conn_auth_info_cb info_cb = {0};

int err = bt_conn_auth_cb_register(&auth_cb);
err = bt_conn_auth_info_cb_register(&info_cb);

/* In the advertising/connection setup: */
bt_conn_set_security(conn, BT_SECURITY_L4);  /* L4 = MITM + SC + 128-bit */
```

`BT_SECURITY_L4` forces LE Secure Connections with MITM protection. If the peer only offers Just Works, the connection is rejected — which is exactly what you want for a device that dispenses insulin.

On BlueZ (Linux host side), you can watch the negotiation:

```bash
# Pair with explicit agent that supports numeric comparison
bluetoothctl
[bluetooth]# agent NoInputNoOutput   # forces Just Works — for testing only
[bluetooth]# pair AA:BB:CC:DD:EE:FF

# Or use a capable agent to exercise Numeric Comparison:
[bluetooth]# agent DisplayYesNo
[bluetooth]# pair AA:BB:CC:DD:EE:FF
# BlueZ prints: "Confirm passkey 123456 (yes/no):"
```

To inspect what actually got negotiated, enable the kernel HCI trace:

```bash
sudo btmon -w /tmp/pairing.btsnoop &
# ... perform pairing ...
# Then grep for the IO Capability and AuthReq bytes in the SMP Pairing Request:
#   IO Capability: 0x03 (DisplayYesNo)
#   AuthReq: 0x0d (Bonding | MITM | SC)
```

The `AuthReq` byte is where the MITM bit lives (bit 2). If it's clear, you're getting Just Works regardless of what the UI shows.

## Common Pitfalls & Gotchas

1. **Silent downgrade to Just Works.** If you set `BT_SECURITY_L2` (encryption without MITM) instead of `L4`, the stack happily accepts Just Works and you'll never see an error. Audit your security level constants — `L2` is the default in many samples and it's the wrong choice for anything clinical.

2. **Numeric Comparison needs a button, not just a display.** `DisplayYesNo` means the device can show the number *and* accept a yes/no. A device with a display but no input must declare `DisplayOnly`, which forces Passkey Entry (peer types) or Just Works. Mismatched capability declarations are the #1 cause of "pairing works on my phone but not the gateway."

3. **OOB requires the OOB data to be exchanged before pairing starts.** You call `bt_conn_oob_auth_reply()` with the 16-byte confirm value from the NFC/QR channel. If you try to set it after the Pairing Request, the stack has already committed to a different method. Also: OOB data is single-use — regenerate it after every pairing or you've defeated the point.

## Try It Yourself

1. **Force Just Works and observe the gap.** Set your peripheral to `BT_SECURITY_L2` with `NoInputNoOutput` capabilities, pair from `bluetoothctl`, then use `btmon` to confirm the `AuthReq` byte has the MITM bit clear. Note that the link is encrypted but unauthenticated.

2. **Exercise Numeric Comparison.** Set the peripheral to `DisplayYesNo` and `BT_SECURITY_L4`, pair from a phone, and confirm the 6-digit number matches on both screens. Then try pairing from a `NoInputNoOutput` central — watch it fail closed with `BT_SECURITY_ERR_AUTH_FAIL`.

3. **Implement a passkey callback.** Wire up `passkey_display` on the peripheral to print the code over UART, and `passkey_entry` on a second dev kit to read it from a serial prompt. Verify in `btmon` that the `SMP Pairing Confirm` values differ from a Just Works run.

## Next up

Tomorrow: **Security Modes & Levels: Mode 1 Levels 1-4, Mode 2 & Attribute Permissions** — how the GATT layer enforces what pairing negotiated, why `BT_SECURITY_L4` on the connection doesn't automatically protect every characteristic, and how to set per-attribute permissions so a read of your therapy log actually requires an authenticated link.
