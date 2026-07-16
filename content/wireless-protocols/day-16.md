---
title: "Day 16: Modem AT Commands & Cellular Firmware Integration Patterns"
date: 2026-07-16
tags: ["til", "wireless-protocols", "at-commands", "modem"]
---

## What I Explored Today

Today I dug into the gritty reality of talking to cellular modems from an MCU. While high-level SDKs and abstraction layers exist, the vast majority of production cellular IoT firmware still relies on raw AT commands over UART. I spent the day studying the Quectel BG96 and u-blox SARA-R5 command sets, focusing on connection lifecycle management, socket handling, and the dreaded "AT+QISEND" timeout dance. The key insight: treating the modem as a state machine, not a command-line tool, is what separates robust firmware from flaky prototypes.

## The Core Concept

Cellular modems are complex, autonomous devices with their own protocol stacks, TCP/IP offload engines, and power management controllers. Your MCU is not "running the network stack" — it's a dumb client issuing text commands and parsing responses. The fundamental pattern is a **request-response-event** model:

1. **Request**: MCU sends AT command (e.g., `AT+QIOPEN=...`)
2. **Response**: Modem replies with `OK` or `ERROR` (synchronous)
3. **Event**: Modem sends unsolicited result codes (URCs) like `+QIURC: "recv",0,100` (asynchronous)

The trap is treating this like a blocking shell. In production, you must:
- Buffer URCs while waiting for command responses
- Use a command queue with timeouts
- Handle modem crashes (watchdog reset via PWRKEY pin)
- Parse responses with a state machine, not `strstr()`

## Key Commands / Configuration / Code

### 1. Modem Initialization Sequence (Quectel BG96)

```c
// Step 1: Basic handshake
AT                          // -> OK
ATE0                        // -> OK (disable echo)
AT+CMEE=2                   // -> OK (verbose error codes)

// Step 2: Network registration
AT+CREG?                    // -> +CREG: 0,1 (home network)
AT+CGREG?                   // -> +CGREG: 0,1 (packet domain)
AT+CGATT=1                  // -> OK (attach to GPRS)

// Step 3: Configure PDP context
AT+CGDCONT=1,"IP","iot.telefonica.com"  // -> OK
AT+QIACT=1                  // -> OK (activate context)

// Step 4: Open TCP socket (non-transparent mode)
AT+QIOPEN=1,0,"TCP","mqtt.example.com",1883,0,0
// -> +QIOPEN: 0,0 (connectID, errorCode)
```

### 2. Robust Command Wrapper (Pseudo-C)

```c
typedef enum {
    MODEM_IDLE,
    MODEM_CMD_PENDING,
    MODEM_CMD_TIMEOUT,
    MODEM_URC_PENDING
} modem_state_t;

// Command queue entry
typedef struct {
    char cmd[128];
    uint32_t timeout_ms;
    void (*callback)(int result, char* response);
} modem_cmd_t;

// Non-blocking send with timeout
int modem_send_cmd(modem_cmd_t* cmd) {
    if (modem_state != MODEM_IDLE) return -1;  // Busy
    
    // Flush any stale URCs from RX buffer
    modem_flush_rx();
    
    // Send command
    uart_write(cmd->cmd, strlen(cmd->cmd));
    uart_write("\r\n", 2);
    
    // Start timeout timer
    timer_start(cmd->timeout_ms);
    modem_state = MODEM_CMD_PENDING;
    
    return 0;
}

// UART RX interrupt handler
void uart_rx_isr(uint8_t byte) {
    static char line[256];
    static uint8_t idx = 0;
    
    line[idx++] = byte;
    if (byte == '\n') {
        line[idx] = '\0';
        idx = 0;
        
        if (strstr(line, "+QURC:") || strstr(line, "+QIURC:")) {
            // Push to URC queue, not command response
            urc_queue_push(line);
        } else if (modem_state == MODEM_CMD_PENDING) {
            // Check for OK, ERROR, or +CME ERROR
            if (strstr(line, "OK") || strstr(line, "ERROR")) {
                modem_state = MODEM_IDLE;
                timer_stop();
                cmd->callback(0, line);  // 0 = success
            }
        }
    }
}
```

### 3. Socket Data Reception Pattern

```c
// Modem sends: +QIURC: "recv",0,<data_len>
// MCU must read with: AT+QIRD=0,<data_len>

void handle_recv_urc(char* urc) {
    int connect_id, data_len;
    sscanf(urc, "+QIURC: \"recv\",%d,%d", &connect_id, &data_len);
    
    // Allocate buffer and read data
    char* buf = malloc(data_len + 1);
    char read_cmd[64];
    snprintf(read_cmd, sizeof(read_cmd), "AT+QIRD=%d,%d", connect_id, data_len);
    
    modem_send_cmd(read_cmd, 5000, read_callback);
    // In read_callback: parse response, feed to MQTT/CoAP stack
}
```

## Common Pitfalls & Gotchas

### 1. The "AT+QISEND" Timeout Death Spiral
When sending large payloads (e.g., 1KB+), the modem may take 2-10 seconds to transmit. If your firmware blocks waiting for `SEND OK`, the URC handler starves. **Fix**: Use non-blocking sends with a separate "send pending" state. Poll `AT+QISACK` to confirm delivery.

### 2. URCs Interleaved with Command Responses
The modem can send `+QIRDI: 0` (incoming data) right in the middle of your `AT+QISTATE=0` response. **Fix**: Always store URCs in a separate queue. Never parse responses with `strstr()` on raw UART data — use a line-based parser that classifies each line as command response, URC, or error.

### 3. Power Saving Mode (PSM) Wake-Up Race
After entering PSM, the modem may take 500ms to wake and re-register. Sending AT commands immediately after asserting DTR causes `ERROR` or no response. **Fix**: Wait for `+QIND: "URC"` or poll `AT+CPIN?` until you get a valid response. Use a minimum 1-second guard timer after wake.

## Try It Yourself

1. **Trace a live connection**: Connect a cellular modem to your dev board and use a logic analyzer on the UART TX/RX lines. Capture the full sequence from power-on to sending an MQTT PUBLISH packet. Identify every URC that arrives during command processing.

2. **Build a URC queue**: Write a minimal state machine (in C or Python) that demultiplexes incoming modem lines into three buckets: command responses, URCs, and errors. Test it against a recorded session log from a real modem.

3. **Implement a retry with exponential backoff**: Write a function that sends `AT+QIACT=1` (activate PDP context) with retries: 3 attempts, 1s/2s/4s delays. Handle the case where the modem returns `+CME ERROR: 100` (unknown error) by power-cycling the modem via PWRKEY.

## Next Up

Tomorrow we shift from cellular to Wi-Fi, but not the power-hungry kind you're used to. We'll explore **Wi-Fi HaLow (802.11ah)** and the **Power-Save (PS) modes** that let Wi-Fi IoT nodes run for years on a coin cell. Spoiler: it's not just about turning the radio off.
