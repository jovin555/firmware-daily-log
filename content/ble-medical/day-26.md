---
title: "Day 26: Reliable Data Transfer: Buffering, Reconnection & Data Integrity"
date: 2026-11-05
tags: ["til", "ble-medical", "reliability", "reconnection"]
---

# Day 26: Reliable Data Transfer: Buffering, Reconnection & Data Integrity

## What I Explored Today

Today I dug into the unglamorous but critical side of BLE medical devices: what happens when the link drops mid-transmission, when the phone's GATT stack can't keep up with a 1 Hz ECG stream, or when a notification arrives out of order. BLE's link layer gives you CRC per packet and retransmission at the link layer, but that guarantees nothing about *application-level* delivery — a notification that was never ACKed at the ATT layer is simply lost, and a disconnect can strand data in a peripheral's buffer. I spent the day wiring up a ring buffer on the peripheral, a sequence-number + CRC scheme on the characteristic payload, and a reconnection state machine that flushes buffered samples once the central re-subscribes. This is the difference between a demo and a device that survives a patient walking out of range for 30 seconds.

## The Core Concept

BLE gives you three layers of "reliability," and it's easy to conflate them:

1. **Link layer**: every PDU has a 24-bit CRC and is retransmitted until ACKed or the supervision timeout fires. This protects a single packet *while connected*.
2. **ATT layer**: notifications are fire-and-forget — there is no ACK. Indications *are* ACKed, but at one-at-a-time throughput, which is too slow for streaming vitals.
3. **Application layer**: entirely your responsibility.

The gap that bites medical devices is between (1) and (3). If the supervision timeout (up to 32 s, negotiated via `connSupervisionTimeout`) expires, the link drops. Anything the peripheral queued in its notification buffer is gone unless *you* persisted it. And even while connected, if the central's ATT stack is busy, the peripheral's TX queue fills and `sd_ble_gatts_hvx()` returns `BLE_ERROR_NO_TX_BUFFERS` — you must handle that or silently drop samples.

The pattern that works: **decouple acquisition from transmission**. Sample into a ring buffer at a fixed rate. Drain the ring buffer into notifications only when the stack accepts them. Tag every payload with a monotonically increasing sequence number and a CRC so the central can detect gaps and corruption. On reconnect, the central reads a "last received sequence" from a status characteristic, and the peripheral replays from the ring buffer. This turns BLE's best-effort notifications into an application-level reliable stream.

## Key Commands / Configuration / Code

**1. Ring buffer with overflow accounting (peripheral, C):**

```c
#define RING_CAP 512  // ~8.5 min of 1 Hz samples, 4 bytes each
typedef struct { uint32_t seq; int16_t ecg; uint16_t crc; } sample_t;

static sample_t ring[RING_CAP];
static volatile uint32_t head, tail;  // head=write, tail=read
static volatile uint32_t dropped;     // overflow counter, exposed via status char

// Called from timer ISR at 1 Hz — never blocks
void acquire_sample(int16_t ecg) {
    uint32_t next = (head + 1) % RING_CAP;
    if (next == tail) { dropped++; return; }  // full: drop newest, count it
    ring[head].seq = head;  // seq == ring index for simplicity here
    ring[head].ecg = ecg;
    ring[head].crc = crc16((uint8_t*)&ring[head], 6);
    head = next;
}
```

**2. Draining to notifications, respecting TX buffer limits (nRF5 SDK):**

```c
void drain_ring(void) {
    while (tail != head) {
        uint16_t len = sizeof(sample_t);
        uint32_t err = sd_ble_gatts_hvx(m_conn_handle, &(ble_gatts_hvx_params_t){
            .handle = m_ecg_char_handle,
            .type   = BLE_GATT_HVX_NOTIFICATION,
            .offset = 0,
            .p_len  = &len,
            .p_data = (uint8_t*)&ring[tail],
        });
        if (err == NRF_ERROR_RESOURCES) return;  // TX queue full — retry on BLE_GATTS_EVT_HVN_TX_COMPLETE
        if (err != NRF_SUCCESS) return;          // disconnected etc.
        tail = (tail + 1) % RING_CAP;
    }
}
```

**3. Reconnection + replay (central side, pseudo-code):**

```c
// On reconnect, before re-enabling notifications:
uint32_t last_seq = read_status_char();  // peripheral exposes last_acked_seq
write_control_char(CMD_REPLAY_FROM, last_seq + 1);
// Peripheral then streams from ring[last_seq+1] forward, then live samples.
// Central verifies: seq == expected_seq++ and crc16(payload) == payload.crc
// Any gap -> log a "data loss" event; any CRC fail -> request replay of that seq.
```

**4. Connection parameters that survive a walk-away (peripheral):**

```c
// Longer supervision timeout tolerates brief obstructions without dropping
#define MIN_CONN_INTERVAL  MSEC_TO_UNITS(15, UNIT_1_25_MS)   // 15 ms
#define MAX_CONN_INTERVAL  MSEC_TO_UNITS(30, UNIT_1_25_MS)   // 30 ms
#define SLAVE_LATENCY      0
#define CONN_SUP_TIMEOUT   MSEC_TO_UNITS(6000, UNIT_10_MS)   // 6 s, well under 32 s max
```

## Common Pitfalls & Gotchas

- **Assuming notifications are reliable.** They aren't. If `sd_ble_gatts_hvx()` returns `NRF_ERROR_RESOURCES`, the sample was *not* sent — if you don't buffer it, it's gone. Always check the return code and retry on `BLE_GATTS_EVT_HVN_TX_COMPLETE`.
- **Ignoring the ATT MTU.** A default MTU of 23 gives you 20 bytes of payload. If your `sample_t` grows past that, `hvx` returns `BLE_ERROR_DATA_SIZE`. Negotiate MTU (up to 247 on most modern stacks) or split payloads — but never assume the central accepted your request.
- **Replaying without a sequence number.** If the central can't tell that seq 100→102 skipped 101, it will happily plot a corrupted ECG. The CRC catches bit errors; the sequence number catches *gaps*. You need both.

## Try It Yourself

1. **Force an overflow.** Set `RING_CAP` to 8, run acquisition at 10 Hz, and pause the drain loop for 2 seconds. Confirm `dropped` increments and that the central sees a sequence gap — then verify your replay logic recovers the missing samples.
2. **Simulate a disconnect.** Pull the peripheral out of range for 10 s while streaming, then reconnect. Check that the central's `last_acked_seq` matches the peripheral's replay start, and that no samples are duplicated or lost.
3. **Corrupt a payload.** In your central's receive path, flip one bit in a received `sample_t` before CRC checking. Confirm the CRC rejects it and your code requests a replay of that sequence number rather than plotting garbage.

## Next Up

Tomorrow: **Testing & Debugging BLE: nRF Sniffer, Wireshark & nRF Connect** — how to actually *see* the packets you've been reasoning about all week, capture a connection interval negotiation, and diagnose a failed notification with a sniffer trace instead of guesswork.
