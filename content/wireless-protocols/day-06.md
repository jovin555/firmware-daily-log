---
title: "Day 06: BLE Security: Pairing, Bonding & LE Secure Connections"
date: 2026-07-06
tags: ["til", "wireless-protocols", "ble-security", "pairing"]
---

## What I Explored Today

Today I dove into BLE security, specifically the pairing and bonding mechanisms that protect data in transit. If you've ever wondered why your BLE peripheral asks for a PIN or why some connections "just work" while others require a passkey entry, this is the layer that controls it. I focused on the two main security architectures: Legacy Pairing (used in Bluetooth 4.0/4.1) and LE Secure Connections (Bluetooth 4.2+), and how bonding stores long-term keys for reconnections. I also looked at the MITM (Man-in-the-Middle) protection options and the real-world implications of each.

## The Core Concept

BLE security isn't just about encrypting the radio link—it's about establishing trust between two devices that have never met. The pairing process is a three-phase handshake:

1. **Pairing Feature Exchange**: Both devices advertise their capabilities (I/O capabilities, whether they support Secure Connections, OOB data availability).
2. **Key Generation**: Based on the exchanged features, a Short Term Key (STK) or Long Term Key (LTK) is generated.
3. **Transport Specific Key Distribution**: The devices exchange identity keys, encryption keys, and other session keys.

The critical distinction is between **pairing** (a one-time session) and **bonding** (storing keys for future reconnections). Without bonding, every connection requires a full pairing exchange. With bonding, the devices can skip to encryption using the stored LTK.

LE Secure Connections (introduced in Bluetooth 4.2) replaced the vulnerable STK-based approach with Elliptic Curve Diffie-Hellman (ECDH) key exchange. This provides **passive eavesdropping protection** even if an attacker captures the pairing packets. Legacy Pairing, by contrast, is vulnerable to a passive eavesdropper capturing the TK (Temporary Key) if the IO capabilities allow it.

## Key Commands / Configuration / Code

### Zephyr RTOS: Enabling Secure Connections and Bonding

```c
// In prj.conf
CONFIG_BT_SMP=y                // Enable Security Manager Protocol
CONFIG_BT_SMP_SC_ONLY=y        // Force LE Secure Connections only
CONFIG_BT_BONDABLE=y           // Allow bonding (key storage)
CONFIG_BT_KEYS_OVERWRITE_OLDEST=y  // Manage key storage limits

// In main.c - Setting security requirements
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>

static struct bt_conn *default_conn;

static void security_changed(struct bt_conn *conn, bt_security_t level,
                             enum bt_security_err err) {
    if (err == BT_SECURITY_ERR_SUCCESS) {
        printk("Security level %d established\n", level);
        // Level 1: No security
        // Level 2: Unauthenticated pairing (no MITM)
        // Level 3: Authenticated pairing (MITM protected)
        // Level 4: LE Secure Connections, authenticated
    }
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .security_changed = security_changed,
};

// Request security level 4 (LE Secure Connections + MITM)
int err = bt_conn_set_security(default_conn, BT_SECURITY_L4);
if (err) {
    printk("Failed to set security: %d\n", err);
}
```

### Nordic nRF5 SDK: Pairing and Bonding Configuration

```c
// In sdk_config.h
#define NRF_SDH_BLE_VS_UUID_COUNT 10
#define NRF_SDH_BLE_SERVICE_CHANGED 1  // Enable Service Changed characteristic

// In main.c - Init pairing parameters
static void pairing_init(void) {
    ret_code_t err_code;
    
    // Security parameters
    ble_gap_sec_params_t sec_params;
    memset(&sec_params, 0, sizeof(sec_params));
    
    sec_params.bond        = 1;                    // Enable bonding
    sec_params.mitm        = 1;                    // Require MITM protection
    sec_params.lesc        = 1;                    // Use LE Secure Connections
    sec_params.keypress    = 0;                    // No keypress notifications
    sec_params.io_caps     = BLE_GAP_IO_CAPS_DISPLAY_ONLY;  // Peripheral has display
    sec_params.oob         = 0;                    // No out-of-band data
    sec_params.min_key_size = 7;                   // Minimum encryption key size
    sec_params.max_key_size = 16;                  // Maximum encryption key size
    
    // Set security parameters for the GAP
    err_code = sd_ble_gap_sec_params_reply(conn_handle, 
                                           BLE_GAP_SEC_STATUS_SUCCESS,
                                           &sec_params, NULL);
    APP_ERROR_CHECK(err_code);
}
```

### ESP-IDF: Handling Passkey Entry

```c
// In main.c - Passkey entry callback
static void esp_gap_cb(esp_ble_gap_cb_event_t event, 
                       esp_ble_gap_cb_param_t *param) {
    switch (event) {
        case ESP_GAP_BLE_PASSKEY_REQ_EVT:
            // Device requests user to enter passkey
            ESP_LOGI(TAG, "Passkey requested, enter on keyboard");
            // In real code, you'd get this from a UI
            uint32_t passkey = 123456;
            esp_ble_passkey_reply(param->passkey_req.bda, true, passkey);
            break;
            
        case ESP_GAP_BLE_NC_REQ_EVT:
            // Numeric Comparison for LE Secure Connections
            ESP_LOGI(TAG, "Numeric Comparison: %"PRIu32, 
                     param->ble_security.ble_req.key_notif.passkey);
            // User must confirm the number matches on both devices
            esp_ble_confirm_reply(param->ble_security.ble_req.bda, true);
            break;
    }
}
```

## Common Pitfalls & Gotchas

1. **IO Capabilities Mismatch**: If your peripheral has `DISPLAY_ONLY` but the central has `KEYBOARD_ONLY`, the pairing will fall back to `Just Works` (no MITM protection). Always check the IO capabilities matrix in the Bluetooth Core Spec. For a product that needs MITM, ensure at least one device can display a 6-digit number and the other can enter it.

2. **Bonding Database Corruption**: On resource-constrained MCUs, the bonding database is often stored in flash. If power is lost during a write, you can end up with a corrupted database that prevents all future connections. Always implement a checksum or use a flash-safe storage library (e.g., Zephyr's Settings subsystem with CRC).

3. **Key Size Mismatch**: The encryption key size negotiation happens during pairing. If one device requests a minimum key size of 16 bytes and the other only supports 7, pairing will fail. Most BLE stacks default to 16 bytes, but some legacy peripherals use 7. Always check `min_key_size` and `max_key_size` in your security parameters.

## Try It Yourself

1. **Test MITM Protection**: Configure your BLE peripheral with `DISPLAY_ONLY` IO capabilities and a central with `KEYBOARD_ONLY`. Pair them and verify that a 6-digit passkey is displayed on the peripheral and must be entered on the central. Then change the central to `DISPLAY_ONLY` and observe the fallback to `Just Works`.

2. **Bonding Persistence**: Write a simple application that bonds with a peer, then power-cycle the peripheral. Reconnect without re-pairing. Check the security callback—it should report level 3 or 4 without any user interaction. If it falls back to level 1, your bonding storage isn't persisting.

3. **LE Secure Connections vs Legacy**: In your BLE sniffer (e.g., Ellisys or Wireshark with a dongle), capture a pairing sequence with `CONFIG_BT_SMP_SC_ONLY=y` and one without. Compare the Pairing Request/Response packets—the Secure Connections version will include the ECDH public key exchange. Note the absence of the vulnerable TK in the SC version.

## Next Up

Tomorrow, we go down a layer: **IEEE 802.15.4: The Radio Layer Under Thread & Zigbee**. We'll look at the PHY and MAC layers that make mesh networking possible, including CSMA-CA, beacon-enabled vs. non-beacon modes, and how 802.15.4 handles 128-bit AES encryption at the frame level.
