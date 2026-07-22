---
title: "Day 22: Zephyr Networking Stack: Connection Manager & Sockets API"
date: 2026-07-22
tags: ["til", "wireless-protocols", "zephyr", "connection-manager"]
---

## What I Explored Today

Today I dug into Zephyr's networking stack—specifically how the Connection Manager orchestrates link-level connectivity and how the Sockets API provides a familiar BSD-like interface for application developers. After spending weeks on lower-level radio details, it was refreshing to see how Zephyr abstracts away the PHY and MAC layers, letting us write network code that looks almost identical to a Linux socket application, while still giving us fine-grained control over power management and connection events.

## The Core Concept

The Zephyr networking stack is modular by design. At the bottom, you have the L2 layer (Ethernet, IEEE 802.15.4, Bluetooth, etc.), and above that sits the IP stack (IPv4/IPv6). The **Connection Manager** is the glue that manages the link state—it handles bringing interfaces up, scanning for networks, associating with APs or coordinators, and triggering reconnection when the link drops. It's not a full TCP/IP stack; it's the state machine that keeps the radio connected.

Why does this matter? In low-power wireless, the radio is often the biggest power drain. The Connection Manager lets you implement policies like "stay connected but enter DTIM sleep" or "disconnect after 30 seconds of idle." Without it, you'd have to manually poll the link status and implement reconnection logic in every application.

The **Sockets API** (`bsdlib` or `zephyr/net/socket.h`) provides POSIX-compatible socket functions: `socket()`, `bind()`, `listen()`, `accept()`, `connect()`, `send()`, `recv()`. This means you can port existing network code with minimal changes. Under the hood, Zephyr maps these to its native networking buffers (`net_pkt`) and offloads TLS/DTLS via `mbedtls` if configured.

## Key Commands / Configuration / Code

### 1. Enabling the Connection Manager in `prj.conf`

```kconfig
# Enable networking core
CONFIG_NETWORKING=y
CONFIG_NET_IPV4=y
CONFIG_NET_IPV6=y

# Connection Manager (for Wi-Fi / Ethernet)
CONFIG_NET_CONNECTION_MANAGER=y
CONFIG_NET_CONNECTION_MANAGER_MONITOR_STACK_SIZE=1024

# For Wi-Fi specifically
CONFIG_WIFI=y
CONFIG_WIFI_ESP_AT=y          # Example: ESP32 AT command Wi-Fi
CONFIG_NET_L2_ETHERNET=y

# Socket support
CONFIG_NET_SOCKETS=y
CONFIG_NET_SOCKETS_POSIX_NAMES=y   # Use standard names (socket, bind, etc.)
```

### 2. Basic TCP Client Using Sockets API

```c
#include <zephyr/net/socket.h>
#include <zephyr/kernel.h>

#define SERVER_ADDR "192.168.1.100"
#define SERVER_PORT 8080

void tcp_client(void)
{
    int sock = -1;
    struct sockaddr_in addr;

    // 1. Create socket (AF_INET, SOCK_STREAM, protocol 0 = TCP)
    sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        printk("socket() failed: %d\n", errno);
        return;
    }

    // 2. Set server address
    addr.sin_family = AF_INET;
    addr.sin_port = htons(SERVER_PORT);
    inet_pton(AF_INET, SERVER_ADDR, &addr.sin_addr);

    // 3. Connect (blocks until connected or timeout)
    if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        printk("connect() failed: %d\n", errno);
        goto cleanup;
    }

    // 4. Send data
    char *msg = "Hello from Zephyr!";
    int sent = send(sock, msg, strlen(msg), 0);
    printk("Sent %d bytes\n", sent);

    // 5. Receive response
    char buf[128];
    int received = recv(sock, buf, sizeof(buf) - 1, 0);
    if (received > 0) {
        buf[received] = '\0';
        printk("Received: %s\n", buf);
    }

cleanup:
    if (sock >= 0) {
        close(sock);
    }
}
```

### 3. Monitoring Connection State with Connection Manager

```c
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/net_event.h>

static struct net_mgmt_event_callback conn_cb;

static void connection_event_handler(struct net_mgmt_event_callback *cb,
                                     uint32_t mgmt_event,
                                     struct net_if *iface)
{
    switch (mgmt_event) {
    case NET_EVENT_L4_CONNECTED:
        printk("Network connected (IP assigned)\n");
        break;
    case NET_EVENT_L4_DISCONNECTED:
        printk("Network disconnected\n");
        // Trigger reconnection logic here
        break;
    default:
        break;
    }
}

void setup_connection_monitor(void)
{
    net_mgmt_init_event_callback(&conn_cb, connection_event_handler,
                                 NET_EVENT_L4_CONNECTED |
                                 NET_EVENT_L4_DISCONNECTED);
    net_mgmt_add_event_callback(&conn_cb);
}
```

## Common Pitfalls & Gotchas

1. **Socket descriptor limits**: Zephyr's default `CONFIG_NET_SOCKETS_POSIX_MAX` is often 4 or 8. If you open multiple sockets (e.g., HTTP client + MQTT + CoAP), you'll hit `ENFILE`. Always increase this in `prj.conf`:
   ```
   CONFIG_NET_SOCKETS_POSIX_MAX=16
   ```

2. **Connection Manager doesn't auto-reconnect by default**: The Connection Manager will report disconnection events, but you must implement reconnection logic yourself. Many engineers assume it automatically retries—it does not. You need to register for `NET_EVENT_L4_DISCONNECTED` and call `net_mgmt()` to re-associate.

3. **Socket timeouts are not POSIX by default**: Zephyr sockets don't have a default send/recv timeout. If the network drops, `recv()` can block forever. Always set a timeout using `setsockopt()` with `SO_RCVTIMEO`:
   ```c
   struct timeval timeout = { .tv_sec = 5, .tv_usec = 0 };
   setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
   ```

## Try It Yourself

1. **Build a minimal TCP echo client**: Configure a Zephyr project for your board (e.g., nRF52840 DK with ESP32 Wi-Fi), enable the Connection Manager and sockets, and write a client that connects to a local echo server (use `netcat -l -p 8080 -e /bin/cat` on Linux). Verify send/recv works.

2. **Add connection monitoring**: Extend the echo client to register for `NET_EVENT_L4_CONNECTED` and `NET_EVENT_L4_DISCONNECTED`. When disconnected, print the event and attempt to reconnect by calling `net_mgmt()` with `NET_REQUEST_WIFI_CONNECT`. Test by unplugging your Wi-Fi AP.

3. **Implement a non-blocking socket**: Modify the client to use `O_NONBLOCK` via `fcntl(sock, F_SETFL, O_NONBLOCK)`. Handle `EAGAIN`/`EWOULDBLOCK` in the send/recv loop. Measure the power difference using a current probe between blocking and non-blocking modes.

## Next Up

Tomorrow we move from implementation to validation: **Interoperability Testing & Certification: Bluetooth SIG, Thread Group**. We'll cover the PTS (Profile Tuning Suite) for Bluetooth, the Thread Test Harness, and what it takes to get your product certified for the official logos. Bring your test scripts.
