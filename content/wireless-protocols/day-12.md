---
title: "Day 12: LoRaWAN Architecture: End Devices, Gateways & Network Servers"
date: 2026-07-12
tags: ["til", "wireless-protocols", "lorawan"]
---

## What I Explored Today

Today I dug into the three-tier architecture that makes LoRaWAN work at scale: end devices (the sensors/actuators), gateways (the packet forwarders), and network servers (the brains of the operation). While the physical layer (LoRa) handles the chirp-spread-spectrum modulation, the MAC layer (LoRaWAN) defines how these three components negotiate uplinks, downlinks, security, and data rates. I spent the morning tracing packets from an STM32WL-based end device through a Kerlink iBTS gateway to The Things Network (TTN) v3 network server, and the afternoon reading the LoRaWAN 1.0.4 specification sections on join procedures and message routing.

## The Core Concept

Why three tiers? Because LoRaWAN decouples the radio path from the network logic. An end device transmits a packet; every gateway within range receives it and forwards the raw radio metadata (RSSI, SNR, timestamp, frequency, spreading factor) to the network server. The network server deduplicates these multiple receptions, selects the best gateway for a downlink, and handles all application-layer processing. This means a single end device can be heard by dozens of gateways, and the network server decides which one replies—enabling seamless roaming and spatial diversity without the end device knowing or caring which gateway is listening.

The critical insight: gateways are dumb pipes. They do not store sessions, decrypt payloads, or make routing decisions. They simply take a LoRa radio packet, wrap it in a UDP packet (using the Semtech Packet Forwarder protocol), and shoot it to the network server. This keeps gateway hardware cheap and stateless, while the network server scales horizontally.

## Key Commands / Configuration / Code

### 1. Gateway Packet Forwarder Configuration (global_conf.json)

This is the file that tells a gateway which network servers to talk to. Here’s a real snippet from a Kerlink iBTS running the Semtech UDP Packet Forwarder v2.0.0:

```json
{
  "SX1301_conf": {
    "lorawan_public": true,
    "clksrc": 0,
    "radio_0": {
      "freq": 868500000,
      "rssi_offset": -166.0,
      "tx_enable": true
    },
    "radio_1": {
      "freq": 868500000,
      "rssi_offset": -166.0,
      "tx_enable": false
    }
  },
  "gateway_conf": {
    "gateway_ID": "B827EBFFFE123456",
    "server_address": "eu1.cloud.thethings.network",
    "serv_port_up": 1700,
    "serv_port_down": 1700,
    "keepalive_interval": 10,
    "stat_interval": 30,
    "push_timeout_ms": 100,
    "forward_crc_valid": true,
    "forward_crc_error": false,
    "forward_crc_disabled": false
  }
}
```

**Key fields:**
- `gateway_ID`: 64-bit EUI derived from the gateway’s MAC address. Must be unique.
- `server_address`: The network server’s hostname or IP. For TTN v3, use the cluster endpoint.
- `serv_port_up/down`: UDP port 1700 is the Semtech standard.
- `forward_crc_valid`: Only forward packets that passed CRC check—reduces noise.

### 2. End Device Join Request (OTAA)

When an end device joins over-the-air (OTAA), it sends a join request. Here’s what that looks like in C using the LoRaMac-node stack on an STM32WL:

```c
// From LoRaMac-node/src/mac/LoRaMac.c
// JoinReq payload: AppEUI (8) | DevEUI (8) | DevNonce (2)
// DevNonce is a random 2-byte value, never reused

LoRaMacStatus_t LoRaMacMlmeJoinReq( LoRaMacJoinReq_t *joinReq )
{
    // Validate parameters
    if( ( joinReq->AppEui == NULL ) || ( joinReq->DevEui == NULL ) ||
        ( joinReq->DevNonce == NULL ) )
    {
        return LORAMAC_STATUS_PARAMETER_ERROR;
    }

    // Set the MAC layer into join mode
    MacCtx.McpsIndication = McpsIndication;
    MacCtx.MlmeIndication = MlmeIndication;

    // Generate random DevNonce (must be fresh per join attempt)
    joinReq->DevNonce[0] = ( uint8_t )( rand() % 256 );
    joinReq->DevNonce[1] = ( uint8_t )( rand() % 256 );

    // Build and send the JoinReq message
    return SendJoinReq( joinReq );
}
```

**Critical detail:** The DevNonce must never repeat. The network server tracks used DevNonces per DevEUI; a replay triggers a rejection. On constrained devices, use a hardware RNG or a persistent counter.

### 3. Network Server Downlink Selection Logic (Python pseudocode)

The network server’s job is to pick the best gateway for a downlink. Here’s the simplified logic from ChirpStack (open-source network server):

```python
def select_downlink_gateway(uplink_metadata_list):
    """
    Given a list of gateway metadata for the same uplink,
    pick the gateway with the best RSSI that also supports
    the required downlink frequency and data rate.
    """
    candidates = []
    for gw in uplink_metadata_list:
        # Gateways must have TX enabled on the target frequency
        if gw.tx_freq == uplink_metadata_list[0].rx_freq:
            candidates.append(gw)

    if not candidates:
        raise NoSuitableGateway("No gateway can TX on that frequency")

    # Pick the one with highest RSSI (strongest signal)
    best_gw = max(candidates, key=lambda g: g.rssi)
    return best_gw.gateway_id
```

**Why RSSI?** The gateway that heard the device best is most likely to have a clean downlink path. In practice, network servers also consider SNR, antenna gain, and regulatory duty-cycle limits.

## Common Pitfalls & Gotchas

1. **Gateway clock drift kills downlink timing.** The Semtech Packet Forwarder uses a 32-bit timestamp (microseconds since gateway boot). If the gateway’s clock drifts more than a few seconds, the network server’s downlink scheduling misses the receive window. Always run NTP on the gateway, and monitor `stat_interval` reports for clock sync status.

2. **DevNonce reuse is permanent.** Once a network server sees a DevNonce value for a given DevEUI, it will never accept it again. If your end device reboots and reuses the same DevNonce (e.g., from a non-persistent RNG seed), the join will fail silently. Store the last used DevNonce in NVM or use a monotonic counter.

3. **Multiple gateways don’t mean multiple downlinks.** The network server sends exactly one downlink, to exactly one gateway. If that gateway fails to transmit (e.g., duty-cycle exceeded), the downlink is lost. There is no automatic failover to another gateway. Design your application to tolerate missed downlinks.

## Try It Yourself

1. **Capture and inspect a join request.** Use a second LoRa module (e.g., SX1262 on a Raspberry Pi) in spectrum analyzer mode to capture the raw LoRa packets. Decode the JoinReq payload: extract the AppEUI, DevEUI, and DevNonce. Verify the DevNonce changes on each reboot.

2. **Set up a local ChirpStack network server.** Deploy ChirpStack v4 on a Linux VM, configure a gateway to point to it (instead of TTN), and register an end device. Watch the gateway logs (`/var/log/chirpstack-gateway-bridge/`) to see the raw UDP packets flowing.

3. **Simulate a downlink timeout.** Configure your end device to send an unconfirmed uplink every 60 seconds. On the network server, disable downlink scheduling for that device. Observe that the end device’s receive windows open, but no downlink arrives. Measure the power impact of those wasted receive windows.

## Next Up

Tomorrow I’ll break down LoRaWAN Classes A, B, and C—the three device operating modes that trade off latency for power consumption—and explain Adaptive Data Rate (ADR), the network server algorithm that dynamically adjusts spreading factor and transmit power to maximize battery life and network capacity.
