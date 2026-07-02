---
title: "Day 20: OpenThread: 802.15.4 & Thread Network"
date: 2026-07-02
tags: ["til", "zephyr", "openthread", "thread"]
---

## What I Explored Today

Today I dove into Zephyr's integration of OpenThread — Google's open-source implementation of the Thread networking protocol. Thread is a low-power, mesh-networking standard built on IEEE 802.15.4 radios (typically 2.4 GHz). Unlike simple point-to-point or star-topology 802.15.4 stacks, Thread creates a self-healing, IPv6-based mesh where every node can route traffic. I built a minimal Thread network with a Leader (the coordinator equivalent) and a Router node, verified commissioning, and tested end-to-end UDP communication. The experience confirmed that Thread is far more than just "Zigbee with IPv6" — it's a production-grade mesh for IoT.

## The Core Concept

Why Thread instead of raw 802.15.4 or BLE mesh? The answer is **deterministic routing and IP convergence**.

Raw 802.15.4 gives you a radio link, but you own the entire network stack — addressing, retransmission, routing, security. That's a lot of wheel-reinventing. BLE mesh works, but it's a managed flood network: every message propagates to every node, which kills scalability and predictability.

Thread solves this with a **distance-vector routing protocol** (based on the IETF RPL standard). Nodes organize into a tree-like Directed Acyclic Graph (DAG) rooted at the Leader. Each Router node maintains a routing table and forwards packets toward the destination. The result: messages take the shortest path, not a broadcast flood. Thread also natively supports IPv6, so you can use familiar sockets, CoAP, or MQTT-SN on top. For an embedded engineer, this means you get a mesh that's debuggable with `ping`, addressable with global IPv6 prefixes, and secure by default (AES-128-CCM encryption, network key commissioning).

## Key Commands / Configuration / Code

### 1. Enabling OpenThread in Zephyr

In your board's `prj.conf`:

```kconfig
# Enable OpenThread stack
CONFIG_OPENTHREAD=y
CONFIG_OPENTHREAD_NORDIC_LIBRARY=y

# Thread device role: full Thread device (router-capable)
CONFIG_OPENTHREAD_THREAD_VERSION_1_3=y
CONFIG_OPENTHREAD_MTD=n          # Minimal Thread Device (sleepy end device)
CONFIG_OPENTHREAD_FTD=y          # Full Thread Device

# Network stack
CONFIG_NETWORKING=y
CONFIG_NET_IPV6=y
CONFIG_NET_IPV6_NBR_CACHE=y
CONFIG_NET_IPV6_MLD=y

# Shell for debugging
CONFIG_OPENTHREAD_SHELL=y
CONFIG_SHELL=y
```

### 2. Initializing the Thread Interface

In your application code, you must start the Thread interface after the Zephyr networking subsystem is ready:

```c
#include <zephyr/kernel.h>
#include <zephyr/net/openthread.h>
#include <openthread/thread.h>
#include <openthread/dataset.h>

static void ot_state_changed_callback(uint32_t flags, void *context)
{
    if (flags & OT_CHANGED_THREAD_ROLE) {
        otDeviceRole role = otThreadGetDeviceRole(context);
        switch (role) {
        case OT_DEVICE_ROLE_DISABLED:
            printk("Role: Disabled\n");
            break;
        case OT_DEVICE_ROLE_DETACHED:
            printk("Role: Detached\n");
            break;
        case OT_DEVICE_ROLE_CHILD:
            printk("Role: Child (end device)\n");
            break;
        case OT_DEVICE_ROLE_ROUTER:
            printk("Role: Router\n");
            break;
        case OT_DEVICE_ROLE_LEADER:
            printk("Role: Leader\n");
            break;
        }
    }
}

void main(void)
{
    otInstance *ot = openthread_get_default_instance();
    if (!ot) {
        printk("Failed to get OpenThread instance\n");
        return;
    }

    otSetStateChangedCallback(ot, ot_state_changed_callback, ot);

    /* Start Thread interface with default dataset */
    otError error = otThreadSetEnabled(ot, true);
    if (error != OT_ERROR_NONE) {
        printk("Failed to enable Thread: %d\n", error);
    }
}
```

### 3. Commissioning via OpenThread Shell

After flashing, connect via serial and use the OpenThread shell:

```
# On the first device (will become Leader):
uart:~$ ot dataset init new
uart:~$ ot dataset commit active
uart:~$ ot ifconfig up
uart:~$ ot thread start
# Wait ~30 seconds, then check:
uart:~$ ot state
leader

# Get the network key and PAN ID for other devices:
uart:~$ ot dataset
Active Dataset: 0xdeadbeef...
PAN ID: 0x1234
Network Key: 00112233445566778899aabbccddeeff

# On a second device, use the same dataset:
uart:~$ ot dataset panid 0x1234
uart:~$ ot dataset networkkey 00112233445566778899aabbccddeeff
uart:~$ ot dataset commit active
uart:~$ ot ifconfig up
uart:~$ ot thread start
# After joining:
uart:~$ ot state
router
```

### 4. Testing UDP Communication

Once both devices are on the network, use the shell to send a UDP message:

```
# On device A (Leader), get its IPv6 address:
uart:~$ ot ipaddr
fdde:ad00:beef:0:0:ff:fe00:fc00

# On device B, send a UDP packet:
uart:~$ ot udp send fdde:ad00:beef:0:0:ff:fe00:fc00 1234 hello
# On device A, listen:
uart:~$ ot udp open
uart:~$ ot udp bind :: 1234
# You should see: "6 bytes from fdde:ad00:beef:0:...:1234"
```

## Common Pitfalls & Gotchas

1. **Radio coexistence with BLE**: Many nRF52840-based boards share the 2.4 GHz radio between BLE and 802.15.4. If you enable both, you must use Zephyr's radio arbiter (`CONFIG_MPSL=y`). Without it, the radio will glitch and Thread will fail to form a network. Symptoms: `ot state` cycles between `detached` and `child` without ever becoming a router.

2. **Dataset mismatch**: The Thread network key, PAN ID, and channel must match exactly on all devices. A common mistake is forgetting `ot dataset commit active` after setting parameters. The dataset is not persistent until committed. Use `ot dataset` to verify before starting the interface.

3. **Router selection timeout**: A new device will initially join as a Child (end device). It only becomes a Router after the Leader grants it router status, which can take 2-5 minutes. Don't panic if `ot state` shows `child` for a while. If it never transitions, check that `CONFIG_OPENTHREAD_FTD=y` is set.

## Try It Yourself

1. **Build a three-node Thread network**: Flash three nRF52840 DKs with the OpenThread shell sample (`samples/net/openthread`). Commission all three with the same dataset. Verify that one becomes Leader, one Router, and one Child. Use `ot neighbors` to see the mesh topology.

2. **Measure mesh latency**: Write a small application that sends a UDP ping from a Child to the Leader every second. Use `ot ping <ipv6-addr>` from the shell to measure round-trip time. Then add a fourth node and observe how routes adapt.

3. **Implement a CoAP server**: Enable `CONFIG_OPENTHREAD_COAP=y` and write a simple CoAP resource that returns sensor data. Use `libcoap` or the Zephyr CoAP API on a Linux host to query the Thread node via its IPv6 address.

## Next Up

Tomorrow, we leave the 2.4 GHz band and move to cellular IoT. I'll explore **LTE-M and NB-IoT with the nRF9160** — Zephyr's modem subsystem, AT command handling, and how to send data to the cloud using the MQTT-over-PPP stack. Bring your SIM card.
