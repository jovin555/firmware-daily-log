---
title: "Day 17: Networking Stack: BSD Sockets & TCP/IP"
date: 2026-06-29
tags: ["til", "zephyr", "networking", "tcp-ip"]
---

## What I Explored Today

Today I dove into Zephyr's networking stack, specifically how it implements the BSD Sockets API for TCP/IP communication. After wrestling with a custom IoT sensor that needed to stream data to a cloud endpoint over TCP, I needed to understand the practical differences between Zephyr's socket interface and the POSIX sockets I'm used to on Linux. The key takeaway: Zephyr gives you a familiar API but with critical constraints around memory, concurrency, and configuration that can bite you if you're not paying attention.

## The Core Concept

Zephyr's networking stack is modular, supporting multiple network interfaces (Ethernet, Wi-Fi, 6LoWPAN, Bluetooth IPSS) through a unified L2 layer. The BSD Sockets API (`<zephyr/net/socket.h>`) provides a POSIX-compatible interface on top of the native TCP/IP stack. Why BSD sockets? Because it's the universal language of network programming — any engineer who's written a TCP client on Linux, Windows, or a microcontroller can pick this up immediately.

But here's the critical difference: Zephyr runs on resource-constrained devices. You don't have virtual memory, process isolation, or a full libc. The socket API is implemented as a thin wrapper around Zephyr's `net_context` and `net_pkt` buffer management. Every socket operation involves buffer pools, and if you misconfigure them, you get silent packet drops instead of graceful errors. The stack also runs in a cooperative or preemptive thread context — blocking socket calls will stall your entire application unless you offload them to a dedicated thread.

The stack is configured via Kconfig. You need `CONFIG_NETWORKING`, `CONFIG_NET_TCP`, and typically `CONFIG_NET_SOCKETS_POSIX_NAMES` to get the familiar `socket()`, `bind()`, `listen()`, `accept()`, `connect()`, `send()`, `recv()` names. Without the POSIX names option, you'd use `zsock_socket()`, `zsock_bind()`, etc. — which is fine but breaks portability.

## Key Commands / Configuration / Code

**Minimal Kconfig for a TCP client:**

```kconfig
CONFIG_NETWORKING=y
CONFIG_NET_IPV4=y
CONFIG_NET_TCP=y
CONFIG_NET_SOCKETS=y
CONFIG_NET_SOCKETS_POSIX_NAMES=y
CONFIG_NET_BUF=y
CONFIG_NET_PKT_TX_COUNT=16
CONFIG_NET_PKT_RX_COUNT=16
CONFIG_NET_BUF_DATA_SIZE=256
CONFIG_HEAP_MEM_POOL_SIZE=4096
CONFIG_MAIN_STACK_SIZE=4096
```

**TCP client example (sending sensor data):**

```c
#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/net_if.h>

#define SERVER_ADDR "192.168.1.100"
#define SERVER_PORT 8080

void tcp_client_thread(void *arg1, void *arg2, void *arg3)
{
    int sock = -1;
    struct sockaddr_in addr;
    char buf[128];
    int ret;

    /* Create socket */
    sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        printk("socket() failed: %d\n", errno);
        return;
    }

    /* Configure server address */
    addr.sin_family = AF_INET;
    addr.sin_port = htons(SERVER_PORT);
    inet_pton(AF_INET, SERVER_ADDR, &addr.sin_addr);

    /* Connect — this blocks */
    ret = connect(sock, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0) {
        printk("connect() failed: %d\n", errno);
        close(sock);
        return;
    }

    /* Send data in a loop */
    while (1) {
        snprintf(buf, sizeof(buf), "sensor_value=%d\n", 
                 (int)(k_uptime_get() % 100));
        ret = send(sock, buf, strlen(buf), 0);
        if (ret < 0) {
            printk("send() failed: %d\n", errno);
            break;
        }
        k_sleep(K_SECONDS(5));
    }

    close(sock);
}

K_THREAD_DEFINE(tcp_client_tid, 4096,
                tcp_client_thread, NULL, NULL, NULL,
                5, 0, 0);
```

**TCP server snippet (echo server):**

```c
int server_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
struct sockaddr_in bind_addr = {
    .sin_family = AF_INET,
    .sin_port = htons(8080),
    .sin_addr.s_addr = INADDR_ANY
};

bind(server_sock, (struct sockaddr *)&bind_addr, sizeof(bind_addr));
listen(server_sock, 1);

while (1) {
    int client = accept(server_sock, NULL, NULL);
    char rx_buf[64];
    int len = recv(client, rx_buf, sizeof(rx_buf) - 1, 0);
    if (len > 0) {
        rx_buf[len] = '\0';
        send(client, rx_buf, len, 0);
    }
    close(client);
}
```

## Common Pitfalls & Gotchas

1. **Stack overflow from socket operations.** The default `CONFIG_MAIN_STACK_SIZE` (typically 2048) is too small for TCP operations. Socket calls use significant stack for buffer management and protocol processing. Always use a dedicated thread with at least 4096 bytes stack, and monitor with `CONFIG_THREAD_STACK_INFO` and `k_thread_stack_space_get()`.

2. **Silent buffer starvation.** If `CONFIG_NET_PKT_TX_COUNT` or `CONFIG_NET_PKT_RX_COUNT` is too low, the stack will silently drop packets when buffers are exhausted. You'll see `send()` succeed but data never arrives. Monitor with `net_stats_print_stats()` or enable `CONFIG_NET_STATISTICS` to catch this. For active TCP connections, start with 16 TX and 16 RX buffers.

3. **Blocking calls in the wrong context.** Zephyr's networking stack is not reentrant in all configurations. Calling `recv()` with a blocking flag from an ISR or a cooperative thread will hang the system. Always use `SOCK_NONBLOCK` with `poll()` or run socket code in a preemptive thread (priority < 0 or use `K_FP_REGS`).

4. **Forgetting to set `CONFIG_NET_SOCKETS_POSIX_NAMES`.** Without this, you must use `zsock_socket()`, `zsock_send()`, etc. The POSIX names are mapped via macros, but the mapping is only available if the config is enabled. Mixing `socket()` with `zsock_send()` will cause linker errors.

## Try It Yourself

1. **Build a TCP echo server** that accepts connections on port 8888 and echoes back received data. Test it with a PC using `netcat` (`nc <device_ip> 8888`). Monitor buffer usage with `net_stats_print_stats()`.

2. **Add non-blocking I/O** to the TCP client example above. Use `fcntl(sock, F_SETFL, O_NONBLOCK)` and `poll()` with `POLLIN`/`POLLOUT` to handle timeouts gracefully. Set a 10-second connect timeout using `SO_TIMEOUT` socket option.

3. **Implement a simple HTTP GET request** using BSD sockets. Connect to `example.com:80`, send `"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"`, and print the response. You'll need DNS resolution — enable `CONFIG_DNS_RESOLVER` and use `getaddrinfo()`.

## Next Up

Tomorrow, we'll switch gears to wireless personal area networks: **Bluetooth LE: Advertising, Scanning & GATT**. We'll configure a BLE peripheral to advertise custom service data, scan for nearby devices, and implement a GATT server with read/write characteristics — essential for wearables and beacon applications.
