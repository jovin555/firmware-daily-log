---
title: "Day 19: Writing a Linux Kernel Driver in Rust: CharDev Example"
date: 2026-07-01
tags: ["til", "rust-embedded", "chardev", "driver", "kernel"]
---

## What I Explored Today

Today I took the plunge into writing a real Linux kernel character device driver using Rust. After weeks of building confidence with `no_std` firmware and RTIC applications, I wanted to see how Rust's safety guarantees translate when you're operating in the kernel's address space—where a single null pointer dereference means a system panic, not just a segfault. I used the `kernel` crate from the Rust-for-Linux project, targeting kernel 6.1 LTS, and built a minimal `/dev/rustchardev` that accepts writes and echoes them back on read.

## The Core Concept

Writing a kernel driver in Rust isn't just about using `unsafe` less often—it's about encoding the kernel's implicit contract into the type system. In C, a character device driver requires you to manually manage file operations, reference counts, and memory allocations, all while praying you don't miss a `put_user` or forget to unlock a mutex. Rust's ownership model and the `kernel` crate's abstractions turn many of these runtime checks into compile-time guarantees.

The key abstraction is the `kernel::chrdev::Registration` type, which wraps the kernel's `cdev` and `dev_t` allocation. When you register a character device, the kernel expects you to provide a `file_operations` struct. In Rust, you implement the `kernel::file_ops::FileOperations` trait, which gives you methods like `read`, `write`, `open`, and `release`. The safety boundary is clear: the trait methods receive references to `kernel::file::File` and `kernel::file::FileContext`, which are safe wrappers around the kernel's `struct file` and `struct inode`.

The real win comes with memory safety. In C, you'd use `copy_to_user` and `copy_from_user` with raw pointers, and if you get the buffer size wrong, you corrupt user space memory. In Rust, the `kernel::user_ptr::UserSlicePtrWriter` and `UserSlicePtrReader` types handle these operations with bounds checking. The compiler ensures you never write past the buffer—something that's impossible to guarantee in C without static analysis tools.

## Key Commands / Configuration / Code

First, ensure you have the Rust-for-Linux toolchain. I'm using kernel 6.1 with the `rust` branch:

```bash
# Clone the kernel source with Rust support
git clone --depth=1 -b rust https://github.com/Rust-for-Linux/linux.git
cd linux
make rustavailable  # should print "Rust is available!"
```

Configure the kernel to enable Rust support:

```bash
make LLVM=1 menuconfig
# Navigate to:
#   Kernel hacking -> Rust support -> Enable Rust support
#   Device Drivers -> Character devices -> <M> Rust character device example
```

Now, the driver code. Create `samples/rust/rust_chrdev.rs`:

```rust
// SPDX-License-Identifier: GPL-2.0
//! A simple character device driver in Rust.

use kernel::prelude::*;
use kernel::chrdev;
use kernel::file_operations::{FileOperations, File, FileContext};
use kernel::user_ptr::UserSlicePtrWriter;

module! {
    type: RustCharDev,
    name: "rust_chardev",
    author: "Your Name",
    description: "A Rust character device driver",
    license: "GPL",
}

struct RustCharDev {
    _dev: Pin<Box<chrdev::Registration<Self>>>,
}

// The buffer shared between open instances (simplified for demo)
struct MyDevice {
    data: [u8; 256],
    len: usize,
}

#[vtable]
impl FileOperations for MyDevice {
    type Wrapper = Pin<Box<Self>>;

    fn open(_file: &File, _context: &FileContext) -> Result<Pin<Box<Self>>> {
        // Allocate and return a new device instance
        let dev = Box::pin_init(MyDevice {
            data: [0u8; 256],
            len: 0,
        })?;
        pr_info!("rust_chardev: opened\n");
        Ok(dev)
    }

    fn write(
        this: &Self,
        _file: &File,
        reader: &mut kernel::user_ptr::UserSlicePtrReader,
        _offset: u64,
    ) -> Result<usize> {
        // Read up to 256 bytes from user space
        let len = reader.read_slice(&mut this.data)?;
        pr_info!("rust_chardev: wrote {} bytes\n", len);
        Ok(len)
    }

    fn read(
        this: &Self,
        _file: &File,
        writer: &mut UserSlicePtrWriter,
        _offset: u64,
    ) -> Result<usize> {
        // Write back what we stored
        let slice = &this.data[..this.len];
        writer.write_slice(slice)?;
        Ok(this.len)
    }
}

impl kernel::Module for RustCharDev {
    fn init(module: &'static ThisModule) -> Result<Self> {
        pr_info!("rust_chardev: loading\n");

        // Allocate a character device region with one minor number
        let dev = chrdev::Registration::new_module(
            "rustchardev",
            module,
            // Major number 0 means kernel allocates dynamically
            0..=0,
        )?;

        Ok(RustCharDev { _dev: dev })
    }
}
```

Build and test:

```bash
make LLVM=1 -j$(nproc)
# Load the module
sudo insmod samples/rust/rust_chrdev.ko
# Check device node (should be /dev/rustchardev)
ls -l /dev/rustchardev
# Test write/read
echo "Hello from Rust" | sudo tee /dev/rustchardev
sudo cat /dev/rustchardev
# Should print: Hello from Rust
```

## Common Pitfalls & Gotchas

1. **The `#[vtable]` macro is mandatory**: If you forget the `#[vtable]` attribute on your `FileOperations` impl, the compiler will give you a cryptic error about missing `Vtable` associated type. This macro generates the vtable structure that the kernel's C code expects. Without it, the `chrdev::Registration` won't compile.

2. **User space buffer sizes are checked at compile time**: The `UserSlicePtrWriter::write_slice` method takes a reference to a fixed-size array. If you try to write more bytes than the user space buffer can hold, the kernel will return `-EFAULT` at runtime. But the real gotcha is that you must ensure your internal buffer doesn't overflow—the `read_slice` method returns the actual number of bytes read, which you must store separately (as I did with `len`).

3. **Module parameters need explicit types**: Unlike C where you can use `module_param` with any type, Rust's `kernel::module` macro requires you to use specific wrapper types like `kernel::module_param::ArrayParam` for arrays. If you try to pass a raw `&str` as a parameter, the build will fail with a type mismatch. Always check the `kernel::module_param` module for available types.

## Try It Yourself

1. **Add an ioctl handler**: Extend the driver to support a custom ioctl command (e.g., `RUST_CHARDEV_CLEAR`) that resets the internal buffer. You'll need to implement the `ioctl` method in `FileOperations` and use `kernel::ioctl` macros.

2. **Implement concurrent access**: The current driver has no locking—if two processes write simultaneously, they'll corrupt the buffer. Add a `kernel::sync::Mutex` to protect the `MyDevice` struct. Hint: you'll need to wrap `MyDevice` in `Arc<Mutex<MyDevice>>` and adjust the `Wrapper` type.

3. **Add a module parameter**: Introduce a `max_size` parameter (default 256) that limits the maximum buffer size. Use `kernel::module_param::u32` and check it in the `open` method to allocate a buffer of that size dynamically.

## Next Up

Tomorrow, I'll compare this Rust driver side-by-side with an equivalent C implementation. We'll examine the exact same functionality—open, read, write, ioctl—and see where Rust's safety guarantees eliminate entire classes of bugs (use-after-free, missing locking, buffer overflows) and where the trade-offs (compile times, kernel version compatibility, ecosystem maturity) still bite. It's not a one-sided victory, and understanding the gaps is crucial for deciding when to use Rust in kernel development.
