---
title: "Day 18: OTA Over BLE: GATT-Based DFU & Throughput Constraints"
date: 2026-07-18
tags: ["til", "secure-ota", "ble-dfu"]
---

## What I Explored Today

Today I went deep into BLE-based Device Firmware Update (DFU) using the GATT protocol stack. I focused on the practical throughput bottlenecks when pushing a 512 KB firmware image over a BLE connection, and how to structure a GATT service for reliable, resume-capable updates. I tested this on an nRF52840 DK using Zephyr’s MCUboot and the Nordic DFU service, measuring actual throughput against the theoretical 1.3 Mbps BLE 5.0 PHY limit.

## The Core Concept

BLE DFU works by exposing a custom GATT service with characteristic handles for control, data, and status. The fundamental constraint is not the radio PHY rate—it’s the connection interval, MTU size, and application-layer acknowledgment overhead. A typical BLE connection uses a 7.5 ms connection interval with an MTU of 23 bytes (default). Even with Data Length Extension (DLE) pushing the MTU to 251 bytes, you’re still limited by how many packets you can send per connection event.

The real bottleneck is the GATT write-without-response vs. write-with-response trade-off. Write-without-response gives higher throughput but zero reliability—if a packet drops, the entire image is corrupted. Write-with-response adds a round-trip per packet, halving your effective throughput. The practical solution is to use a credit-based flow control mechanism: send N packets without response, then wait for a cumulative ACK. This is exactly how Nordic’s Secure DFU service works, and it’s the pattern you should replicate.

## Key Commands / Configuration / Code

Below is a minimal GATT DFU service definition using Zephyr’s BT GATT API. This defines the control point and data transfer characteristics.

```c
// dfu_service.c - GATT DFU Service for Zephyr
#include <zephyr/bluetooth/gatt.h>

// DFU Service UUID: 00001530-1212-EFDE-1523-785FEABCD123
#define BT_UUID_DFU_SERVICE_VAL \
    BT_UUID_128_ENCODE(0x00001530, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123)

// Control Point UUID: 00001531-1212-EFDE-1523-785FEABCD123
#define BT_UUID_DFU_CTRL_PT_VAL \
    BT_UUID_128_ENCODE(0x00001531, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123)

// Data Transfer UUID: 00001532-1212-EFDE-1523-785FEABCD123
#define BT_UUID_DFU_DATA_VAL \
    BT_UUID_128_ENCODE(0x00001532, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123)

static struct bt_gatt_attr dfu_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_128(BT_UUID_DFU_SERVICE_VAL)),
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(BT_UUID_DFU_CTRL_PT_VAL),
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                           BT_GATT_PERM_WRITE,
                           NULL, dfu_ctrl_pt_write, NULL),
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(BT_UUID_DFU_DATA_VAL),
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                           BT_GATT_PERM_WRITE,
                           NULL, dfu_data_write, NULL),
};

// Callback: handle control point writes (start, suspend, resume, abort)
static ssize_t dfu_ctrl_pt_write(struct bt_conn *conn,
                                 const struct bt_gatt_attr *attr,
                                 const void *buf, uint16_t len,
                                 uint16_t offset, uint8_t flags)
{
    const uint8_t *cmd = (const uint8_t *)buf;
    if (len < 1) return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);

    switch (cmd[0]) {
    case 0x01: // START_DFU
        // Validate image header, prepare flash area
        break;
    case 0x02: // RECEIVE_INIT
        // Expect init packet (hash, size, version)
        break;
    case 0x03: // ABORT
        // Clean up, reset state
        break;
    }
    return len;
}

// Callback: receive firmware data chunks
static ssize_t dfu_data_write(struct bt_conn *conn,
                              const struct bt_gatt_attr *attr,
                              const void *buf, uint16_t len,
                              uint16_t offset, uint8_t flags)
{
    // Write chunk to flash at current offset
    // Update CRC32 accumulator
    // If len < MTU, signal end of image
    return len;
}
```

To maximize throughput, configure the connection parameters aggressively:

```c
// In your application init, request optimal BLE params
struct bt_le_conn_param *conn_params = BT_LE_CONN_PARAM(
    6,    // min interval: 7.5 ms (6 * 1.25 ms)
    6,    // max interval: 7.5 ms
    0,    // latency: 0
    400   // supervision timeout: 4 s
);
bt_conn_le_param_update(conn, conn_params);

// Request Data Length Extension (MTU up to 251 bytes)
bt_le_set_data_len(conn, BT_BUF_RX_SIZE, BT_BUF_RX_SIZE);
```

On the client side (smartphone or gateway), use Nordic’s `nrf-ble-dfu` library or implement your own GATT client that sends packets in bursts:

```python
# Python example using bleak (BLE library)
import asyncio
from bleak import BleakClient

DFU_SERVICE_UUID = "00001530-1212-efde-1523-785feabcd123"
DFU_CTRL_UUID = "00001531-1212-efde-1523-785feabcd123"
DFU_DATA_UUID = "00001532-1212-efde-1523-785feabcd123"

async def send_firmware(client, firmware_bytes, mtu=247):
    # Step 1: Send start command
    await client.write_gatt_char(DFU_CTRL_UUID, b'\x01', response=True)

    # Step 2: Send init packet (hash + metadata)
    init_packet = create_init_packet(firmware_bytes)
    await client.write_gatt_char(DFU_DATA_UUID, init_packet, response=True)

    # Step 3: Send data in bursts of 10 packets without response
    burst_size = 10
    for i in range(0, len(firmware_bytes), mtu * burst_size):
        chunk = firmware_bytes[i:i + mtu * burst_size]
        await client.write_gatt_char(DFU_DATA_UUID, chunk, response=False)
        # Wait for cumulative ACK from device (poll status characteristic)
        await asyncio.sleep(0.01)  # Small delay to let device process
```

## Common Pitfalls & Gotchas

**1. Connection interval mismatch kills throughput.** If your peripheral requests a 7.5 ms interval but the central (phone) only supports 30 ms, you’ll get 1/4 the throughput. Always negotiate parameters after connection, and log the actual interval. On iOS, the minimum connection interval is 15 ms (12 * 1.25 ms) unless you’re in the Apple MFI program.

**2. Flash write latency causes buffer overruns.** Writing to internal flash takes 2-5 ms per page (4 KB on nRF52). If the BLE stack receives packets during a write, the RX buffer overflows and packets are dropped. Solution: use a double-buffer approach—fill one buffer while writing the other to flash, or pause the BLE RX during flash operations using `bt_conn_pause()`.

**3. Ignoring the init packet validation.** Many engineers skip the init packet (containing firmware hash, size, and version) and just stream raw binary. This is dangerous: a partial or corrupted transfer leaves the device in an unbootable state. Always validate the init packet before accepting any data, and use the hash to verify the complete image before swapping to the new slot.

## Try It Yourself

1. **Measure your baseline throughput.** Set up a BLE peripheral with the DFU service above and a central that sends 100 KB of dummy data. Log the actual time and calculate throughput. Then increase the MTU to 247 bytes and re-measure. Compare the difference.

2. **Implement burst-mode flow control.** Modify the peripheral to accept up to 10 write-without-response packets before requiring a cumulative ACK. On the central, send bursts of 10 packets and wait for the ACK. Measure throughput vs. single-packet write-with-response.

3. **Add resume support.** Implement a control point command that reports the last successfully written offset. On the central, if the connection drops mid-transfer, reconnect, query the offset, and resume from that point instead of restarting. This is critical for large images over unreliable BLE links.

## Next Up

Tomorrow: **Day 19: OTA Over Cellular: NB-IoT/LTE-M Bandwidth & Cost Considerations**. We’ll dive into the constraints of cellular IoT networks—narrowband vs. LTE-M data rates, power consumption trade-offs, and how to design a firmware update protocol that doesn’t bankrupt you on data charges.
