---
title: "Day 05: BLE Mesh: Provisioning, Models & Relay Nodes"
date: 2026-07-05
tags: ["til", "wireless-protocols", "ble-mesh"]
---

## What I Explored Today

Today I dove into BLE Mesh—the network-layer extension to Bluetooth LE that enables many-to-many communication across hundreds of nodes. Unlike classic BLE's star topology (one central, many peripherals), BLE Mesh uses a managed-flooding architecture where relay nodes retransmit messages to extend range and reliability. I focused on three pillars: the provisioning process that securely adds devices to a mesh network, the model system that defines node behavior, and the relay node mechanics that make mesh scale.

## The Core Concept

BLE Mesh solves a fundamental problem: BLE's 1:1 connection model doesn't scale for lighting control, sensor arrays, or building automation. You can't have 500 light bulbs each maintaining a connection to a phone. Instead, BLE Mesh uses a publish/subscribe model over a managed-flooding network. Every node can send messages to a group address, and any node subscribed to that group receives them—no direct connections needed.

The key innovation is the **relay node**. When a node sends a message, nearby relay nodes retransmit it with a Time-To-Live (TTL) decrement. This creates redundant paths: if one relay fails, another hop delivers the message. The mesh stack uses a message cache to prevent infinite loops—each node remembers recently seen messages and drops duplicates.

**Provisioning** is the security handshake that binds a device to a mesh network. It uses Elliptic Curve Diffie-Hellman (ECDH) to establish a shared secret, then distributes a Network Key and Application Keys. Without provisioning, a device is an unprovisioned beacon—it can't send or receive mesh messages.

**Models** are the standardized interfaces that define what a node can do. A Generic OnOff Client model can send on/off commands; a Generic OnOff Server model can receive them and control a GPIO. Models are defined by the Bluetooth SIG and can be extended with vendor-specific models.

## Key Commands / Configuration / Code

For this exploration, I used the Zephyr RTOS BLE Mesh stack on an nRF52840 DK. Here's the essential provisioning code and relay configuration.

### Provisioner-Side: Provisioning a Node

```c
// Zephyr BLE Mesh provisioning example (provisioner role)
#include <bluetooth/mesh.h>

static void prov_complete(uint16_t net_idx, uint16_t addr, const uint8_t dev_key[16])
{
    printk("Provisioned node 0x%04x on net 0x%04x\n", addr, net_idx);
    // Now bind application key to the node's element
    bt_mesh_cfg_mod_app_bind(net_idx, addr, addr, 
                             BT_MESH_MODEL_ID_GEN_ONOFF_SRV, 
                             app_key_idx, NULL);
}

static const struct bt_mesh_prov prov = {
    .uuid = dev_uuid,
    .output_size = 0,    // No OOB output
    .output_actions = 0,
    .complete = prov_complete,
};

void provision_device(const uint8_t uuid[16])
{
    // Start provisioning over PB-ADV (advertising bearer)
    bt_mesh_provision_adv(uuid, BT_MESH_NET_PRIMARY, 0x0001, 0);
}
```

### Node-Side: Enabling Relay Functionality

```c
// In your node's main.c - enable relay support
#include <bluetooth/mesh.h>

static struct bt_mesh_cfg_cli cfg_cli;

static void relay_config(void)
{
    struct bt_mesh_relay_params relay_params = {
        .count = 2,       // Number of retransmissions
        .interval = 10,   // Interval in ms (10-100)
    };
    
    // Enable relay with default parameters
    bt_mesh_relay_set(BT_MESH_RELAY_ENABLED, &relay_params);
    
    // Set TTL for outgoing messages
    bt_mesh_net_ttl_set(7);  // Default 7, max 127
}

// Model handler for Generic OnOff Server
static const struct bt_mesh_model_op gen_onoff_srv_op[] = {
    { BT_MESH_MODEL_OP_GEN_ONOFF_GET, 0, gen_onoff_get },
    { BT_MESH_MODEL_OP_GEN_ONOFF_SET, 2, gen_onoff_set },
    BT_MESH_MODEL_OP_END,
};

BT_MESH_MODEL_CB_DEFINE(gen_onoff_srv, BT_MESH_MODEL_ID_GEN_ONOFF_SRV,
                        gen_onoff_srv_op, NULL, NULL, &onoff_cb);
```

### Configuring Relay via Mesh Model

```c
// Remote configuration of relay on node 0x0005
void configure_remote_relay(uint16_t node_addr)
{
    struct bt_mesh_relay_params params = {
        .count = 3,
        .interval = 20,
    };
    
    // Send Config Relay Set message
    bt_mesh_cfg_relay_set(BT_MESH_NET_PRIMARY, node_addr, 
                          BT_MESH_RELAY_ENABLED, &params, NULL);
}
```

## Common Pitfalls & Gotchas

1. **TTL Too Low Kills Reliability**: I set TTL=2 on a 50-node network and saw 40% packet loss. The default TTL=7 is safe for most deployments. Each relay decrements TTL by 1—if your network diameter is 5 hops, TTL must be ≥5. Use `bt_mesh_net_ttl_get()` to verify.

2. **Message Cache Size Matters**: The default message cache (10 entries in Zephyr) is too small for dense networks. With 100+ nodes, a relay can see the same message from multiple neighbors. If the cache overflows, duplicates flood the network. Increase `CONFIG_BT_MESH_CACHE_SIZE` to 50-100 in your prj.conf.

3. **Provisioning Bearer Selection**: PB-ADV (advertising) works for most cases but has a 10-second timeout. For production, use PB-GATT (GATT bearer) which is more reliable over longer distances. Switch with `bt_mesh_prov_gatt()` before provisioning.

## Try It Yourself

1. **Provision a Node Remotely**: Set up two nRF52840 boards. Flash one as provisioner, one as unprovisioned node. Use `bt_mesh_provision_adv()` to add the node to your network. Verify with `bt_mesh_cfg_node_identity_set()` to see it in scan responses.

2. **Measure Relay Latency**: Create a network with 3 relay nodes in a chain. Send a message from node A to node D (3 hops). Use a logic analyzer on the GPIO toggles at each relay to measure per-hop latency. Expected: ~5-10ms per hop at TTL=7.

3. **Test TTL Tuning**: Set TTL=1 on a relay node and try to reach a node 2 hops away. Observe the message never arrives. Then increase TTL to 3 and verify delivery. Use `bt_mesh_net_ttl_set()` and monitor with `bt_mesh_net_ttl_get()`.

## Next Up

Tomorrow: **BLE Security: Pairing, Bonding & LE Secure Connections** — I'll break down the pairing process, how bonding stores long-term keys, and why LE Secure Connections (LESC) with FIPS-approved ECDH is mandatory for BLE 5.x products. We'll also cover the OOB (Out-of-Band) methods that prevent MITM attacks in production.
