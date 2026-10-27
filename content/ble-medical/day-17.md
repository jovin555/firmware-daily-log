---
title: "Day 17: BLE Attacks: Sniffing, MITM, Replay, KNOB & BLESA"
date: 2026-10-27
tags: ["til", "ble-medical", "attacks", "mitm"]
---

# Day 17: BLE Attacks: Sniffing, MITM, Replay, KNOB & BLESA

## What I Explored Today

Today I moved from building BLE medical devices to breaking them. I set up a small lab with a Nordic nRF52840 dongle running the Sniffer firmware, a Raspberry Pi 4 with a built-in BT 5.0 controller, and my trusty HackRF for the physical-layer experiments. I walked through five attack classes that matter for medical IoT: passive sniffing, man-in-the-middle, replay, KNOB (Key Negotiation of Bluetooth), and BLESA (BLE Spoofing Attack). The goal wasn't to become a pentester overnight — it was to understand *which* of these actually apply to a glucose monitor or an insulin pump, and what mitigations are worth the BOM cost.

## The Core Concept

BLE's security model rests on three pillars: **pairing** (establishing keys), **encryption** (protecting the link), and **authentication** (proving identity). Every attack below exploits a gap in one of these pillars.

- **Sniffing** exploits the fact that BLE's link-layer encryption is only as strong as the pairing that produced the key. If a device uses Just Works pairing (no MITM protection), the key is derived from a 6-digit TK that an attacker can brute-force offline in milliseconds. Once you have the LTK, you decrypt every packet.
- **MITM** exploits the pairing exchange itself. If the user can't verify a passkey or numeric comparison, an attacker positioned between two devices can relay pairing messages and end up with two sets of keys — one shared with each side.
- **Replay** exploits the absence of application-layer freshness. BLE's link-layer encryption has a packet counter, but if your GATT characteristic accepts a "start insulin bolus" command without a nonce or timestamp, an attacker who captured one encrypted frame can re-inject it later (or the same frame can be replayed by a malicious peripheral).
- **KNOB** (CVE-2019-9506) exploits the fact that the entropy negotiation in the BR/EDR (and BLE) key-establishment procedure is unauthenticated. An attacker in the middle can force both sides down to 1 byte of entropy, making the session key brute-forceable in ~2^8 attempts.
- **BLESA** (2020) exploits reconnection. After a device reconnects, many stacks skip re-authentication and trust the previously bonded peer. An attacker who spoofs the peripheral's address can impersonate it and push data to the central.

For medical devices, the practical ranking of risk is: **replay > BLESA > MITM > KNOB > sniffing**. Replay is trivially exploitable against naive GATT designs; sniffing requires physical proximity and a $10 dongle but yields nothing if pairing is LE Secure Connections with OOB or passkey.

## Key Commands / Configuration / Code

### 1. Passive sniffing with nRF Sniffer + Wireshark

```bash
# Flash the nRF Sniffer firmware to an nRF52840 dongle, then:
# Wireshark -> Edit -> Preferences -> Protocols -> nRF Sniffer for Bluetooth LE
# Set the interface to the dongle's COM port (e.g., /dev/ttyACM0 on Linux)

# From the CLI, capture to pcapng for offline analysis:
tshark -i /dev/ttyACM0 -w ble_capture.pcapng -a duration:60

# Filter for ATT writes to a specific handle (e.g., insulin bolus characteristic):
tshark -r ble_capture.pcapng -Y "btatt.opcode == 0x12 && btatt.handle == 0x0025"
```

### 2. MITM with a Raspberry Pi as a relay

```bash
# On the Pi, use btproxy (from BlueZ) to expose the HCI to a second host:
sudo btproxy -i hci0 -p 10001

# On the attacker host, connect to the proxy and run a GATT client:
# (btproxy forwards HCI, so the attacker's stack sees the real controller)
sudo hcitool -i hci0 lescan
```

The relay works because the attacker's controller is now the *central* to the peripheral and the *peripheral* to the real central — classic MITM. Mitigation: require LE Secure Connections with passkey or numeric comparison, which binds the pairing to a human-verified secret.

### 3. Replay detection in firmware (Zephyr example)

```c
/* Reject replayed GATT writes by tracking a monotonic counter per characteristic. */
static uint32_t last_bolus_seq = 0;

static ssize_t on_bolus_write(struct bt_conn *conn,
                              const struct bt_gatt_attr *attr,
                              const void *buf, uint16_t len,
                              uint16_t offset, uint8_t flags)
{
    const struct bolus_cmd *cmd = buf;
    if (len != sizeof(*cmd)) return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);

    /* Reject if the sequence number is not strictly greater than the last seen. */
    if (cmd->seq <= last_bolus_seq) {
        LOG_WRN("Replay detected: seq=%u last=%u", cmd->seq, last_bolus_seq);
        return BT_GATT_ERR(BT_ATT_ERR_WRITE_NOT_PERMITTED);
    }
    last_bolus_seq = cmd->seq;
    return len;
}
```

### 4. KNOB mitigation — enforce minimum entropy

```c
/* On the peripheral, reject pairing if the negotiated entropy is below 16 bytes. */
static void auth_cancel(struct bt_conn *conn) { /* ... */ }

static struct bt_conn_auth_cb auth_cb = {
    .cancel = auth_cancel,
    /* ... */
};

/* In your connection callback, check the security level after pairing: */
if (bt_conn_get_security(conn) < BT_SECURITY_L4) {
    bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
}
```

`BT_SECURITY_L4` forces LE Secure Connections with authenticated pairing — which also closes the KNOB window because the entropy negotiation is bound to the authenticated key exchange.

### 5. BLESA mitigation — re-authenticate on reconnect

```c
/* Zephyr: force re-pairing on every reconnect for bonded peers. */
static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) return;
    /* Do NOT trust the bond cache; require fresh authentication. */
    int rc = bt_conn_set_security(conn, BT_SECURITY_L4);
    if (rc) {
        LOG_ERR("Failed to re-authenticate: %d", rc);
        bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
    }
}
```

## Common Pitfalls & Gotchas

1. **Assuming "encrypted" means "authenticated."** LE Secure Connections with Just Works is encrypted but not MITM-protected. An attacker with a sniffer can still derive the key. For medical devices, always require passkey, numeric comparison, or OOB.
2. **Forgetting that the bond cache is attacker-controlled.** BLESA works because the stack trusts the IRK/address mapping after a reconnect. If your device accepts a connection from a bonded address without re-authenticating, you've handed the attacker a session.
3. **Testing only with your own phone.** Real attacks use a second controller (nRF52, HackRF, or a rooted Android with HCI snoop). If you only test with the iOS/Android stack, you'll miss the MITM and replay paths entirely.

## Try It Yourself

1. **Sniff your own device.** Flash the nRF Sniffer firmware to an nRF52840 dongle, pair your phone to a dev board running a custom GATT service, and capture the pairing exchange. Confirm in Wireshark whether the pairing was Just Works or passkey — and whether the LTK is derivable from the capture.
2. **Build a replay harness.** Write a Python script using `bleak` to connect to your peripheral, capture a write to a characteristic, disconnect, reconnect, and re-send the exact same bytes. Verify your firmware rejects it (or doesn't — that's the lesson).
3. **Force a downgrade.** On a test peripheral, temporarily disable LE Secure Connections and observe whether your central still pairs. Then re-enable it and confirm the central refuses to fall back to legacy pairing.

## Next up

Tomorrow: **Application-Layer Security for Medical Data on Top of BLE** — why link-layer encryption isn't enough for PHI, how to layer AES-GCM and signed payloads over GATT, and what FDA's premarket cybersecurity guidance actually expects from your characteristic design.
