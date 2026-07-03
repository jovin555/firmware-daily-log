---
title: "Day 21: LTE-M & NB-IoT with nRF9160"
date: 2026-07-03
tags: ["til", "zephyr", "lte", "nrf9160"]
---

## What I Explored Today

Today I got my hands dirty with cellular IoT on the nRF9160 SiP using Zephyr's modem subsystem. I built a minimal application that registers on an LTE-M network, sends a UDP packet to a test server, and then cleanly tears down the connection. The goal was to understand the real workflow: configuring the modem, handling AT commands, managing power states, and dealing with the quirks of cellular network timing. The nRF9160 is a beast—it combines an ARM Cortex-M33 application processor with a dedicated LTE modem, and Zephyr provides a rich (if sometimes overwhelming) set of drivers and libraries to control it.

## The Core Concept

Why does cellular IoT matter? LTE-M and NB-IoT are 3GPP standards designed specifically for low-power, wide-area (LPWA) applications. LTE-M (Cat-M1) offers higher bandwidth (~1 Mbps) and lower latency, making it suitable for firmware updates or voice. NB-IoT (Cat-NB1/NB2) trades bandwidth for better coverage and lower power, ideal for sensors that send a few bytes per day. The nRF9160 supports both, and you select the network mode via AT commands before attaching.

The key architectural insight: Zephyr's modem subsystem abstracts the cellular stack into a socket-like API, but the real control happens through the Modem AT shell and the `modem_info` library. You don't just `connect()`—you must first configure the network mode, wait for registration, then establish a PDP context, and only then can you open sockets. The modem has its own power states (active, idle, PSM, eDRX) that you must manage explicitly to achieve the advertised ultra-low power consumption.

## Key Commands / Configuration / Code

### 1. Kconfig Configuration (prj.conf)

```kconfig
# Enable modem subsystem
CONFIG_MODEM=y
CONFIG_MODEM_CELLULAR=y
CONFIG_MODEM_INFO=y
CONFIG_MODEM_CMD_HANDLER=y

# Enable socket support
CONFIG_NET_SOCKETS=y
CONFIG_NET_SOCKETS_POSIX_NAMES=y

# nRF9160 modem specific
CONFIG_NRF_MODEM_LIB=y
CONFIG_NRF_MODEM_LIB_ON_FAULT_APPEND=y

# Enable AT shell for debugging
CONFIG_MODEM_SHELL=y

# Network mode: 0=NB-IoT, 1=LTE-M, 2=LTE-M + NB-IoT
CONFIG_NRF_MODEM_LIB_NETWORK_MODE_LTE_M_NBIOT=y

# Power saving features
CONFIG_NRF_MODEM_LIB_PSM=y
CONFIG_NRF_MODEM_LIB_EDRX=y

# Logging
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=3
```

### 2. Minimal Application Code (main.c)

```c
#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/modem/backend/uart.h>
#include <nrf_modem_at.h>
#include <nrf_modem_gnss.h>
#include <modem/modem_info.h>
#include <modem/lte_lc.h>

/* Buffer for modem responses */
static char response_buf[256];

void main(void)
{
    int err;
    struct sockaddr_in6 server_addr;
    int sock;

    printk("nRF9160 LTE-M/NB-IoT Example\n");

    /* Step 1: Initialize the modem and wait for it to be ready */
    printk("Initializing modem...\n");
    err = lte_lc_init_and_connect();
    if (err) {
        printk("Modem init failed: %d\n", err);
        return;
    }

    /* Step 2: Wait for network registration (LTE_LC_NW_REG_REGISTERED) */
    printk("Waiting for network registration...\n");
    err = lte_lc_wait_for_registration(LTE_LC_NW_REG_REGISTERED, K_SECONDS(60));
    if (err) {
        printk("Network registration timeout\n");
        return;
    }
    printk("Registered on network\n");

    /* Step 3: Send a raw AT command to verify modem is responsive */
    err = nrf_modem_at_printf("AT+CGSN");
    if (err < 0) {
        printk("AT command failed: %d\n", err);
    }

    /* Step 4: Create a UDP socket */
    sock = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        printk("Socket creation failed: %d\n", errno);
        return;
    }

    /* Step 5: Set up server address (test server at 1.2.3.4, port 1234) */
    server_addr.sin6_family = AF_INET6;
    server_addr.sin6_port = htons(1234);
    inet_pton(AF_INET6, "::ffff:1.2.3.4", &server_addr.sin6_addr);

    /* Step 6: Send a test message */
    const char *msg = "Hello from nRF9160!";
    err = sendto(sock, msg, strlen(msg), 0,
                 (struct sockaddr *)&server_addr, sizeof(server_addr));
    if (err < 0) {
        printk("Send failed: %d\n", errno);
    } else {
        printk("Sent %d bytes\n", err);
    }

    /* Step 7: Clean up */
    close(sock);
    lte_lc_power_off();
    printk("Modem powered off\n");
}
```

### 3. Debugging with AT Shell

```bash
# Connect via UART and enter AT shell
uart:~$ modem at
modem_at:~$ AT+CGMI          # Get modem manufacturer
modem_at:~$ AT+CGMM          # Get modem model
modem_at:~$ AT+CEREG?        # Check network registration status
modem_at:~$ AT+CSQ           # Check signal quality
```

## Common Pitfalls & Gotchas

1. **Network Registration Timeouts**: The `lte_lc_wait_for_registration()` function can block for up to 60 seconds. If you're indoors or in a poor coverage area, it may never register. Always implement a fallback—either retry with a different network mode (LTE-M vs NB-IoT) or set a shorter timeout and handle the failure gracefully. Use `AT+CEREG=2` to enable unsolicited registration status updates.

2. **Socket Creation After Modem Power Save**: If the modem enters PSM (Power Saving Mode) or eDRX, your socket may become invalid. The modem can drop PDP contexts when transitioning between active and idle states. Always check the return value of `sendto()` and be prepared to re-establish the socket and PDP context. Use `lte_lc_psm_req()` to control PSM parameters explicitly.

3. **AT Command Buffer Overflow**: The `nrf_modem_at_printf()` function has a limited internal buffer (typically 256 bytes). If you send a long command or expect a long response, you'll get truncated data. Use `nrf_modem_at_cmd()` with a custom buffer for complex commands. Also, never mix `nrf_modem_at_printf()` with direct UART writes to the modem—they share the same UART line and will corrupt each other.

## Try It Yourself

1. **Network Mode Switching**: Modify the `prj.conf` to use only NB-IoT (`CONFIG_NRF_MODEM_LIB_NETWORK_MODE_NBIOT=y`) and compare registration time and signal strength with LTE-M. Log the results using `AT+CSQ` and `AT+CEREG?`.

2. **Power Save Mode Configuration**: Add code to configure PSM parameters using `lte_lc_psm_req()` with a TAU (Tracking Area Update) timer of 10 minutes and an active time of 5 seconds. Measure current consumption with a power profiler before and after entering PSM.

3. **FOTA Simulation**: Use the modem's DFU service to download a small binary from a test server over UDP. Implement a simple retry mechanism that handles socket failures due to modem sleep cycles.

## Next Up

Tomorrow we dive into **Power Management: PM States & Hooks**—how to put the nRF9160 into deep sleep, wake on RTC or GPIO, and use Zephyr's power management subsystem to achieve microamp-level idle currents.
