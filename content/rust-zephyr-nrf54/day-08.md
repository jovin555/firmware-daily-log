---
title: "Day 08: SPI & I2C Peripheral Access in Rust on nRF54LM20"
date: 2026-07-17
tags: ["til", "rust-zephyr-nrf54", "spi", "i2c"]
---

## What I Explored Today

Today I wired up both SPI and I2C on the nRF54LM20 using Rust bindings to Zephyr's peripheral API. After days of GPIO toggling and UART printf debugging, it was time to talk to actual sensors and devices. I implemented a full-duplex SPI transaction with an external ADC and an I2C read from a temperature sensor, both using the `zephyr::devicetree` and `zephyr::drivers` crates. The key takeaway: Zephyr's device tree macros map cleanly to Rust types, but the ownership model for bus peripherals requires careful thought.

## The Core Concept

Zephyr's peripheral model is built on device tree nodes and driver instances. Every SPI or I2C bus is a `struct device*` in C, and the Rust bindings expose these as opaque handles. The critical insight is that Zephyr's API is inherently *shared* — multiple sensors can live on the same bus, but the bus itself is a shared resource. Rust's ownership rules fight this directly. The solution is to treat the bus handle as a token you pass around, not something you own exclusively. Zephyr's internal mutexes handle the real concurrency; your Rust code just needs to ensure you don't hold the bus across await points or try to use it from two threads without synchronization.

For SPI, the transaction model is synchronous and blocking — you configure the chip select, clock polarity/phase, and data order per-device in the devicetree, then call `spi_transceive()`. For I2C, it's simpler: you write a register address, then read bytes back. The nRF54LM20's hardware supports both at up to 8 MHz (SPI) and 1 MHz (I2C), but the Zephyr driver layer adds some overhead.

## Key Commands / Configuration / Code

First, the devicetree overlays. I added an SPI temperature sensor (MAX31855) and an I2C accelerometer (LIS2DH12) to the board's `.overlay`:

```dts
/ {
    spisensor: max31855@0 {
        compatible = "maxim,max31855";
        reg = <0>;
        spi-max-frequency = <4000000>;
        cs-gpios = <&gpio0 15 GPIO_ACTIVE_LOW>;
    };

    i2csensor: lis2dh12@18 {
        compatible = "st,lis2dh12";
        reg = <0x18>;
    };
};

&spi1 {
    status = "okay";
    cs-gpios = <&gpio0 15 GPIO_ACTIVE_LOW>;
};

&i2c2 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;
};
```

Now the Rust code. I used the `zephyr::devicetree::spi` and `zephyr::devicetree::i2c` modules to get handles:

```rust
use zephyr::devicetree::spi::{SpiBus, SpiDevice};
use zephyr::devicetree::i2c::I2cDevice;
use zephyr::drivers::spi::SpiConfig;
use zephyr::drivers::i2c::I2cMsg;

// SPI: read 4 bytes from MAX31855
fn read_spi_temp() -> Result<[u8; 4], zephyr::Error> {
    // Get bus and device from devicetree labels
    let bus = SpiBus::from_label("spi1")?;
    let dev = SpiDevice::from_label("spisensor")?;

    // Configure for this specific device (from devicetree)
    let config = SpiConfig::new()
        .frequency(4_000_000)          // 4 MHz
        .operation(spi::OP_MODE_MASTER)
        .word_size(8);                 // 8-bit words

    // Transceive: send 0x00 (dummy) to clock in 4 bytes
    let tx_buf = [0x00u8; 4];
    let mut rx_buf = [0u8; 4];

    bus.transceive(&dev, &config, &tx_buf, &mut rx_buf)?;

    Ok(rx_buf)
}

// I2C: read WHO_AM_I register (0x0F) from LIS2DH12
fn read_i2c_whoami() -> Result<u8, zephyr::Error> {
    let i2c = I2cDevice::from_label("i2csensor")?;
    let addr = 0x18u8;

    // Write register address, then read 1 byte
    let reg_addr = [0x0Fu8];
    let mut whoami = [0u8];

    i2c.write_read(addr, &reg_addr, &mut whoami, 100)?;  // 100ms timeout

    Ok(whoami[0])
}
```

The `write_read` method on I2C handles the combined transaction — Zephyr's I2C driver sends a START, writes the register, sends a repeated START, then reads. No manual stop/start needed.

## Common Pitfalls & Gotchas

**1. CS GPIO polarity mismatch.** The devicetree `cs-gpios` property must match the chip's active level. Many SPI devices use active-low chip select, but some use active-high. If your `cs-gpios` has `GPIO_ACTIVE_LOW` but the device expects `GPIO_ACTIVE_HIGH`, the transaction will appear to succeed but the slave won't respond. Always check the datasheet's timing diagram.

**2. I2C clock stretching timeout.** The nRF54LM20's I2C peripheral has a hardware timeout for clock stretching (default ~25 ms). Some older sensors stretch the clock for longer during internal operations. If you get sporadic NACKs, increase the timeout in the devicetree with `clock-stretch-timeout = <100>;` (in microseconds).

**3. Rust's `SpiConfig` is not cached.** Every call to `bus.transceive()` re-applies the configuration to the hardware registers. If you're doing high-speed transactions (e.g., reading an ADC at 1 kHz), the overhead of setting config each time adds up. For performance-critical paths, consider using Zephyr's `spi_transceive_cs()` with a pre-configured `spi_cs_control` struct, but that requires `unsafe` FFI.

## Try It Yourself

1. **Add an SPI flash memory (e.g., W25Q32) to the devicetree** and implement a `read_jedec_id()` function that sends command `0x9F` and reads 3 bytes. Verify you get the expected manufacturer ID.

2. **Write an I2C driver for a temperature/humidity sensor (e.g., SHT30)** that reads two 16-bit registers and converts to Celsius/percent RH. Use `i2c.write_read()` with a 16-bit register address (MSB first).

3. **Benchmark SPI vs I2C throughput** on the nRF54LM20: read 256 bytes from a dummy device (or loopback TX/RX) 1000 times, timing with `zephyr::sys_clock::k_cycle_get_32()`. Compare the raw bus speed to the actual application throughput.

## Next Up

Tomorrow I'm diving into Zephyr Kernel Objects from Rust: Threads, Semaphores & Mutexes. We'll see how to spawn cooperative threads, synchronize access to shared peripherals, and avoid deadlocks when mixing Rust's ownership model with Zephyr's preemptive kernel.
