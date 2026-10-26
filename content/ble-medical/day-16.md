---
title: "Day 16: Privacy: Resolvable Private Addresses, IRK & the Filter Accept List"
date: 2026-10-26
tags: ["til", "ble-medical", "privacy", "rpa"]
---

## What I Explored Today

Today I dug into how BLE keeps a wearable from being tracked across a hospital floor while still letting the right gateway find it. The mechanism is Resolvable Private Addresses (RPAs), derived from an Identity Resolving Key (IRK) shared during bonding, and the Filter Accept List that lets a controller do the matching in hardware. I traced the full lifecycle: how the address rotates, how the peer resolves it, and where the privacy actually lives (hint: it's the key distribution, not the address format). I also confirmed on a Nordic nRF52 and a Zephyr build that the controller resolves RPAs before the host ever sees a connection event, which matters for power and for the medical gateway's connection latency.

## The Core Concept

A public BLE address is a permanent MAC — broadcast it and anyone with a cheap sniffer can follow your patient monitor from the ICU to the pharmacy. A *static random* address is better (no vendor OUI) but still constant, so it's trackable. The real fix is an address that changes every ~15 minutes and that only trusted peers can correlate.

An RPA is 48 bits: the top two bits are `01` (that's what marks it "resolvable private"), the upper 24 bits are a random `prand`, and the lower 24 bits are `hash = ah(IRK, prand)`. The `ah` function is AES-128 with the IRK as key, applied to `prand`, truncated to 24 bits. A peer that holds the same IRK recomputes the hash; if it matches, the address belongs to a known device. Everyone else sees noise that rotates.

The IRK is exchanged once, encrypted, during bonding (Phase 3 of the SMP pairing, distributed via the `Encryption Information` and `Identity Information` keys). After that, the device advertises under fresh RPAs and the peer resolves them locally — no over-the-air lookup, no server, no privacy leak. This is why the security of the whole scheme rests on bonding: leak the IRK and you can deanonymize the device forever.

The Filter Accept List is the payoff. Instead of waking the host CPU for every advertiser in range, you load the peer's IRK (or its identity address) into the controller. The controller resolves incoming RPAs against the list in hardware and only reports matches. On a coin-cell medical patch, that's the difference between a week of battery and a day.

## Key Commands / Configuration / Code

Zephyr, generating and storing an IRK and enabling privacy on the peripheral:

```c
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/settings/settings.h>

static bt_addr_le_t id_addr; /* our identity address (public or static random) */

/* Load identity + IRK from settings (persisted across reboots) */
int err = settings_load();
if (err) { /* handle */ }

/* Enable controller-based privacy: controller generates/uses the IRK
 * and rotates RPAs automatically. Requires CONFIG_BT_PRIVACY=y. */
bt_le_oob oob;
err = bt_le_oob_get_local(BT_ID_DEFAULT, &oob); /* populates oob.addr (RPA) */

/* Advertise with a resolvable private address */
struct bt_le_adv_param adv_param = BT_LE_ADV_PARAM_INIT(
    BT_LE_ADV_OPT_CONN | BT_LE_ADV_OPT_USE_IDENTITY,
    BT_GAP_ADV_FAST_INT_MIN_2, BT_GAP_ADV_FAST_INT_MAX_2, NULL);
err = bt_le_adv_start(&adv_param, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
```

Central side — add a bonded peer to the Filter Accept List so the controller resolves its RPA and only wakes us on a match:

```c
/* After bonding, the peer's IRK is in the bond info. Add to accept list. */
bt_addr_le_t peer_id;
bt_le_filter_accept_list_add(&peer_id); /* controller now resolves this peer's RPAs */

/* Scan with the accept list filter — host only sees matching advertisers */
struct bt_le_scan_param scan = BT_LE_SCAN_PARAM_INIT(
    BT_LE_SCAN_TYPE_PASSIVE,
    BT_LE_SCAN_OPT_FILTER_ACCEPT_LIST,   /* hardware-side filtering */
    BT_GAP_SCAN_FAST_INTERVAL, BT_GAP_SCAN_FAST_WINDOW);
bt_le_scan_start(&scan, scan_cb);
```

Inspecting what the controller actually resolved (nRF Connect / `btmon`):

```bash
# btmon shows the RPA on air and the resolved identity address
sudo btmon -w capture.snoop
# Look for: "LE Advertising Report" with Address Type: Random (0x01)
# followed by "Identity Address" once the controller resolves it.
```

Key Kconfig for the peripheral: `CONFIG_BT_PRIVACY=y`, `CONFIG_BT_RPA_TIMEOUT=900` (seconds, the 15-minute default), and `CONFIG_BT_FILTER_ACCEPT_LIST=y` on the central.

## Common Pitfalls & Gotchas

- **`BT_LE_ADV_OPT_USE_IDENTITY` vs. privacy.** If you set `USE_IDENTITY` *and* privacy, the controller advertises under the identity address, not an RPA — you've just defeated the whole point. Use identity only for bonded reconnection where you explicitly want the stable address, and understand the tradeoff.
- **IRK is only as private as the bond.** If your device allows Just Works pairing (no MITM), an attacker within radio range during the first bond can capture the IRK exchange. For medical devices, require LE Secure Connections with passkey or OOB, or the RPA is theater.
- **Filter Accept List capacity is finite.** Many controllers support only 8–16 entries. A gateway tracking 40 patient monitors can't hold them all in hardware; you'll fall back to host-side resolution and lose the power win. Check `HCI_LE_Read_Filter_Accept_List_Size` before designing the fleet.

## Try It Yourself

1. Flash a Zephyr peripheral with `CONFIG_BT_PRIVACY=y` and `CONFIG_BT_RPA_TIMEOUT=60`, then run `btmon` for five minutes. Confirm the advertised address changes and that the top two bits are `01` (i.e., the first hex nibble of the address is `4`, `5`, `6`, or `7`).
2. Bond a central, then add the peer to the Filter Accept List and scan with `BT_LE_SCAN_OPT_FILTER_ACCEPT_LIST`. Verify the host callback fires only for your device while a second unbonded phone advertising nearby is ignored.
3. Deliberately break it: set `BT_LE_ADV_OPT_USE_IDENTITY` on the peripheral and re-scan. Watch the address stop rotating — a concrete demo of why that flag and privacy are mutually exclusive.

## Next up

Tomorrow we go on the offensive: **BLE Attacks — Sniffing, MITM, Replay, KNOB & BLESA**. We'll look at how a passive sniffer captures a bond, how the KNOB attack forces a 1-byte entropy key, and why BLESA breaks reconnection authentication even on patched stacks.
