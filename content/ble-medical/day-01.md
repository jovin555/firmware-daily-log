---
title: "Day 01: BLE Architecture: Controller, Host, HCI & the Protocol Stack"
date: 2026-10-11
tags: ["til", "ble-medical", "ble", "architecture"]
---

## What I Explored Today

I kicked off this series by mapping the BLE protocol stack onto the hardware and software boundaries that actually exist in a medical device. The mental model I keep coming back to: BLE is not one protocol, it's a split architecture where a small, real-time **Controller** handles radio timing and link-layer state, while a larger **Host** runs the profiles, GATT, and application logic. Between them sits the **HCI** (Host Controller Interface), which is the contract that lets you swap silicon vendors without rewriting your application. For a patient monitor or infusion pump, that separation matters because it determines where your real-time guarantees live, where your certification burden sits, and where you can actually debug when a connection drops mid-therapy.

## The Core Concept

The reason BLE is split at all is timing. The Link Layer must hop channels, respond to connection events within tight windows (a connection interval can be as short as 7.5 ms), and handle acknowledgement and encryption in hardware. That work is not something you want a general-purpose RTOS scheduler interfering with. So the Controller — a dedicated core or a hardware block — owns the PHY, Link Layer, and often the AES-128 CCM crypto engine.

The Host owns everything above the radio: L2CAP, ATT, GATT, GAP, SM (Security Manager), and your profiles. It's where you write code. The HCI is the seam. It's a command/event/data protocol that can run over UART (the classic H:4 transport), USB, or be entirely virtual when Host and Controller share one chip (a "SoC" or "combined" build).

The practical consequence: when you pick a module, you're really choosing *where the seam is*. An nRF52 running the SoftDevice is a combined build — no HCI on the wire, lower latency, but the Controller is a black box you configure through a vendor API. An nRF52 as a connectivity chip talking to an STM32 host over UART is a split build — you get full HCI control and portability, at the cost of a serial link that can bottleneck throughput and add latency.

For medical devices, this is a regulatory question too. If you use a pre-certified Controller module, much of the RF and Link Layer testing is already done. Your Host code is where your application-level risk analysis lives.

## Key Commands / Configuration / Code

The fastest way to see the split is to talk raw HCI. On Linux, `btmon` decodes the HCI stream live, and `btmgmt`/`hciconfig` drive the Controller directly.

```bash
# Watch the HCI command/event traffic between Host and Controller
sudo btmon

# In another shell, reset the controller and read its version
sudo hciconfig hci0 reset
sudo hcitool -i hci0 cmd 0x04 0x0001   # HCI_Read_Local_Version_Information
```

That `0x04 0x0001` is OGF 0x04 (Informational Parameters), OCF 0x0001. The Controller replies with an `HCI_Command_Complete` event carrying the HCI version, manufacturer ID, and LMP subversion — proof the seam is real and observable.

On an embedded split build, the same exchange looks like this over UART:

```c
// H:4 transport: 0x01 = HCI Command packet type
// OGF 0x08 (LE Controller), OCF 0x0001 (LE_Set_Event_Mask)
uint8_t cmd[] = {
    0x01,             // H4: HCI Command
    0x01, 0x20,       // OpCode 0x2001, little-endian (OCF=0x0001, OGF=0x08)
    0x08,             // Parameter total length
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x3F  // event mask
};
uart_write(cmd, sizeof(cmd));
```

A combined build hides all of this. With the Nordic SoftDevice you'd instead call:

```c
// No HCI on the wire — the SoftDevice API is the seam
ble_gap_conn_params_t params = {
    .min_conn_interval = MSEC_TO_UNITS(15, UNIT_1_25_MS),  // 15 ms
    .max_conn_interval = MSEC_TO_UNITS(30, UNIT_1_25_MS),  // 30 ms
    .slave_latency     = 0,
    .conn_sup_timeout  = MSEC_TO_UNITS(4000, UNIT_10_MS)   // 4 s
};
sd_ble_gap_ppcp_set(&params);
```

Note the units: connection intervals are in 1.25 ms ticks, supervision timeout in 10 ms ticks. Getting these wrong is the single most common source of "it connects then drops."

## Common Pitfalls & Gotchas

**1. Assuming the HCI is transparent.** In split builds, the UART link between Host and Controller has finite bandwidth. If you push large GATT notifications, the HCI ACL data flow can saturate and add latency. Budget your UART baud rate against your throughput, not the other way around.

**2. Confusing GAP roles with Link Layer roles.** GAP "central/peripheral" is a Host concept. The Link Layer sees "master/slave." They usually map 1:1, but the terminology mismatch causes real confusion when reading Controller-level traces in `btmon`.

**3. Treating the Controller as stateless.** It holds connection state, the resolving list, bonding keys, and the whitelist. A Controller reset (`HCI_Reset`) wipes all of it. In a medical device, an unexpected Controller reset means re-establishing bonds — plan for that in your state machine.

## Try It Yourself

1. **Observe the seam.** On a Linux box with a USB BLE dongle, run `sudo btmon` in one terminal and `bluetoothctl` in another. Pair a device and identify the exact HCI commands for `LE_Create_Connection` and the `LE_Connection_Complete` event.

2. **Read your Controller.** Issue `HCI_Read_Local_Version_Information` (OGF 0x04, OCF 0x0001) and decode the response. Note the HCI version and manufacturer — this tells you which spec features you can rely on.

3. **Map your stack.** Take a BLE module you have on the bench and determine whether it's a combined or split build. If split, find the HCI transport (UART pins, baud rate) in the datasheet and confirm it in a logic analyzer capture.

## Next Up

Tomorrow: **BLE Physical Layer: 2.4 GHz Channels & the 1M, 2M and Coded PHYs** — why BLE advertises on three channels, how the 2M PHY doubles throughput, and when Coded PHY's range extension is worth the data-rate hit for a body-worn sensor.
