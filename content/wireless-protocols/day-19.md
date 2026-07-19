---
title: "Day 19: MQTT & MQTT-SN for Constrained Networks"
date: 2026-07-19
tags: ["til", "wireless-protocols", "mqtt", "mqtt-sn"]
---

## What I Explored Today

Today I dug into the practical differences between MQTT and MQTT-SN (Sensor Networks) when deploying on constrained wireless links. While MQTT dominates IoT cloud connectivity, its TCP dependency and relatively large header overhead make it painful on 802.15.4, BLE, or LoRa links where MTUs hover around 127 bytes and round-trip times are unpredictable. I spent the morning porting an existing MQTT sensor node to MQTT-SN using Eclipse Paho and the Eclipse Paho MQTT-SN gateway, measuring actual wire bytes and connection setup latency on a CC2538-based 6LoWPAN mesh.

## The Core Concept

MQTT assumes a reliable, ordered, stream-oriented transport (TCP). On constrained networks, that assumption breaks. TCP's three-way handshake adds 2-3 round trips before a single PUBLISH can flow. On a LoRa link with a 2-second airtime per packet, that's 6+ seconds just to connect. Worse, TCP's congestion control and retransmission logic interact poorly with lossy, low-bandwidth links—you get head-of-line blocking and spurious retransmissions that waste battery.

MQTT-SN replaces TCP with UDP and introduces a gateway abstraction. The gateway sits at the edge of the constrained network, translates between MQTT-SN (over UDP) and standard MQTT (over TCP), and handles session state on behalf of sleepy end devices. The wire format changes dramatically: topic names become 2-byte topic IDs, QoS flows are optimized for single-packet exchanges, and a "sleep" mode lets nodes go dormant for seconds or minutes without losing subscriptions.

The key architectural insight: MQTT-SN is not a different protocol—it's a mapping layer. Every MQTT-SN message maps 1:1 to an MQTT message at the gateway. This means your cloud broker (Mosquitto, EMQX, VerneMQ) doesn't change. Only the edge devices and the gateway need MQTT-SN support.

## Key Commands / Configuration / Code

**1. Setting up an MQTT-SN Gateway with Eclipse Paho**

The Paho gateway translates between MQTT-SN (UDP port 1883) and MQTT (TCP port 1883 on broker). Run it on a Raspberry Pi or any Linux box bridging the constrained network to Ethernet/WiFi:

```bash
# Install the gateway (from Eclipse Paho MQTT-SN Gateway)
git clone https://github.com/eclipse/paho.mqtt-sn.embedded-c.git
cd paho.mqtt-sn.embedded-c/Gateway

# Build with UDP and MQTT broker support
make gateway UDPGW=1 MQTT_BROKER=1

# Run with config file
./build/release/gateway -f gateway.conf
```

Example `gateway.conf`:
```ini
# Listen on UDP port 1883 for MQTT-SN clients
GatewayUDPPort 1883

# Forward to MQTT broker on localhost:1883
BrokerTCPAddr localhost:1883

# Enable sleep mode support (critical for battery nodes)
SleepMode true

# Pre-defined topic IDs (avoid dynamic registration overhead)
PredefinedTopicID 1 /sensors/temperature
PredefinedTopicID 2 /sensors/humidity
PredefinedTopicID 3 /actuators/valve
```

**2. MQTT-SN Client (C on Zephyr/FreeRTOS)**

Using the Paho embedded C library on a constrained device:

```c
#include "MQTTSNClient.h"

// Network context for UDP over 6LoWPAN
static Network network;
static MQTTSNClient client;

// Callback for incoming publishes
void message_arrived(MessageData* data) {
    // data->topicName->lenstring.data holds topic ID (2 bytes)
    // data->message->payload holds the payload
    if (data->topicName->lenstring.len == 2) {
        uint16_t topic_id = (data->topicName->lenstring.data[0] << 8) |
                             data->topicName->lenstring.data[1];
        if (topic_id == 3) {
            // Actuator command received
            handle_valve_command(data->message->payload);
        }
    }
}

void mqttsn_init(void) {
    // Initialize UDP socket on port 1883
    NetworkInit(&network, "192.168.1.100", 1883);
    MQTTSNClientInit(&client, &network, 5000, message_arrived);

    // Connect with sleep mode enabled (keep session alive)
    MQTTSNConnectData connect_data = MQTTSNConnectData_default;
    connect_data.duration = 60;  // sleep for 60 seconds between wakeups
    connect_data.clean_session = 0;  // retain subscriptions on gateway

    MQTTSNReturnCode rc = MQTTSNConnect(&client, &connect_data);
    if (rc != MQTTSN_RETURN_CODE_ACCEPTED) {
        // Handle connection failure
        return;
    }

    // Subscribe using pre-defined topic ID (no string exchange)
    MQTSSNSubscribeData sub_data = MQTSSNSubscribeData_default;
    sub_data.topic_id = 3;  // /actuators/valve
    sub_data.qos = MQTSSN_QOS_1;
    MQTSSNSubscribe(&client, &sub_data);
}

// On timer tick: wake, publish, sleep
void publish_temperature(float temp_c) {
    MQTTSNDisconnect(&client);  // triggers sleep mode
    // Device goes into deep sleep for 60 seconds
    // On wake, re-connect with clean_session=0
    MQTTSNConnect(&client, &connect_data);
    MQTTSNPublishData pub_data = MQTTSNPublishData_default;
    pub_data.topic_id = 1;  // /sensors/temperature
    pub_data.qos = MQTSSN_QOS_0;
    pub_data.payload = (uint8_t*)&temp_c;
    pub_data.payload_len = sizeof(float);
    MQTTSNPublish(&client, &pub_data);
    MQTTSNDisconnect(&client);  // back to sleep
}
```

**3. Wire capture comparison**

Using tcpdump on the gateway interface to see the difference:

```bash
# MQTT-SN PUBLISH (QoS 0) on wire: 7 bytes total
# [0x00][0x07] - length (7 bytes)
# [0x0C]       - message type (PUBLISH)
# [0x00]       - flags (QoS 0, no retain, topic ID type)
# [0x00][0x01] - topic ID (pre-defined #1)
# [0x41]       - payload ('A' = 0x41)

# Equivalent MQTT PUBLISH on TCP: ~30+ bytes
# Fixed header + topic string "/sensors/temperature" (20 bytes) + payload
```

## Common Pitfalls & Gotchas

**1. Topic ID registration race conditions**
Dynamic topic ID registration (REGISTER/REGACK) requires a round trip before the first PUBLISH. If your device sleeps between registration and publish, the gateway may have timed out the registration. Always use pre-defined topic IDs in the gateway config for sensors that publish infrequently—this eliminates the registration exchange entirely.

**2. Gateway session state vs. broker session state**
MQTT-SN gateways maintain their own session state (topic ID mappings, pending messages). If the gateway restarts, all connected MQTT-SN clients lose their session even if the broker has `clean_session=false`. You must implement reconnection logic that re-registers topic IDs and re-subscribes. The Paho gateway has a `-p` flag to persist state to disk, but it's not crash-safe by default.

**3. Sleep mode and QoS 1/2 interactions**
When a device is in sleep mode, the gateway buffers QoS 1/2 messages. On wakeup, the device sends a PINGREQ, and the gateway delivers buffered messages. However, if the device wakes, receives a message, and immediately goes back to sleep without sending PUBACK, the gateway will retransmit on the next wakeup. This creates duplicate delivery. Always send PUBACK before sleeping, or use QoS 0 for telemetry and reserve QoS 1 for actuation commands that need exactly-once semantics.

## Try It Yourself

1. **Measure the overhead**: Set up a Mosquitto broker and the Paho MQTT-SN gateway on a Raspberry Pi. Write a Python script using `paho-mqtt` to subscribe to `/sensors/temperature`. Then, from a constrained device (or even a second Linux machine), send 1000 temperature readings using standard MQTT (TCP) and 1000 using MQTT-SN (UDP). Use `tcpdump` or Wireshark to compare total bytes transmitted. Calculate the percentage savings.

2. **Implement sleep mode**: Modify the C client example above to publish a temperature reading every 60 seconds, sleeping between publishes. Add a second topic for a battery voltage reading that publishes every 300 seconds. Verify with the gateway logs that the device only exchanges packets during wake windows and that the gateway buffers messages for the battery topic.

3. **Test gateway failure recovery**: While your MQTT-SN client is sleeping, kill the gateway process. Restart it. Observe whether the client can reconnect and resume publishing without manual intervention. Implement a reconnection strategy that re-registers topic IDs and re-subscribes on every connect, even with `clean_session=0`.

## Next Up

Tomorrow I'll tackle **6LoWPAN & IPv6 Header Compression for Constrained Links**—how to squeeze a 40-byte IPv6 header into 2-7 bytes on an 802.15.4 frame, and why the ND (Neighbor Discovery) protocol needs a complete overhaul for low-power mesh networks.
