---
title: "Day 27: Peripheral Access Crates (PAC): Register-Level Access"
date: 2026-07-09
tags: ["til", "rust-embedded", "pac", "registers", "svd2rust"]
---

## What I Explored Today

Today I dove into Peripheral Access Crates (PACs) — the lowest-level Rust interface to microcontroller hardware. Generated automatically from vendor SVD files using `svd2rust`, PACs give us direct register-level access with type-safe abstractions. No more magic numbers or datasheet page-flipping for bit positions. After weeks of blinking LEDs with high-level APIs, I finally understand what happens when you write to `GPIO_ODR`.

## The Core Concept

Every microcontroller peripheral is controlled by reading and writing memory-mapped registers. Traditionally, embedded C code does this with `#define` macros and struct pointer casts. Rust PACs replace this fragile approach with compile-time checked register access.

The key insight: PACs don't abstract away the hardware — they make the hardware *safer* to touch. Each register becomes a strongly-typed struct. Each bitfield becomes an enum or a newtype. Write operations are atomic by default. Read-modify-write patterns are explicit.

Why does this matter? Because register-level bugs are insidious. Writing to the wrong bit can disable a clock tree, corrupt a DMA transfer, or silently brick your I2C bus. PACs catch these mistakes at compile time, not during a 3 AM debug session.

The `svd2rust` toolchain reads CMSIS-SVD XML files (provided by silicon vendors) and generates Rust code that mirrors the hardware register map exactly. The generated code uses `core::ptr::write_volatile` and `core::ptr::read_volatile` under the hood, ensuring the compiler doesn't optimize away your hardware accesses.

## Key Commands / Configuration / Code

First, add a PAC to your project. For an STM32F4, you'd use `stm32f4`:

```toml
# Cargo.toml
[dependencies]
stm32f4 = { version = "0.15.1", features = ["stm32f411"] }
cortex-m = "0.7.7"
cortex-m-rt = "0.7.3"
```

The `features` array selects the exact chip variant. Wrong feature = wrong register map = undefined behavior.

Here's how you actually use a PAC to toggle a GPIO pin:

```rust
// No std, no HAL — just raw PAC access
#![no_std]
#![no_main]

use cortex_m_rt::entry;
use stm32f4::stm32f411;

#[entry]
fn main() -> ! {
    // Take the peripheral singleton (ensures only one instance)
    let peripherals = stm32f411::Peripherals::take().unwrap();
    
    // Get the GPIOA and RCC register blocks
    let gpioa = &peripherals.GPIOA;
    let rcc = &peripherals.RCC;
    
    // Step 1: Enable GPIOA clock (RCC_AHB1ENR bit 0)
    rcc.ahb1enr.modify(|_, w| w.gpioaen().set_bit());
    
    // Step 2: Configure PA5 as output (MODER bits 10-11 = 01)
    gpioa.moder.modify(|_, w| w.moder5().output());
    
    // Step 3: Toggle PA5 by writing to BSRR
    loop {
        // Set PA5 (BS0 = 1)
        gpioa.bsrr.write(|w| w.bs5().set_bit());
        delay(10_000);
        
        // Reset PA5 (BR5 = 1)
        gpioa.bsrr.write(|w| w.br5().set_bit());
        delay(10_000);
    }
}

fn delay(cycles: u32) {
    // Busy-wait loop — real code would use a timer
    for _ in 0..cycles {
        cortex_m::asm::nop();
    }
}
```

Notice the pattern: `modify()` for read-modify-write, `write()` for full register replacement. The closures receive a `W` (writer) token that exposes type-safe bitfield methods. The compiler ensures you can't set a reserved bit or write an invalid value.

For reading registers, use `read()`:

```rust
// Read the input data register
let idr_value = gpioa.idr.read();
let pa5_state = idr_value.idr5().bit_is_set();
// pa5_state is a bool — no manual bit masking
```

## Common Pitfalls & Gotchas

**1. Forgetting to enable peripheral clocks**
This is the #1 mistake. You write perfect register configuration code, but the peripheral never responds because its clock gate is still disabled. Always check the reference manual's clock tree section. For STM32, that's RCC registers. For nRF, it's the CLOCK peripheral. The PAC won't save you here — it just exposes the registers.

**2. Misunderstanding `modify()` vs `write()`**
`modify()` reads the current value, applies your closure, then writes back. This is safe for updating individual bitfields. `write()` overwrites the entire register. Using `write()` on a register with reserved bits can clear hardware state you didn't intend to touch. The PAC's `write()` method actually zeroes all unspecified bits — which is correct for write-only registers like BSRR, but catastrophic for MODER.

**3. PAC features are per-chip, not per-family**
Using `stm32f4` with the `stm32f411` feature gives you exactly the registers for that chip. If you switch to `stm32f405`, the register map changes. Some peripherals have different bit positions or entirely different register layouts. Always regenerate or reselect the PAC when changing silicon revisions.

## Try It Yourself

1. **Read and log the chip ID register** — On STM32F4, that's `DBGMCU.IDCODE`. Read it using `peripherals.DBGMCU.idcode.read()`. Print the bits to understand your silicon revision. This is a safe first exercise because it's read-only.

2. **Toggle two pins simultaneously** — Use the BSRR register to set PA5 and reset PA6 in a single write. The PAC's `bsrr.write()` accepts a closure where you can call both `.bs5().set_bit()` and `.br6().set_bit()`. Verify with a logic analyzer.

3. **Implement a crude software PWM** — Use a PAC timer peripheral (e.g., TIM2) to generate a PWM signal without any HAL. Configure the PSC, ARR, and CCR registers directly. This will teach you why HALs exist — but also give you deep respect for what they abstract.

## Next Up

Tomorrow we'll climb one layer up: **Embedded HAL: The Hardware Abstraction Layer Traits**. We'll see how the `embedded-hal` crate defines portable interfaces for GPIO, I2C, SPI, and serial — and how PACs become the foundation that HAL implementations are built upon.
