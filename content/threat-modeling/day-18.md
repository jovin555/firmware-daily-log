---
title: "Day 18: Command Injection & Insecure Deserialization in IoT Protocols"
date: 2026-07-18
tags: ["til", "threat-modeling", "command-injection"]
---

## What I Explored Today

Today I dug into two of the most dangerous attack vectors in IoT firmware: command injection through protocol parsers and insecure deserialization in device-to-cloud communication. These aren't theoretical — I've seen production devices bricked by malformed MQTT payloads and entire sensor networks compromised via crafted CoAP messages. The intersection of constrained resources and legacy C code makes IoT especially vulnerable. I spent the day analyzing real-world CVEs (CVE-2023-34362, CVE-2022-27226) and testing mitigations on an ESP32 target running FreeRTOS with a custom MQTT/CoAP stack.

## The Core Concept

Command injection happens when an attacker embeds OS commands into data that gets passed to a shell or system call. In IoT, this often occurs in protocol handlers that parse device names, firmware URLs, or configuration strings. The core problem: developers use `system()`, `popen()`, or `execvp()` with unsanitized input. Insecure deserialization is subtler — it exploits the trust placed in serialized data formats (CBOR, JSON, custom binary protocols) to inject malicious objects that alter program flow or allocate unexpected memory.

Why these matter together: IoT devices commonly receive serialized commands over MQTT or CoAP, deserialize them, and then execute actions based on the parsed data. A single vulnerability chain — deserialize a crafted payload that contains a command injection string — gives an attacker remote code execution with no authentication bypass needed. The STRIDE threat model classifies this as Tampering + Elevation of Privilege.

## Key Commands / Configuration / Code

### Vulnerable MQTT Command Handler (C on ESP32)

```c
// DANGEROUS: Direct system() call with MQTT topic payload
void mqtt_callback(char *topic, uint8_t *payload, unsigned int len) {
    char cmd[128];
    // payload contains: "firmware_update; rm -rf /"
    snprintf(cmd, sizeof(cmd), "wget http://update-server/%s", payload);
    system(cmd);  // NEVER DO THIS
}
```

### Secure Implementation with Input Validation

```c
// SAFE: Whitelist-based command dispatch
#define MAX_CMD_LEN 64
#define VALID_CMDS "reboot", "status", "update"

typedef enum { CMD_REBOOT, CMD_STATUS, CMD_UPDATE, CMD_INVALID } cmd_t;

cmd_t parse_command(const char *input) {
    // Reject any non-alphanumeric characters
    for (size_t i = 0; input[i] != '\0'; i++) {
        if (!isalnum((unsigned char)input[i]) && input[i] != '_') {
            return CMD_INVALID;
        }
    }
    if (strcmp(input, "reboot") == 0) return CMD_REBOOT;
    if (strcmp(input, "status") == 0) return CMD_STATUS;
    if (strcmp(input, "update") == 0) return CMD_UPDATE;
    return CMD_INVALID;
}

void handle_mqtt_command(const char *raw_cmd) {
    switch (parse_command(raw_cmd)) {
        case CMD_REBOOT: esp_restart(); break;
        case CMD_STATUS: report_status(); break;
        case CMD_UPDATE: trigger_safe_update(); break;
        default: log_error("Invalid command received"); break;
    }
}
```

### Insecure Deserialization in CBOR (Common in CoAP)

```c
// VULNERABLE: No bounds checking on CBOR array length
void parse_sensor_config(uint8_t *cbor_data, size_t len) {
    CborParser parser;
    CborValue it;
    cbor_parser_init(cbor_data, len, 0, &parser, &it);
    
    // Attacker sends array with count=65535, causing OOM or buffer overflow
    size_t array_len;
    cbor_value_get_array_length(&it, &array_len);
    
    // No validation! Allocates based on attacker-controlled value
    sensor_t *sensors = malloc(array_len * sizeof(sensor_t));
    // ... reads into this buffer without checking actual data size
}
```

### Secure CBOR Deserialization with Bounds

```c
// SAFE: Enforce maximum array length
#define MAX_SENSORS 32

bool parse_sensor_config_safe(uint8_t *cbor_data, size_t len) {
    CborParser parser;
    CborValue it;
    if (cbor_parser_init(cbor_data, len, 0, &parser, &it) != CborNoError)
        return false;
    
    size_t array_len;
    if (cbor_value_get_array_length(&it, &array_len) != CborNoError)
        return false;
    
    // Reject oversized arrays immediately
    if (array_len > MAX_SENSORS) {
        log_error("Sensor count %zu exceeds max %d", array_len, MAX_SENSORS);
        return false;
    }
    
    // Now safe to allocate
    sensor_t *sensors = calloc(array_len, sizeof(sensor_t));
    if (!sensors) return false;
    
    // Parse each element with type checking
    for (size_t i = 0; i < array_len; i++) {
        if (!cbor_value_is_text_string(&it)) {
            free(sensors);
            return false;
        }
        // ... safe parsing continues
    }
    return true;
}
```

### MQTT Broker ACL Configuration (Mosquitto)

```conf
# /etc/mosquitto/acl.conf
# Restrict command topics to specific patterns
pattern write sensor/%u/command
pattern read sensor/%u/status

# Block shell metacharacters at broker level (Mosquitto 2.x+)
# Requires plugin: mosquitto-noprompt
allow_anonymous false
password_file /etc/mosquitto/passwd
```

## Common Pitfalls & Gotchas

1. **Assuming protocol libraries are safe.** I've seen teams use `cJSON_Parse()` without checking for nested object depth. An attacker sends a deeply nested JSON (e.g., 10,000 levels) that blows the stack on a Cortex-M0 with 8KB RAM. Always set recursion limits — `cJSON_InitHooks()` lets you override malloc, but not depth.

2. **Shell escaping is not enough.** Many developers try `escapeshellcmd()` or manual backslash escaping. This fails because different shells (sh, bash, ash) interpret escape sequences differently. On BusyBox ash (common in IoT), `\n` inside a string is not escaped — it's a literal newline. Whitelist-based dispatch is the only reliable defense.

3. **CBOR indefinite-length arrays.** The CBOR spec allows arrays without a declared length (major type 4, additional info 31). If your parser doesn't handle this, an attacker can send an "infinite" array that causes your parser to loop forever or OOM. Always check `cbor_value_is_length_known()` before trusting array lengths.

## Try It Yourself

1. **Audit your MQTT handler.** Find every place where `system()`, `popen()`, or `exec*()` is called. Replace with a whitelist-based command dispatcher. Test with payloads containing `;`, `|`, `&&`, and backticks.

2. **Fuzz your CBOR/JSON deserializer.** Write a Python script that generates malformed CBOR: arrays with count=0xFFFFFFFF, deeply nested maps (depth 100+), and indefinite-length arrays. Feed these to your device over CoAP and monitor for crashes or memory leaks.

3. **Set up MQTT ACLs.** Configure Mosquitto with pattern-based ACLs that restrict which topics each device can publish/subscribe to. Test that a compromised device cannot publish to `+/command` topics belonging to other devices.

## Next Up

Tomorrow: **Denial-of-Service Resilience: Input Validation & Rate Limiting** — we'll explore how to protect IoT devices from resource exhaustion attacks through proper input throttling, watchdog timers, and protocol-level rate limiting.
