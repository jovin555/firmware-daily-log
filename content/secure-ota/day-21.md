---
title: "Day 21: Update Telemetry: Success/Failure Reporting Back to the Fleet"
date: 2026-07-21
tags: ["til", "secure-ota", "telemetry", "reporting"]
---

## What I Explored Today

Today I wired up the telemetry feedback loop that lets each device report update outcomes back to the fleet management server. Without this, OTA is a one-way gamble — you push an update and hope it landed. I implemented a lightweight, authenticated reporting pipeline using MQTT with QoS 1, structured JSON payloads, and server-side aggregation into a time-series database. The goal: every device must report either a `success` or a `failure` (with a reason code) within a configurable window, or the fleet manager flags it as a stale device.

## The Core Concept

Update telemetry is the feedback half of the OTA loop. It answers three questions: Did the update apply? Did it boot correctly? If not, why? The "why" is critical — a device that fails to boot after an update might be bricked, but a device that reports a failed signature check needs a different remediation than one that ran out of flash space.

The architecture I settled on uses a two-phase report: a **pre-reboot acknowledgment** (the update was staged and verified) and a **post-reboot confirmation** (the new firmware booted and passed its self-test). The fleet server correlates these by a unique `update_id` and `device_id`. If the post-reboot report never arrives, the server assumes a boot failure and can trigger a rollback command on the next power cycle.

For security, each report is signed with the device’s private key (using ECDSA over P-256) and includes a monotonic sequence number to prevent replay attacks. The server verifies the signature against the device’s registered public key before accepting the telemetry.

## Key Commands / Configuration / Code

### Device-Side Reporting Script (Python on embedded Linux)

```python
import json
import time
import hmac
import hashlib
from paho.mqtt import client as mqtt

# Device identity loaded from secure element
DEVICE_ID = "dev-007"
UPDATE_ID = "20260721-firmware-v3.2.1"
HMAC_KEY = bytes.fromhex("a1b2c3d4e5f6...")  # stored in TPM

def build_telemetry(status, reason=""):
    payload = {
        "device_id": DEVICE_ID,
        "update_id": UPDATE_ID,
        "status": status,          # "success" or "failure"
        "reason": reason,          # e.g., "sig_check_fail", "boot_timeout"
        "timestamp": int(time.time()),
        "seq": get_next_seq()      # monotonic counter from NVM
    }
    # HMAC-SHA256 over sorted JSON keys
    msg = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    payload["hmac"] = hmac.new(HMAC_KEY, msg.encode(), hashlib.sha256).hexdigest()
    return json.dumps(payload)

def report_status(status, reason=""):
    client = mqtt.Client(client_id=DEVICE_ID)
    client.tls_set("/etc/ssl/certs/ca.crt")
    client.username_pw_set("device", "token-from-provisioning")
    client.connect("fleet-mqtt.example.com", 8883, 60)
    
    topic = f"fleet/{DEVICE_ID}/telemetry/update"
    payload = build_telemetry(status, reason)
    # QoS 1 ensures at-least-once delivery
    client.publish(topic, payload, qos=1)
    client.disconnect()

# Called after successful staging, before reboot
report_status("staged_ok")
# After reboot, in new firmware's init
report_status("success")
```

### Server-Side Aggregation (InfluxDB Write via Python)

```python
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

client = InfluxDBClient(url="http://localhost:8086", token="admin-token", org="fleet")
write_api = client.write_api(write_options=SYNCHRONOUS)

def ingest_telemetry(mqtt_payload):
    # Verify HMAC first (omitted for brevity)
    data = json.loads(mqtt_payload)
    point = Point("update_outcome") \
        .tag("device_id", data["device_id"]) \
        .tag("update_id", data["update_id"]) \
        .field("status", data["status"]) \
        .field("reason", data.get("reason", "")) \
        .field("seq", data["seq"]) \
        .time(data["timestamp"], write_precision="s")
    write_api.write(bucket="ota_telemetry", record=point)
```

### Fleet Dashboard Query (Grafana)

```sql
-- Count successes vs failures per update rollout
SELECT 
  update_id,
  count(*) FILTER (WHERE status = 'success') AS successes,
  count(*) FILTER (WHERE status = 'failure') AS failures
FROM update_outcome
WHERE time > now() - 1h
GROUP BY update_id
```

## Common Pitfalls & Gotchas

1. **Missing post-reboot report due to watchdog reset**  
   If the device crashes during boot, it may never send the post-reboot telemetry. The server must have a timeout (e.g., 5 minutes after the pre-reboot ack) and treat missing reports as failures. I use a scheduled job that queries for devices with `staged_ok` but no `success` within the window.

2. **HMAC key rotation breaks in-flight reports**  
   If you rotate the device’s HMAC key between staging and reboot, the post-reboot report will fail verification. Always use the key that was active at the time of staging. I store the key version in the telemetry payload and keep the previous key valid for a 10-minute overlap window.

3. **QoS 1 duplicates causing double-counted successes**  
   MQTT QoS 1 guarantees delivery but can deliver duplicates. The server must deduplicate using the `seq` field. I use a Redis set per device that stores the last 100 sequence numbers; any duplicate is silently dropped.

## Try It Yourself

1. **Implement a telemetry timeout handler**  
   Write a Python script that queries your time-series database for devices that sent `staged_ok` more than 10 minutes ago but have no `success` record. Print their device IDs and simulate a rollback command.

2. **Add HMAC verification to your server-side MQTT consumer**  
   Take the `ingest_telemetry` function above and add HMAC verification before writing to InfluxDB. Use the device’s stored key (looked up from a database by `device_id`). Reject payloads with invalid HMACs.

3. **Build a Grafana alert for high failure rates**  
   Create an alert rule that fires when the failure rate for a given `update_id` exceeds 5% within the last 15 minutes. Use the SQL query above as a base and configure a webhook notification to your incident management system.

## Next Up

Tomorrow, I’ll tackle how to make all of this compliant with the **EU Cyber Resilience Act (CRA)** — specifically the update requirements around secure reporting, vulnerability disclosure timelines, and mandatory update availability periods. The CRA changes what "good enough" means for fleet telemetry.
