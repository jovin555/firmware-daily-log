---
title: "Day 15: eBPF Maps: Hash, Array, Ring Buffer & Perf Events"
date: 2026-06-27
tags: ["til", "ebpf", "maps", "ring-buffer"]
---

## What I Explored Today

Today I went deep into eBPF maps — the data structures that bridge kernel and user space. I've used maps before, but never systematically compared the four most common types: hash maps, array maps, ring buffers, and perf event arrays. I built a small tracing tool that uses each type for a different purpose, and the performance differences were stark. Ring buffers, in particular, are a game-changer for high-throughput observability.

## The Core Concept

eBPF maps are the only way to persist state across eBPF program invocations and to communicate with user space. Without maps, each eBPF program runs in isolation — no memory, no context, no output. The kernel provides a map API (`bpf_map_lookup_elem`, `bpf_map_update_elem`, etc.) that works from both kernel-side eBPF programs and user-space loader tools.

The *why* matters here. Choosing the wrong map type causes data loss, performance cliffs, or excessive memory. Hash maps are flexible but have lookup overhead. Array maps are fixed-size but O(1) and pre-allocated. Perf event arrays were the original high-throughput channel, but they require per-CPU buffers and complex user-space parsing. Ring buffers (introduced in Linux 5.8) solve this with a single shared buffer, adaptive reservation, and zero-copy semantics — they're now the recommended path for most event streaming.

## Key Commands / Configuration / Code

I wrote a small C program that attaches a kprobe to `do_sys_openat2` and uses all four map types. Here's the kernel-side snippet with inline comments:

```c
// Kernel-side eBPF program (pseudo-code, compiled with clang -target bpf)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, u32);    // PID
    __type(value, u64);  // count
} open_counts SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 4);  // one slot per severity
    __type(key, u32);
    __type(value, u64);
} severity_counts SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 24);  // 16MB buffer
} events_ring SEC(".maps");

struct event {
    u32 pid;
    u32 uid;
    char comm[16];
    char filename[256];
};

SEC("kprobe/do_sys_openat2")
int trace_open(struct pt_regs *ctx)
{
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u32 uid = bpf_get_current_uid_gid() & 0xFFFFFFFF;

    // Hash map: count opens per PID
    u64 *count = bpf_map_lookup_elem(&open_counts, &pid);
    u64 new_count = count ? (*count + 1) : 1;
    bpf_map_update_elem(&open_counts, &pid, &new_count, BPF_ANY);

    // Array map: increment severity bucket (0=info, 1=warn, etc.)
    u32 key = 0;  // info bucket
    u64 *sev = bpf_map_lookup_elem(&severity_counts, &key);
    if (sev) {
        __sync_fetch_and_add(sev, 1);
    }

    // Ring buffer: emit full event struct
    struct event *e = bpf_ringbuf_reserve(&events_ring, sizeof(*e), 0);
    if (!e) return 0;  // buffer full, drop silently
    e->pid = pid;
    e->uid = uid;
    bpf_get_current_comm(&e->comm, sizeof(e->comm));
    bpf_probe_read_user_str(&e->filename, sizeof(e->filename),
        (void *)PT_REGS_PARM2(ctx));
    bpf_ringbuf_submit(e, 0);
    return 0;
}
```

User-space reading (using libbpf's ring buffer API):

```c
// User-space consumer (simplified)
int handle_event(void *ctx, void *data, size_t len) {
    struct event *e = (struct event *)data;
    printf("PID=%d UID=%d COMM=%s FILE=%s\n",
           e->pid, e->uid, e->comm, e->filename);
    return 0;
}

struct ring_buffer *rb = ring_buffer__new(bpf_map__fd(skel->maps.events_ring),
                                          handle_event, NULL, NULL);
while (1) {
    ring_buffer__consume(rb);  // non-blocking poll
    // or ring_buffer__poll(rb, timeout_ms) for blocking
}
```

To compile and run:
```bash
clang -O2 -target bpf -c tracer.bpf.c -o tracer.bpf.o
bpftool gen skeleton tracer.bpf.o > tracer.skel.h
gcc -o tracer tracer.c -lbpf -lelf -lz
sudo ./tracer
```

For perf event arrays (legacy but still common in older codebases):
```c
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u32));
    __uint(max_entries, 64);  // max CPUs
} perf_events SEC(".maps");

// In kprobe: bpf_perf_event_output(ctx, &perf_events, BPF_F_CURRENT_CPU,
//                                  &event, sizeof(event));
```

## Common Pitfalls & Gotchas

1. **Ring buffer reservation failures are silent.** If `bpf_ringbuf_reserve` returns NULL, your event is dropped. Always check the return value. Many beginners skip this and corrupt memory. The kernel won't warn you.

2. **Hash map key/value sizes must be exact.** A common mistake: using a `u32` key in the C struct but passing a `u64` from user space. The map lookup silently returns NULL. Always verify `key_size` and `value_size` in your map definition match your actual data.

3. **Perf event arrays require per-CPU buffer setup.** Unlike ring buffers, you must explicitly open a perf event file descriptor for each CPU and pass it to `bpf_perf_event_output`. This is error-prone and wastes memory on idle CPUs. Ring buffers handle this transparently.

4. **Array maps are pre-allocated at load time.** You cannot resize them. The `max_entries` is fixed. If you need dynamic sizing, use a hash map or a percpu array variant.

## Try It Yourself

1. **Modify the ring buffer size.** Change `max_entries` to `1 << 20` (1MB) and run a heavy file-open workload (e.g., `find /usr -type f`). Observe dropped events via `bpftool map show`. Then increase to `1 << 26` (64MB) and compare.

2. **Replace ring buffer with perf event array.** Rewrite the `events_ring` map as `BPF_MAP_TYPE_PERF_EVENT_ARRAY`. Update the kprobe to use `bpf_perf_event_output`. Measure throughput with `perf stat` — you'll see higher CPU usage due to per-CPU interrupt handling.

3. **Add a hash map lookup from user space.** After loading the program, use `bpftool map lookup` to read `open_counts` for PID 1234. Then write a small Python script using `ctypes` to call `bpf_map_lookup_elem` via the `bpf()` syscall.

## Next Up

Tomorrow I'll tackle **libbpf & CO-RE: Portable eBPF Programs in C** — how to write a single eBPF binary that runs across kernel versions without recompilation, using BTF and relocation records. No more hardcoded field offsets.
