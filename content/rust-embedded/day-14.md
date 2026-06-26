---
title: "Day 14: Embassy Networking: TCP/IP & BLE with nrf-softdevice"
date: 2026-06-26
tags: ["til", "rust-embedded", "networking", "ble", "nrf"]
---

## What I Explored Today

Today I wired up both TCP/IP over Wi-Fi (via ESP32 as a network co-processor) and BLE GATT services on an nRF52840 using Embassy's async runtime and the `nrf-softdevice` crate. The goal was to build a sensor node that streams data over TCP to a local server while simultaneously advertising a BLE service for direct phone interaction. Getting both stacks to coexist without priority inversion or buffer exhaustion took some careful design, but Embassy's executor and the softdevice's radio scheduler made it surprisingly clean.

## The Core Concept

Embedded networking with Embassy isn't about polling loops or interrupt-driven state machines—it's about async tasks that yield cooperatively. The nRF softdevice (Nordic's proprietary BLE/ANT radio stack) runs in a separate privileged mode, and `nrf-softdevice` provides safe Rust bindings that integrate with Embassy's executor. For TCP/IP, we typically use an external Wi-Fi module (ESP-AT or Wiznet) because the nRF52840 lacks built-in Ethernet/Wi-Fi. The key insight: both BLE and TCP tasks run as concurrent async tasks under the same executor, with the softdevice's radio scheduler arbitrating BLE events and the SPI/UART driver handling network traffic.

The `embassy-net` crate provides a TCP/IP stack (smoltcp-based) that works over any medium—here we use an ESP32 in AT command mode over UART. The BLE stack runs through `nrf-softdevice`'s `Softdevice` singleton, which must be initialized before any BLE operations. The critical design pattern is to spawn separate tasks for BLE advertising, connection management, and TCP data streaming, all sharing state via `embassy_sync` channels.

## Key Commands / Configuration / Code

**Cargo.toml dependencies:**
```toml
[dependencies]
embassy-executor = { version = "0.6", features = ["arch-cortex-m", "defmt"] }
embassy-time = { version = "0.4", features = ["defmt", "tick-hz-32_768"] }
embassy-nrf = { version = "0.2", features = ["nrf52840", "gpiote", "time-driver-rtc1"] }
embassy-net = { version = "0.5", features = ["defmt", "tcp", "medium-ip"] }
nrf-softdevice = { version = "0.3", features = ["ble", "s140"] }
embedded-io-async = "0.6"
```

**Initializing the softdevice and BLE stack:**
```rust
// Must be called once, before any BLE operations
let config = nrf_softdevice::Config {
    clock: Some(softdevice::ClockConfig {
        hf: softdevice::HfClockConfig::Internal,
        lf: softdevice::LfClockConfig::ExternalXtal,
    }),
    ..Default::default()
};
let sd = Softdevice::enable(&config);
// sd is a singleton—only one instance exists
```

**Spawning concurrent BLE advertising and TCP tasks:**
```rust
#[embassy_executor::task]
async fn ble_task(sd: &'static Softdevice) {
    let config = GapConfig::new(
        "nRF-Sensor",           // device name
        &adv_data::ADV_IND,     // advertising type
        &[],
        100,                    // interval (ms)
    );
    let mut advertiser = BLEAdvertiser::new(sd);
    loop {
        advertiser.advertise(&config).await;
        // Yield to other tasks between advertisements
        Timer::after_millis(500).await;
    }
}

#[embassy_executor::task]
async fn tcp_task(spi: Spi, cs: Output<'static>) {
    let mut wifi = EspWifi::new(spi, cs, 115200).await;
    wifi.connect("SSID", "PASSWORD").await;
    let mut socket = TcpSocket::new();
    socket.connect((192, 168, 1, 100, 8080)).await;
    loop {
        let sensor_data = read_sensor().await;
        socket.write_all(&sensor_data).await;
        Timer::after_secs(1).await;
    }
}
```

**Sharing data between tasks via a channel:**
```rust
static SENSOR_CHANNEL: Channel<CriticalSectionRawMutex, [u8; 32], 10> = Channel::new();

#[embassy_executor::task]
async fn sensor_task() {
    loop {
        let data = read_sensor().await;
        SENSOR_CHANNEL.send(data).await;
        Timer::after_millis(100).await;
    }
}
```

## Common Pitfalls & Gotchas

1. **Softdevice priority inversion**: The softdevice runs at a higher interrupt priority than Embassy's executor. If you hold a critical section (e.g., `interrupt::free`) for too long, BLE radio events will be missed, causing disconnections. Always use `embassy_sync` primitives instead of raw `Mutex` or `RefCell` in BLE callbacks.

2. **TCP buffer exhaustion**: `embassy-net`'s smoltcp stack uses fixed-size buffers. If your TCP socket's send buffer fills up (e.g., remote server is slow), `write_all` will block indefinitely. Set a timeout or use `write` with partial writes and retry logic. I hit this when my server went down—the task hung forever.

3. **BLE advertising interval vs. Wi-Fi throughput**: The softdevice's radio scheduler interleaves BLE advertising events with other radio activity. If your Wi-Fi module uses SPI at high speed, BLE advertising can be delayed, causing phones to miss advertisements. I found that setting the advertising interval to 100ms and using a 1ms connection interval (for connected BLE) kept both stacks happy.

## Try It Yourself

1. **Dual-stack sensor node**: Modify the code above to read a temperature sensor (e.g., SHT30) and send the value over both BLE notifications and TCP. Use a shared `Channel` to feed the same data to both tasks.

2. **BLE OTA trigger**: Add a BLE characteristic that, when written with a specific value, triggers an OTA firmware update via the softdevice's DFU service. Use `nrf-softdevice`'s `ble_dfu` feature.

3. **Wi-Fi reconnection with backoff**: Implement exponential backoff in the TCP task when the Wi-Fi connection drops. Use `Timer::after` with increasing delays (1s, 2s, 4s, ...) and reset after successful reconnection.

## Next Up

Tomorrow we'll dive into **defmt: Efficient Logging for Embedded Rust**—how to replace `println!` with a zero-overhead, format-string-based logger that works over RTT, semihosting, or UART, and why it's a game-changer for debugging async systems.
