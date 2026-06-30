---
title: "Day 18: Rust in the Linux Kernel: rust_module! Basics (v6.1+)"
date: 2026-06-30
tags: ["til", "rust-embedded", "kernel", "rust", "module"]
---

## What I Explored Today

Today I finally dug into the `rust_module!` macro that landed in Linux kernel v6.1, which provides the foundation for writing kernel modules entirely in Rust. After months of writing C kernel modules, I wanted to understand how Rust's safety guarantees translate into the kernel's demanding environment. The `rust_module!` macro is the entry point—it handles module initialization, cleanup, and parameter registration with the kernel's module infrastructure, all while maintaining Rust's ownership and lifetime semantics.

## The Core Concept

The `rust_module!` macro is not just syntactic sugar—it's a carefully designed abstraction that bridges Rust's module system with the Linux kernel's C-based module loading/unloading mechanism. When you call `insmod` or `modprobe`, the kernel expects specific C symbols: `init_module` and `cleanup_module` (or their `module_init`/`module_exit` equivalents). The `rust_module!` macro generates these symbols from your Rust code, wrapping them in `unsafe` blocks that call your safe Rust functions.

Why does this matter? In C kernel modules, you manually manage every aspect of initialization—allocating resources, registering with subsystems, and ensuring cleanup happens on every error path. Rust's `rust_module!` macro enforces a structured initialization pattern: you define a struct that holds your module's state, and the macro ensures that `drop` is called on that struct when the module is unloaded. This means Rust's RAII (Resource Acquisition Is Initialization) pattern works even in kernel space, eliminating entire classes of memory leaks and use-after-free bugs that plague C modules.

The macro also integrates with the kernel's module parameter system. You can declare parameters that userspace can set via `modprobe` or `/sys/module/<name>/parameters/`, and Rust's type system ensures they're properly validated before your module code runs.

## Key Commands / Configuration / Code

First, ensure your kernel is built with Rust support. You need a v6.1+ kernel configured with:

```bash
# In your kernel source tree
make LLVM=1 menuconfig
# Navigate to:
#   General setup -> Rust support (enable)
#   Device Drivers -> Rust support -> Enable Rust modules
```

A minimal Rust kernel module looks like this:

```rust
// SPDX-License-Identifier: GPL-2.0
//! My first Rust kernel module

use kernel::prelude::*;

module! {
    type: MyModule,
    name: "my_rust_module",
    author: "Your Name",
    description: "A minimal Rust kernel module",
    license: "GPL",
    params: {
        count: u32 {
            default: 42,
            permissions: 0o644,
            description: "Number of iterations",
        },
    },
}

struct MyModule {
    count: u32,
}

impl kernel::Module for MyModule {
    fn init(module: &'static ThisModule) -> Result<Self> {
        pr_info!("Hello from Rust kernel module!\n");
        pr_info!("Count parameter: {}\n", module.count);
        Ok(MyModule { count: module.count })
    }
}

impl Drop for MyModule {
    fn drop(&mut self) {
        pr_info!("Goodbye from Rust kernel module (count was {})!\n", self.count);
    }
}
```

Build it from your kernel tree:

```bash
# Build the module
make LLVM=1 M=samples/rust/ modules

# Or build your custom module directory
make LLVM=1 M=/path/to/your/module modules

# Load it
sudo insmod my_rust_module.ko count=100

# Check kernel log
dmesg | tail -5

# Unload
sudo rmmod my_rust_module
```

The `module!` macro expands to generate:
- `init_module()` and `cleanup_module()` C symbols
- Module parameter registration via `module_param_named`
- A `THIS_MODULE` reference for your `init` function
- Proper `unsafe` wrappers around kernel C APIs

## Common Pitfalls & Gotchas

1. **Missing `kernel::prelude::*` import**: The `pr_info!`, `pr_err!`, and other kernel macros are in the prelude. Forgetting this import leads to confusing "macro not found" errors that don't point to the real issue. Always start your module with `use kernel::prelude::*;`.

2. **Module type must be `'static`**: The `init` function receives `&'static ThisModule`, but your `Module` implementation must not borrow from it beyond initialization. The `ThisModule` reference is only valid during `init`. Store any needed parameters in your struct by value, not by reference.

3. **Parameter permissions are octal, not decimal**: The `permissions` field in `params` uses standard Unix file permissions in octal. `0o644` means readable by all, writable by root. Using decimal `644` will give unexpected permissions (0o1204), which may prevent userspace from reading the parameter.

## Try It Yourself

1. **Extend the parameter set**: Add a `name: String` parameter to the module above. Print it during initialization. Remember that kernel string parameters have a maximum length (typically 1024 bytes). Use `kernel::params::StringParam` for safe handling.

2. **Add a timer**: Modify the module to start a kernel timer on init that prints a message every 5 seconds. Use `kernel::timer::Timer` from the Rust kernel API. Ensure the timer is cancelled in `drop` to prevent use-after-free.

3. **Create a parameter-dependent behavior**: Add a boolean parameter `verbose: bool` that controls whether the module prints extra debug messages. Use `pr_debug!` for verbose messages and `pr_info!` for standard ones. Verify with `dmesg` that the behavior changes based on the parameter value.

## Next Up

Tomorrow, I'll build on this foundation and write a full character device driver in Rust—complete with `open`, `read`, `write`, and `release` operations, demonstrating how Rust's ownership model prevents the classic "driver forgot to lock" bugs that plague C char drivers. We'll register with the kernel's file operations table and handle userspace I/O safely.
