---
title: "Day 14: Memory Management: Placement new & Static Pools"
date: 2026-06-26
tags: ["til", "cpp-embedded", "placement-new", "pool", "static"]
---

## What I Explored Today

Today I dug into placement `new` and static memory pools — two techniques that let us control *where* objects live in memory, bypassing the heap entirely. On embedded targets with 64 KB of RAM or less, dynamic allocation via `malloc`/`new` is often banned in coding standards (MISRA, AUTOSAR). Placement `new` gives us back object construction without allocation, and static pools give us deterministic, O(1) allocation for fixed-size blocks. I implemented a small pool allocator for a CAN message buffer and confirmed it works with `-fno-exceptions` and no heap.

## The Core Concept

The standard `new` expression does two things: it allocates memory (usually from the heap) and then constructs the object in that memory. In embedded systems, we often want to separate these steps. Placement `new` is a language feature that lets you construct an object at a specific memory address you already own — no allocation happens.

Why would you want this? Three reasons:

1. **Determinism** — Heap allocation has unpredictable latency (worst-case O(n) for some allocators). A static pool gives you O(1) allocation and deallocation.
2. **No fragmentation** — Fixed-size blocks in a pool never fragment. You can prove the system will never run out of memory if you size the pool correctly at compile time.
3. **Real-time safety** — No locks needed if the pool is per-core or accessed from a single thread. No `malloc` calls that might trigger a context switch or page fault.

The pattern is: pre-allocate a chunk of static memory (an array of `std::byte` or `uint8_t`), then use placement `new` to construct objects into slots of that array. When done, call the destructor explicitly (`obj->~T()`) — placement `new` has no corresponding placement `delete`.

## Key Commands / Configuration / Code

Here's a static pool for CAN message objects (32 bytes each, 16 slots):

```cpp
#include <cstdint>
#include <new> // for placement new

// CAN frame structure (compact, no virtual functions)
struct CanFrame {
    uint32_t id;
    uint8_t  data[8];
    uint8_t  dlc;
    uint8_t  flags;
    
    void clear() { id = 0; dlc = 0; flags = 0; }
};

// Static pool — all memory is in BSS, no heap
class StaticPool {
    static constexpr size_t kBlockSize = sizeof(CanFrame);
    static constexpr size_t kNumBlocks = 16;
    
    // Aligned storage — ensures proper alignment for any object up to kBlockSize
    alignas(alignof(CanFrame)) std::byte storage_[kBlockSize * kNumBlocks];
    
    // Bitmap: 1 = free, 0 = allocated. 16 bits fits in uint16_t.
    uint16_t free_mask_ = 0xFFFF;

public:
    void* allocate() {
        if (free_mask_ == 0) return nullptr; // pool exhausted
        
        // Find first free slot (GCC/Clang builtin, single instruction)
        int slot = __builtin_ctz(free_mask_);  // count trailing zeros
        free_mask_ &= ~(1U << slot);           // mark as used
        return &storage_[slot * kBlockSize];
    }
    
    void deallocate(void* ptr) {
        if (!ptr) return;
        size_t slot = (static_cast<std::byte*>(ptr) - storage_) / kBlockSize;
        free_mask_ |= (1U << slot);            // mark as free
    }
    
    // Construct an object in a pre-allocated slot
    template<typename T, typename... Args>
    T* construct(Args&&... args) {
        void* slot = allocate();
        if (!slot) return nullptr;
        return ::new (slot) T(std::forward<Args>(args)...);
    }
    
    // Destroy an object (must call destructor explicitly)
    template<typename T>
    void destroy(T* obj) {
        if (!obj) return;
        obj->~T();              // explicit destructor call
        deallocate(obj);
    }
};

// Usage example
StaticPool can_pool;

void handle_can_interrupt() {
    CanFrame* frame = can_pool.construct<CanFrame>();
    if (frame) {
        frame->id = 0x123;
        frame->dlc = 8;
        // ... fill data ...
        // Later, when done:
        can_pool.destroy(frame);
    }
}
```

Key points in the code:
- `alignas(alignof(CanFrame))` ensures the storage is aligned for any object up to `kBlockSize`.
- `__builtin_ctz` is a single-cycle instruction on ARM (CLZ) and x86 (BSF/TZCNT). No loop.
- `::new (slot) T(...)` — the global scope resolution `::` prevents picking up a class-specific `operator new`.
- Destructor is called manually: `obj->~T()`. There is no `delete` for placement `new`.

## Common Pitfalls & Gotchas

1. **Forgetting to call the destructor** — Placement `new` does not pair with `delete`. If you call `delete` on a placement-constructed object, you'll invoke `operator delete(void*)` on the address, which typically calls `free()` — corrupting your pool. Always call `obj->~T()` explicitly, then return the memory to the pool.

2. **Alignment mismatches** — If your pool storage is aligned to `max_align_t` (usually 8 or 16 bytes) but you construct an object with `alignof(T) > alignof(storage)`, you get undefined behavior. For example, a `std::uint64_t` on a 32-bit platform might require 8-byte alignment. Always use `alignas(alignof(T))` or `alignas(std::max_align_t)` on the storage array.

3. **Exception safety** — If `T`'s constructor throws, the pool slot is already marked as allocated. The standard says placement `new` does not deallocate on exception. You must catch the exception and manually deallocate the slot. In embedded systems with `-fno-exceptions`, this is moot — constructors must not throw.

4. **Array placement new** — `::new (buffer) T[10]` does *not* work as expected. The compiler may store array metadata (like element count) before the array, overwriting adjacent pool slots. Never use array placement `new` with pools. Construct elements one at a time in a loop.

## Try It Yourself

1. **Extend the pool for variable-size blocks** — Modify `StaticPool` to handle two block sizes (e.g., 32 bytes and 64 bytes) using separate pools. Implement `allocate(size_t size)` that dispatches to the correct pool.

2. **Add a free-list instead of a bitmap** — Replace the `free_mask_` with a singly-linked free list stored in the free slots themselves (intrusive). Compare the code size and speed on your target MCU.

3. **Instrument with a watchdog** — Add a compile-time counter `static_assert(kNumBlocks * kBlockSize < 1024)` to prevent accidental large pools. Then add a runtime counter that triggers a fault handler if `allocate()` returns `nullptr` more than 3 times in a row (indicates pool sizing error).

## Next up

Tomorrow we'll look at **C++ in Zephyr: Enabling & Writing C++ Drivers** — how to configure the Zephyr build system for C++, write driver classes that inherit from Zephyr device structs, and handle the interrupt-to-method dispatch pattern that makes C++ drivers actually practical in a real-time OS.
