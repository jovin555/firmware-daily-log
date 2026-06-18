---
title: "Day 06: Peripheral Access Crates (PAC): Register-Level Access"
date: 2026-06-18
tags: ["til", "rust-embedded", "pac", "registers", "svd2rust"]
---

## What I Explored Today

Today I dove into Peripheral Access Crates (PACs)—the lowest-level Rust abstraction for microcontroller hardware. PACs are auto-generated from SVD (System View Description) files using `svd2rust`, giving us type-safe, zero-cost access to every register and bitfield in the microcontroller's memory map. I learned how to read, modify, and write registers directly, and why this matters even when higher-level HALs exist.

## The Core Concept

Every embedded engineer eventually needs to touch registers. Maybe the HAL doesn't expose a specific feature, you're debugging a hardware quirk, or you're writing your own driver. PACs are the bridge between raw memory-mapped I/O and safe Rust.

The key insight: PACs don't abstract away the hardware—they make it *safer to access*. Instead of `unsafe { *(0x4000_0000 as *mut u32) = 0x01; }`, you get:

```rust
peripherals.GPIOA.odr.write(|w| w.bits(0x01));
```

Under the hood, this compiles to the exact same single `STR` instruction, but the compiler now knows the register width, the bitfield layout, and can enforce read/write permissions at compile time. The PAC also handles the volatile access for you—no more forgotten `core::ptr::read_volatile`.

The real power? The type system prevents entire classes of bugs. You can't write a 32-bit value to a 16-bit register. You can't write to a read-only register. You can't accidentally use the wrong base address. And because everything is generated from the vendor's SVD file, the register definitions are guaranteed to match the datasheet.

## Key Commands / Configuration / Code

### Adding a PAC to your project

For an STM32F103 (Blue Pill), add this to `Cargo.toml`:

```toml
[dependencies]
stm32f1 = { version = "0.15", features = ["rt"] }
cortex-m = "0.7"
cortex-m-rt = "0.7"
```

The `rt` feature enables the vector table and startup code. Without it, you'd need to manually set up the interrupt handlers.

### Reading a register

```rust
use stm32f1::stm32f103;

let peripherals = stm32f103::Peripherals::take().unwrap();
let gpioa = &peripherals.GPIOA;

// Read the Input Data Register (IDR) - returns a RegisterBlock
let idr_value: u16 = gpioa.idr.read().bits();
// Or access individual bitfields:
let pin5_state: bool = gpioa.idr.read().idr5().bit_is_set();
```

### Writing to an output register

```rust
// Set PA5 high using the Output Data Register (ODR)
gpioa.odr.write(|w| w.odr5().set_bit());

// Atomic set/reset using BSRR (Bit Set/Reset Register)
gpioa.bsrr.write(|w| w.bs5().set_bit());   // Set PA5
gpioa.bsrr.write(|w| w.br5().set_bit());   // Reset PA5
```

### Modifying a single bitfield (read-modify-write)

```rust
// Configure PA5 as push-pull output, 50MHz speed
gpioa.crl.write(|w| {
    w.mode5().output_50mhz()   // Set mode bits
     .cnf5().push_pull()       // Set config bits
});
```

The `modify` method is safer for partial updates:

```rust
// Only change the mode for PA5, leave other pins untouched
gpioa.crl.modify(|_, w| {
    w.mode5().output_50mhz()
});
```

### Enabling a peripheral clock

This is the most common mistake—forgetting to enable the clock:

```rust
let rcc = &peripherals.RCC;
rcc.apb2enr.write(|w| w.iopaen().set_bit());  // Enable GPIOA clock
// Now GPIOA registers are accessible
```

## Common Pitfalls & Gotchas

**1. Forgetting to enable the peripheral clock**
The most frequent bug. Reading a register on a clock-gated peripheral returns garbage (often 0x00000000 or 0xFFFFFFFF). Always check the reference manual's clock tree—each peripheral has a specific enable bit in RCC.

**2. Using `write()` when you need `modify()`**
`write()` sets *all* bits in the register to the value you specify. If you only want to change one bitfield, `write()` will zero out everything else. This is especially dangerous with configuration registers like `CRL`/`CRH` where other pins' settings live in the same register.

**3. Misunderstanding volatile access**
PACs handle volatile reads/writes automatically, but if you hold a reference to a register across multiple operations, the compiler might optimize away intermediate reads. Always re-read from the peripheral if you need the latest value:

```rust
// WRONG - compiler might cache the first read
let idr = &gpioa.idr;
let first = idr.read().bits();
// ... some delay ...
let second = idr.read().bits();  // Might return cached value

// RIGHT - fresh reference each time
let first = gpioa.idr.read().bits();
// ... some delay ...
let second = gpioa.idr.read().bits();
```

## Try It Yourself

1. **Blink an LED using only PAC calls** — No HAL, no `embedded-hal` traits. Write a program that toggles PA5 by directly writing to the BSRR register. Measure the toggle rate with an oscilloscope and compare it to a HAL-based implementation.

2. **Read a button with internal pull-up** — Configure a GPIO pin as input with pull-up, then poll the IDR register in a loop. Print the pin state over semihosting or a serial port. Verify the register values match the datasheet.

3. **Reverse-engineer a register** — Pick a peripheral you haven't used (e.g., TIM2 or USART1). Without looking at example code, use the PAC API and the reference manual to configure it for a simple operation (e.g., generate a 1Hz timer interrupt). This forces you to understand the register map.

## Next Up

Tomorrow we'll explore **Embedded HAL: The Hardware Abstraction Layer Traits** — how traits like `OutputPin`, `DelayMs`, and `Serial` let you write portable drivers that work across any microcontroller with a HAL implementation. We'll see how the PAC we learned today becomes the foundation for these abstractions.
