---
title: "Day 15: Memory Safety at the Boundary: Rust/C FFI in Zephyr Modules"
date: 2026-07-24
tags: ["til", "rust-zephyr-nrf54", "ffi", "memory-safety"]
---

## What I Explored Today

Today I tackled the trickiest part of integrating Rust into an existing Zephyr codebase: the FFI boundary between Rust and C. Specifically, I built a Rust module that wraps the nRF54LM20's SPIM peripheral driver, exposing a safe Rust API while calling the Zephyr C driver underneath. The goal was to ensure that no undefined behavior leaks across the boundary—no dangling pointers, no buffer overruns, no unsound casts. I focused on three concrete patterns: safe wrapper types for C structs, ownership transfer via `Box` and raw pointers, and panic-safe callbacks.

## The Core Concept

The Rust/C FFI boundary is where memory safety guarantees break down. Rust's borrow checker and ownership model don't apply to C code. When you call a C function from Rust, you're responsible for ensuring that:

1. **Pointers are valid** (non-null, properly aligned, pointing to live memory)
2. **Lifetimes are respected** (C code doesn't outlive the data it references)
3. **Data races are prevented** (C code may not be thread-safe)
4. **Panics don't unwind across the boundary** (undefined behavior)

The key insight is to create a **safe abstraction layer** that encapsulates all unsafe operations. This layer should be as thin as possible—ideally one function call deep—so you can audit it thoroughly. Every `unsafe` block must be justified with a safety comment explaining why the invariants hold.

For Zephyr, the most common FFI patterns involve:
- Wrapping Zephyr's device structs (`const struct device *`) in Rust newtypes
- Converting between Rust slices and C pointer+length pairs
- Handling asynchronous callbacks (e.g., SPI transaction completion)

## Key Commands / Configuration / Code

First, I defined the FFI bindings for the Zephyr SPIM driver. I used `bindgen` to generate them, but manually wrapped the critical functions for clarity.

```rust
// src/spim.rs — Safe wrapper around nRF54LM20 SPIM peripheral

use core::ffi::{c_uint, c_void};
use core::ptr::NonNull;

// Opaque handle to the Zephyr device — we never dereference it in Rust
#[repr(transparent)]
pub struct SpimDevice {
    // Zephyr's `const struct device *` is just a pointer to opaque data
    inner: NonNull<c_void>,
}

// Safety: Zephyr guarantees device pointers are valid for the lifetime of the program
unsafe impl Send for SpimDevice {}
unsafe impl Sync for SpimDevice {}

extern "C" {
    // Zephyr's device_get_binding — returns NULL on failure
    fn device_get_binding(name: *const u8) -> *mut c_void;

    // Zephyr's spim_transfer — takes device, config, and buffer descriptors
    fn spim_transfer(
        dev: *const c_void,
        tx_buf: *const u8,
        tx_len: c_uint,
        rx_buf: *mut u8,
        rx_len: c_uint,
    ) -> i32;
}

impl SpimDevice {
    /// Open the SPIM device by devicetree label.
    /// Returns None if the device is not available.
    pub fn open(label: &str) -> Option<Self> {
        // Convert Rust string to C string (null-terminated)
        let c_str = core::ffi::CString::new(label).ok()?;
        let ptr = unsafe { device_get_binding(c_str.as_ptr()) };
        NonNull::new(ptr).map(|inner| SpimDevice { inner })
    }

    /// Perform a synchronous SPI transfer.
    /// Takes a mutable slice for rx_buf to allow safe mutation.
    /// Returns 0 on success, negative errno on failure.
    pub fn transfer(
        &self,
        tx_buf: &[u8],
        rx_buf: &mut [u8],
    ) -> Result<(), i32> {
        // Safety: Both slices are valid for the duration of the call.
        // The C function will not retain pointers after returning.
        let ret = unsafe {
            spim_transfer(
                self.inner.as_ptr(),
                tx_buf.as_ptr(),
                tx_buf.len() as c_uint,
                rx_buf.as_mut_ptr(),
                rx_buf.len() as c_uint,
            )
        };
        if ret == 0 {
            Ok(())
        } else {
            Err(ret)
        }
    }
}
```

The critical safety invariants:
- `device_get_binding` returns a pointer valid for the program's lifetime (Zephyr guarantees this)
- `spim_transfer` is synchronous — it blocks until the transfer completes, so the slices are only borrowed temporarily
- The `Send`/`Sync` impls are safe because Zephyr's device structs are global singletons

For the callback-based API (asynchronous), I used a `Box<dyn FnOnce>` stored in a static mut, protected by a critical section:

```rust
use core::sync::atomic::{AtomicBool, Ordering};

static CALLBACK_PENDING: AtomicBool = AtomicBool::new(false);
static mut CALLBACK: Option<Box<dyn FnOnce(i32)>> = None;

extern "C" fn spim_callback_wrapper(_dev: *const c_void, result: i32) {
    // Safety: Called from Zephyr's interrupt context, single-threaded
    unsafe {
        if let Some(cb) = CALLBACK.take() {
            cb(result);
        }
    }
    CALLBACK_PENDING.store(false, Ordering::Release);
}
```

## Common Pitfalls & Gotchas

1. **Zephyr's device tree labels are not Rust strings.** The label passed to `device_get_binding` must be a null-terminated C string. Using `&str` directly will cause buffer overruns. Always use `CString` or `CStr` for conversion.

2. **Slices must not be aliased.** If you pass the same buffer for both TX and RX (half-duplex), ensure the slices don't overlap. Zephyr's SPIM driver expects distinct buffers; passing overlapping slices is undefined behavior. Use `split_at_mut` or separate allocations.

3. **Panic in a C callback = UB.** If a Rust callback panics and the panic handler tries to unwind across the FFI boundary, the behavior is undefined. Wrap all callback bodies in `catch_unwind` or use `#[panic_handler]` that aborts. For Zephyr, I use a custom panic handler that logs and then loops forever.

## Try It Yourself

1. **Wrap another Zephyr peripheral** (e.g., UART or I2C) using the same pattern. Create a safe `UartDevice` struct that calls `uart_fifo_fill` and `uart_fifo_read`. Verify that the C function signatures match your Rust declarations.

2. **Add a lifetime parameter** to `SpimDevice::transfer` that ties the borrow to the device handle. This prevents the user from dropping the device while a transfer is in progress. Hint: use `&'a self` and `&'a [u8]`.

3. **Implement a zero-copy transfer** using Zephyr's `spim_transfer_async` with a completion callback. Store the callback in a `static mut` and use a critical section (e.g., `cortex_m::interrupt::free`) to safely set and clear it.

## Next Up

Tomorrow I'll tackle **Logging & Debugging: defmt/RTT with Zephyr on nRF54LM20**. We'll integrate the `defmt` logging framework with Zephyr's RTT backend, enabling real-time, low-overhead debug output without a UART.
