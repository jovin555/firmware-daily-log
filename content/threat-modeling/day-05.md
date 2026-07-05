---
title: "Day 05: Trust Boundaries: Identifying Where Attackers Enter"
date: 2026-07-05
tags: ["til", "threat-modeling", "trust-boundary"]
---

## What I Explored Today

Today I dug into trust boundaries — the invisible lines that separate trusted from untrusted data in an embedded system. In threat modeling, every time data crosses a trust boundary, you have a potential attack surface. I spent the day mapping trust boundaries on a real STM32-based IoT sensor node, tracing data from the physical world (sensor inputs, debug ports) through firmware layers to the cloud. The key insight: most embedded vulnerabilities exist because engineers assume data is trusted when it arrives, but the boundary was crossed three layers ago.

## The Core Concept

A trust boundary is not a firewall. It’s a logical or physical demarcation where the level of trust in data changes. In embedded systems, trust boundaries exist at every interface where an external entity can inject data into your control flow.

Why this matters: Attackers don’t break your crypto; they cross trust boundaries where you forgot to validate. A classic example: a UART bootloader that accepts firmware updates without authentication. The UART pin is a physical trust boundary — the moment you accept data from it, you must assume it’s hostile. If you don’t validate at that boundary, an attacker with a $5 USB-to-UART adapter can rewrite your flash.

Trust boundaries are hierarchical. In a typical IoT device:
- **Physical boundary**: debug pins, sensor I2C/SPI buses, USB ports
- **Network boundary**: Wi-Fi/Bluetooth stack, TCP/IP sockets, MQTT topics
- **Firmware boundary**: interrupt handlers, DMA buffers, RTOS task boundaries
- **Memory boundary**: MPU/MMU regions, stack vs heap, flash vs RAM

Every time data moves from a lower-trust zone to a higher-trust zone, you must validate, sanitize, and authenticate. The most dangerous assumption: “This data came from our own sensor, so it’s safe.” Sensors can be spoofed, wires can be tapped, and I2C buses have no authentication.

## Key Commands / Configuration / Code

### 1. Mapping Trust Boundaries with a Memory Map

Start by documenting every data ingress point. Here’s a practical approach using a linker script comment block and a C header:

```c
// trust_boundaries.h — define all external data entry points
// Each entry marks a trust boundary that requires validation

typedef enum {
    TRUST_BOUNDARY_UART1_RX,      // Physical: debug UART
    TRUST_BOUNDARY_USB_CDC,       // Physical: USB virtual COM
    TRUST_BOUNDARY_SPI1_MISO,     // Physical: external sensor
    TRUST_BOUNDARY_I2C1_SDA,      // Physical: RTC/EEPROM
    TRUST_BOUNDARY_ETH_MAC_RX,    // Network: Ethernet frame
    TRUST_BOUNDARY_WIFI_RX,       // Network: Wi-Fi packet
    TRUST_BOUNDARY_DMA_CH2,       // Memory: peripheral DMA
    TRUST_BOUNDARY_IRQ_HANDLER,   // Firmware: external interrupt
} trust_boundary_t;

// Validation function — must be called at each boundary
int validate_at_boundary(trust_boundary_t boundary, 
                         const uint8_t *data, 
                         size_t len);
```

### 2. Practical Validation at a UART Trust Boundary

This is what real validation looks like — not just length checks, but protocol-level validation:

```c
// uart_rx_handler.c — validate at the UART trust boundary
// Called from ISR context, must be fast and deterministic

#define UART_MAX_PACKET  256
#define UART_MIN_PACKET  4    // header + CRC

typedef struct __attribute__((packed)) {
    uint8_t  sync_byte;       // must be 0xAA
    uint8_t  msg_type;        // 0-15 only
    uint16_t payload_len;     // must match actual bytes
    uint8_t  payload[UART_MAX_PACKET];
    uint16_t crc16;           // CRC-16-IBM over header+payload
} uart_packet_t;

// Returns 0 on success, -1 on validation failure
int validate_uart_packet(const uint8_t *raw, size_t len) {
    if (len < sizeof(uart_packet_t)) {
        return -1;  // Truncated packet — reject
    }
    const uart_packet_t *pkt = (const uart_packet_t *)raw;
    
    // Boundary check 1: sync byte
    if (pkt->sync_byte != 0xAA) {
        return -1;  // Not our protocol — discard
    }
    
    // Boundary check 2: message type range
    if (pkt->msg_type > 15) {
        return -1;  // Unknown command — reject
    }
    
    // Boundary check 3: payload length consistency
    if (pkt->payload_len > UART_MAX_PACKET) {
        return -1;  // Buffer overflow attempt — reject
    }
    if (pkt->payload_len + sizeof(uart_packet_t) - sizeof(pkt->payload) != len) {
        return -1;  // Length mismatch — possible injection
    }
    
    // Boundary check 4: CRC validation
    uint16_t calc_crc = crc16_ibm(raw, len - sizeof(uint16_t));
    if (calc_crc != pkt->crc16) {
        return -1;  // Data corruption or tampering
    }
    
    return 0;  // Passed all boundary checks
}
```

### 3. Configuring MPU to Enforce Trust Boundaries (ARMv7-M)

Hardware enforcement is better than software-only. On Cortex-M with MPU:

```c
// mpu_config.c — enforce memory trust boundaries
// Region 0: Flash (RX) — trusted code
// Region 1: SRAM data (RW) — trusted data
// Region 2: Peripheral region (RW) — untrusted DMA buffers

void configure_trust_boundary_mpu(void) {
    // Disable MPU during configuration
    MPU->CTRL = 0;
    
    // Region 2: DMA buffer area — only this region can be accessed by DMA
    // Address: 0x20001000, size: 4KB, no-execute, no-share
    MPU->RNR  = 2;
    MPU->RBAR = (0x20001000) | MPU_RBAR_VALID | (2 << 4);  // region 2
    MPU->RASR = (0x03 << 1)   // Full access (R/W for privileged)
              | (0x01 << 24)  // 4KB size
              | (0x01 << 28)  // Enable
              | (0x01 << 18); // XN (eXecute Never)
    
    // Enable MPU with background region disabled
    MPU->CTRL = MPU_CTRL_ENABLE_Msk | MPU_CTRL_PRIVDEFENA_Msk;
    __DSB();
    __ISB();
}
```

## Common Pitfalls & Gotchas

**1. Assuming DMA transfers are trusted.** DMA bypasses the CPU — it writes directly to memory. If you configure a DMA channel to receive UART data into a buffer, and that buffer is also used by a control loop, you’ve created a trust boundary that the CPU never validates. Always mark DMA buffers as untrusted memory regions in the MPU, and copy/validate before use.

**2. Trusting interrupt handlers from external sources.** An external GPIO interrupt can fire at any time. If your ISR writes to a shared variable without atomic access or a mutex, you’ve crossed a trust boundary into the main loop’s data space. Use hardware debounce, validate edge counts, and never trust the interrupt source to be well-behaved.

**3. Forgetting that “trusted” internal buses can be probed.** I2C and SPI are not authenticated. An attacker with a logic analyzer or a malicious sensor on the same bus can inject data. If your firmware reads a temperature sensor over I2C and uses that value to trigger a safety shutdown, you must validate the sensor data at the I2C transaction boundary — not just trust the device address.

## Try It Yourself

1. **Map your own system’s trust boundaries.** Take a schematic or block diagram of your current embedded project. Draw red lines at every point where external data enters: debug ports, sensors, network interfaces, user buttons, even power-on-reset timing. Count how many boundaries you find — most engineers miss at least three.

2. **Add a validation layer to one UART handler.** Take your existing UART receive ISR and add a validation function that checks packet structure, length, and CRC before the data enters your application logic. Measure the timing overhead — it should be under 10 microseconds on a 100 MHz Cortex-M.

3. **Configure an MPU region for an untrusted DMA buffer.** If your MCU has an MPU/MMU, create a memory region for your DMA receive buffer with execute-never and restricted access. Then verify that any attempt to jump to that buffer triggers a fault (this is how you prevent shellcode injection).

## Next Up

Tomorrow: **Attack Surface Analysis: UART, JTAG, USB & Debug Ports** — we’ll walk through each physical debug interface, show how to disable them in production firmware, and demonstrate a JTAG-based flash extraction attack using OpenOCD. Bring your debug probe.
