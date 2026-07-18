---
title: "Day 09: Zephyr Kernel Objects from Rust: Threads, Semaphores & Mutexes"
date: 2026-07-18
tags: ["til", "rust-zephyr-nrf54", "threads", "semaphores"]
---

## What I Explored Today

Today I bridged the gap between Zephyr's C-based kernel API and Rust's ownership model by implementing threads, semaphores, and mutexes on the nRF54LM20. While Zephyr's kernel objects are designed for C's manual memory management, Rust's type system introduces both safety guarantees and friction points. I built a minimal cooperative scheduler pattern using `k_thread`, `k_sem`, and `k_mutex` — all called through FFI bindings — and discovered that the real challenge isn't the API calls themselves, but managing lifetimes and preventing deadlocks when Rust's borrow checker meets Zephyr's preemptive threading.

## The Core Concept

Zephyr's kernel objects are fundamentally global, mutable state — exactly what Rust's ownership model tries to prevent. A `k_sem` lives in a static allocation, accessible from any thread context. Rust wants each resource to have a single owner. The reconciliation strategy: wrap kernel objects in `unsafe`-free abstractions that enforce correct usage at compile time, while acknowledging that Zephyr's scheduler can preempt your Rust code at any instruction.

The key insight is that Zephyr's mutex (`k_mutex`) is *not* Rust's `std::sync::Mutex`. Zephyr's mutex is a priority-inheritance-aware kernel primitive that can suspend the calling thread. Rust's mutex is a spinlock for short critical sections. You cannot simply `#![no_std]`-wrap one into the other — they serve different purposes. Zephyr mutexes protect resources across thread yields; Rust mutexes protect data from concurrent access within a single thread pool. Today I learned to treat them as complementary, not equivalent.

## Key Commands / Configuration / Code

### 1. Defining a Zephyr Thread in Rust

First, the thread stack must be statically allocated with proper alignment. Zephyr requires `K_THREAD_STACK_SIZEOF` alignment, which is 8 bytes on ARM Cortex-M.

```rust
// src/main.rs
use core::mem::MaybeUninit;
use zephyr_sys::*;  // generated bindings

// Stack must be 8-byte aligned for Zephyr's stack checking
#[repr(C, align(8))]
struct ThreadStack([u8; 2048]);

static mut THREAD_STACK: ThreadStack = ThreadStack([0u8; 2048]);
static mut THREAD_DATA: MaybeUninit<k_thread> = MaybeUninit::uninit();

// Thread entry point — must be extern "C" for Zephyr's scheduler
extern "C" fn worker_thread(_arg1: *mut c_void, _arg2: *mut c_void, _arg3: *mut c_void) {
    loop {
        // Zephyr's k_sleep is safe to call from any context
        unsafe { k_sleep(K_MSEC(1000)) };
        // ... do work
    }
}

pub fn start_worker() {
    unsafe {
        k_thread_create(
            THREAD_DATA.as_mut_ptr(),
            THREAD_STACK.0.as_mut_ptr() as *mut c_void,
            2048,
            Some(worker_thread),
            core::ptr::null_mut(),
            core::ptr::null_mut(),
            core::ptr::null_mut(),
            5, // priority (lower = higher priority)
            0, // options
            K_MSEC(0), // no delay
        );
        k_thread_name_set(THREAD_DATA.as_mut_ptr(), c"worker".as_ptr());
    }
}
```

### 2. Safe Semaphore Wrapper

The trick is to use Rust's lifetime system to prevent use-after-free while the semaphore is in use.

```rust
pub struct Semaphore {
    inner: k_sem,
}

impl Semaphore {
    pub fn new() -> Self {
        let mut sem = k_sem {
            // k_sem fields are opaque; zero-initialize
            ..unsafe { core::mem::zeroed() }
        };
        unsafe {
            k_sem_init(&mut sem, 0, 1); // binary semaphore
        }
        Semaphore { inner: sem }
    }

    pub fn give(&mut self) {
        unsafe { k_sem_give(&mut self.inner) };
    }

    pub fn take(&mut self, timeout: k_timeout_t) -> bool {
        unsafe { k_sem_take(&mut self.inner, timeout) == 0 }
    }
}
```

### 3. Mutex with Priority Inheritance

Zephyr's mutexes automatically handle priority inheritance — a critical feature for real-time systems that Rust's standard library lacks.

```rust
pub struct Mutex {
    inner: k_mutex,
}

impl Mutex {
    pub fn new() -> Self {
        let mut mtx = unsafe { core::mem::zeroed() };
        unsafe { k_mutex_init(&mut mtx) };
        Mutex { inner: mtx }
    }

    pub fn lock(&mut self) {
        unsafe { k_mutex_lock(&mut self.inner, K_FOREVER) };
    }

    pub fn unlock(&mut self) {
        unsafe { k_mutex_unlock(&mut self.inner) };
    }
}
```

## Common Pitfalls & Gotchas

### 1. Stack Overflow Detection is Off by Default
Zephyr's stack sentinel (`CONFIG_STACK_SENTINEL`) is disabled in many default configurations. If your Rust thread overflows its 2048-byte stack, you'll get silent corruption, not a panic. Always enable `CONFIG_STACK_SENTINEL=y` in your `prj.conf` during development, and consider using Zephyr's `K_THREAD_STACK_DEFINE` macro via FFI for proper guard pages.

### 2. Rust's Drop vs Zephyr's Deallocation
You cannot implement `Drop` for a Zephyr mutex that calls `k_mutex_unlock` — the mutex may be locked by a different thread. Rust's `Drop` runs on the current thread's stack unwind, which is exactly the wrong place to release a kernel mutex. Instead, use explicit `lock()`/`unlock()` pairs and never rely on RAII for Zephyr kernel objects.

### 3. The `extern "C"` Trap
Your thread entry function must be `extern "C"` and have the exact signature `fn(*mut c_void, *mut c_void, *mut c_void)`. If you accidentally use `extern "Rust"`, Zephyr's scheduler will jump to garbage — no compiler warning, just a hard fault. I lost an hour to this. Always double-check the function pointer type in `k_thread_create`.

## Try It Yourself

1. **Implement a producer-consumer pattern**: Create two threads sharing a `k_sem`. One thread increments a counter and calls `k_sem_give`; the other waits on `k_sem_take` and prints the counter. Use `k_sleep` to control timing. Observe the output on your serial console.

2. **Measure priority inheritance**: Create three threads at priorities 1, 2, and 3. The lowest-priority thread locks a `k_mutex` and then sleeps. The middle thread tries to lock the same mutex. Verify (via `k_thread_priority_get`) that the low-priority thread inherits the middle thread's priority while holding the mutex.

3. **Break the RAII pattern**: Write a wrapper that implements `Drop` for `k_mutex` by calling `k_mutex_unlock`. Spawn a thread that panics while holding the mutex. Observe the resulting deadlock — then refactor to use explicit lock/unlock with a `Result` return.

## Next Up

Tomorrow: **Interrupt Handling: Rust ISRs in a Zephyr Context**. We'll wire up a GPIO interrupt on the nRF54LM20, write the ISR in Rust, and tackle the challenge of sharing data between interrupt context and thread context without `static mut` hacks.
