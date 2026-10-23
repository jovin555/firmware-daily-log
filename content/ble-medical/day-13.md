---
title: "Day 13: LE Legacy Pairing vs LE Secure Connections (ECDH P-256)"
date: 2026-10-23
tags: ["til", "ble-medical", "le-secure-connections", "ecdh"]
---

## What I Explored Today

Today I dug into the two pairing generations that every BLE medical device firmware engineer eventually has to choose between: **LE Legacy Pairing** (the original 4.0 mechanism based on the TK/STK exchange) and **LE Secure Connections** (introduced in Bluetooth 4.2, built on ECDH over P-256). On paper they look like two checkbox options in the GAP settings. In practice, the choice determines whether a passive eavesdropper who captured the pairing exchange can brute-force the link key offline in seconds, or whether they're stuck staring at an elliptic curve they can't invert. For a glucose meter or a pulse oximeter that pairs once and then streams data for years, this is not an academic distinction — it's the difference between a device that's secure by design and one that's only secure if nobody was listening during the first 30 seconds of its life.

## The Core Concept

The fundamental problem pairing solves is: two devices that have never met need to agree on a long-term key (the LTK) over a radio channel that anyone can hear. Legacy Pairing solves this with the **Temporary Key (TK)** — a shared secret that is either `0x0000000000000000` (Just Works), a 6-digit passkey, or an OOB value. Both sides run the **c1** function (a custom AES-based mixing function) over the TK, the two random nonces, and the pairing parameters to derive the **STK**. The critical weakness: the entire STK derivation is a deterministic function of values that are *all transmitted in the clear* except the TK. An attacker who sniffs the pairing exchange captures the nonces and the confirm values, then runs the same c1 function offline against every possible TK. For Just Works that's a single guess. For a 6-digit passkey it's 10⁶ guesses — trivial on a laptop. The link key is recovered in under a second.

**LE Secure Connections** replaces this with **Elliptic Curve Diffie-Hellman over P-256**. Each device generates an ephemeral private/public keypair, exchanges public keys, and computes a shared secret `DHKey = X-coordinate of (private × peer_public)`. Because ECDH is a one-way function, an eavesdropper who sees both public keys cannot compute the shared secret — that's the discrete log problem on P-256, which is computationally infeasible. The DHKey then feeds into the **f4/f5/f6/g2** functions (all AES-CMAC based) to derive the LTK and to authenticate the exchange. The authentication step (numeric comparison, passkey, or OOB) is what binds the ECDH exchange to the actual humans/devices, preventing a man-in-the-middle who substitutes their own public keys.

The practical upshot: with Secure Connections, even **Just Works** pairing is resistant to passive eavesdropping. The MITM risk remains (Just Works has no authentication), but the "record the pairing, crack the key later" attack class is dead. That's why the Bluetooth SIG and FDA-aligned security guidance increasingly treat LE Secure Connections as the baseline for medical devices.

## Key Commands / Configuration / Code

On Zephyr, the choice is a Kconfig symbol. Both can be enabled simultaneously — the stack negotiates the highest common generation during the Pairing Feature Exchange.

```kconfig
# prj.conf — enable both, prefer Secure Connections
CONFIG_BT_SMP=y
CONFIG_BT_SMP_SC_ONLY=n          # allow legacy fallback for old phones
CONFIG_BT_SMP_SC_PAIR_ONLY=n     # if y, reject any legacy pairing attempt
CONFIG_BT_PRIVACY=y              # resolvable private addresses pair well with SC
CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16
```

If you want to *enforce* Secure Connections (recommended for new medical designs):

```kconfig
CONFIG_BT_SMP_SC_ONLY=y          # only SC; legacy peers will fail to pair
```

On Nordic's SoftDevice (nRF5 SDK), the equivalent is a bitmask in the security parameters:

```c
// ble_gap_sec_params_t
ble_gap_sec_params_t sec_params = {
    .bond          = 1,
    .mitm          = 1,
    .lesc          = 1,   // LE Secure Connections
    .keypress      = 0,
    .io_caps       = BLE_GAP_IO_CAPS_DISPLAY_YESNO,
    .oob           = 0,
    .min_key_size  = 16,
    .max_key_size  = 16,
    .kdist_own     = { .enc = 1, .id = 1 },
    .kdist_peer    = { .enc = 1, .id = 1 },
};
sd_ble_gap_authenticate(conn_handle, &sec_params);
```

On the Linux/BlueZ side you can inspect what actually got negotiated after pairing:

```bash
# Pair and then dump the bond info
bluetoothctl <<EOF
pair AA:BB:CC:DD:EE:FF
info AA:BB:CC:DD:EE:FF
EOF

# The "Paired: yes" line plus the absence of a legacy warning
# indicates SC was used. For deeper inspection:
sudo btmon -w /tmp/pairing.snoop &
# ... perform pairing ...
# Then open in Wireshark: look for "SMP Pairing Response"
# and check the "Secure Connections" flag (bit 3 of AuthReq)
```

The AuthReq byte in the Pairing Request/Response is where the SC flag lives — bit 3 (`0x08`). If either side doesn't set it, the stack falls back to legacy.

## Common Pitfalls & Gotchas

**1. "SC enabled" ≠ "SC used."** Enabling `CONFIG_BT_SMP_SC_ONLY=n` lets the stack negotiate down to legacy if the peer doesn't advertise SC support. Many cheap BLE modules and older Android versions still don't. If your threat model requires SC, set `SC_ONLY=y` and accept that some peers won't pair — test against your actual phone fleet before shipping.

**2. The LTK derivation differs between generations.** Legacy derives the LTK from the STK via `s1(STK, r1, r2)`; Secure Connections derives it from the DHKey via `f5`. If you're doing key management on a host (e.g., storing LTKs in a secure element), make sure your key-derivation code path matches the generation that actually paired. A mismatch produces a bond that "works" until the first reconnect, then fails with an MIC error.

**3. Debugging SC is harder because the interesting values aren't on the air.** With legacy you can watch the c1 inputs in a sniffer and reproduce the STK. With SC, the DHKey never crosses the air — you need the private keys from the device. Plan for on-device logging of the DHKey (in a debug build only, obviously) if you need to reproduce a pairing failure.

## Try It Yourself

1. **Sniff a legacy pairing and crack it.** Use two nRF52 DKs, force legacy pairing (`CONFIG_BT_SMP_SC_ONLY=n` and a peer that doesn't advertise SC), capture with `btmon` or a nRF Sniffer, and use the `crackle` tool to recover the TK and LTK from the capture. Then repeat with SC enabled and confirm crackle fails.

2. **Inspect the AuthReq byte.** Capture a pairing exchange from your phone to your dev board and decode the AuthReq field in both the Pairing Request and Response. Confirm bit 3 (SC) is set on both sides. If it isn't, figure out which side is downgrading.

3. **Force SC-only and test your fleet.** Set `CONFIG_BT_SMP_SC_ONLY=y`, reflash, and attempt to pair with every phone/tablet you own. Document which ones fail — that's your real-world compatibility matrix, and it's the number your product manager will ask for.

## Next Up

Tomorrow: **Pairing Methods: Just Works, Passkey Entry, Numeric Comparison & OOB** — the four ways to authenticate a pairing, when each is appropriate for a medical device, and why "Numeric Comparison" is the sweet spot for devices with a display but no keypad.
