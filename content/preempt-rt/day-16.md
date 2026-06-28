---
title: "Day 16: RT Linux for Industrial Control: EtherCAT & Fieldbus"
date: 2026-06-28
tags: ["til", "preempt-rt", "ethercat", "fieldbus", "industrial"]
---

## What I Explored Today

Today I dove into the practical integration of PREEMPT_RT Linux with industrial fieldbus systems, specifically EtherCAT. While many assume that real-time Linux is only for soft real-time applications, the combination of PREEMPT_RT with dedicated EtherCAT master stacks can achieve cycle times below 100 µs—competitive with dedicated FPGA-based solutions. I built a working EtherCAT master on a BeagleBone Black running a 5.10.y-rt kernel, connected to a simple digital I/O slave, and measured jitter under varying loads.

## The Core Concept

Industrial control systems demand deterministic behavior at the fieldbus level. EtherCAT, as a master-slave protocol, relies on the master to send and process Ethernet frames within a precise cycle window. The critical insight is that the master's real-time performance directly determines the minimum achievable cycle time and jitter.

Why PREEMPT_RT matters here: EtherCAT master stacks (like SOEM, IgH EtherCAT Master, or RT-EtherCAT) typically run in userspace or as kernel modules. Without real-time guarantees, the master thread can be preempted by non-real-time processes, causing frame transmission delays that cascade into bus errors or watchdog timeouts. PREEMPT_RT ensures that the EtherCAT master thread runs with deterministic scheduling, even under heavy system load from logging, GUI, or network services.

The real trick is not just enabling PREEMPT_RT—it's pinning the EtherCAT master thread to a dedicated CPU core, setting its scheduling policy to `SCHED_FIFO` with appropriate priority, and isolating that core from kernel housekeeping tasks. This creates a "hard real-time island" for the fieldbus communication while the rest of the system handles non-critical tasks.

## Key Commands / Configuration / Code

### 1. Isolating a CPU Core for EtherCAT

```bash
# Add to kernel boot parameters in /boot/grub/grub.cfg or /boot/extlinux/extlinux.conf
# This isolates CPU core 1 from the scheduler and moves all interrupts off it
isolcpus=1 nohz_full=1 rcu_nocbs=1

# Verify isolation after boot
cat /sys/devices/system/cpu/isolated
# Expected output: 1
```

### 2. Setting Up IgH EtherCAT Master with PREEMPT_RT

```bash
# Install dependencies
sudo apt-get install build-essential linux-headers-$(uname -r) libtool autoconf

# Clone and build IgH EtherCAT master (v1.6.2 tested)
git clone https://gitlab.com/etherlab.org/ethercat.git -b stable-1.6
cd ethercat
./bootstrap
./configure --enable-rt --enable-cycles
make -j$(nproc)
sudo make modules_install install

# Load the module with real-time support
sudo modprobe ec_master main_devices=00:04:9f:00:00:01
# Note: Replace MAC with your EtherCAT slave's address
```

### 3. Pinning the Master Thread with Real-Time Priority

```c
// Example: Setting SCHED_FIFO priority from userspace application
#include <sched.h>
#include <pthread.h>

void setup_rt_thread(pthread_t thread, int priority) {
    struct sched_param param;
    param.sched_priority = priority;
    
    // Set scheduling policy to SCHED_FIFO
    if (pthread_setschedparam(thread, SCHED_FIFO, &param) != 0) {
        perror("Failed to set RT scheduling");
        exit(EXIT_FAILURE);
    }
    
    // Pin to isolated core (CPU 1)
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(1, &cpuset);
    if (pthread_setaffinity_np(thread, sizeof(cpu_set_t), &cpuset) != 0) {
        perror("Failed to pin thread");
        exit(EXIT_FAILURE);
    }
}

// In your EtherCAT master loop:
int main() {
    pthread_t ecat_thread;
    pthread_create(&ecat_thread, NULL, ecat_master_loop, NULL);
    setup_rt_thread(ecat_thread, 80);  // Priority 80 (0-99 range)
    pthread_join(ecat_thread, NULL);
    return 0;
}
```

### 4. Measuring Jitter with Cyclictest While Running EtherCAT

```bash
# Run cyclictest on the isolated core while EtherCAT is active
sudo cyclictest -p 80 -t 1 -a 1 -n -i 1000 -l 100000
# -p 80: priority matches our EtherCAT thread
# -a 1: run on CPU core 1
# -i 1000: interval 1000 µs
# -l 100000: 100,000 iterations

# Expected output with proper configuration:
# T: 0 (0) P:80 I:1000 C:100000 Min: 2 Act: 3 Avg: 4 Max: 12
# Max jitter under 20 µs is typical for a well-configured system
```

## Common Pitfalls & Gotchas

**1. Interrupt Storm from Network Interface**
The Ethernet controller handling EtherCAT frames generates interrupts that can preempt your real-time thread. Always use interrupt coalescing or, better, move the NIC's IRQ affinity to a non-isolated core. Check with `cat /proc/interrupts | grep eth` and adjust via `/proc/irq/<IRQ>/smp_affinity`.

**2. Priority Inversion with Kernel Modules**
If your EtherCAT master runs as a kernel module (IgH's `ec_master`), it inherits the kernel's scheduling context. You must set the module's thread priority via module parameters or `chrt` after loading. Many engineers forget this and wonder why their kernel module doesn't respect userspace RT settings.

**3. Memory Allocation in Real-Time Path**
Calling `malloc()` or `kmalloc()` inside the EtherCAT cycle loop can cause non-deterministic delays due to page faults. Pre-allocate all memory buffers during initialization. Use `mlockall(MCL_CURRENT | MCL_FUTURE)` in userspace to lock pages, or use `GFP_ATOMIC` in kernel modules.

## Try It Yourself

1. **Isolate a core and measure baseline jitter**: Boot your PREEMPT_RT system with `isolcpus=1 nohz_full=1 rcu_nocbs=1`. Run `cyclictest -p 80 -t 1 -a 1 -n -i 500 -l 50000` and record the max jitter. Then add a stress load (`stress --cpu 4`) on the other cores and re-run. Note the difference.

2. **Build and run a minimal EtherCAT master**: Using SOEM (Simple Open EtherCAT Master), compile the `slaveinfo` example. Connect any EtherCAT slave (e.g., a Beckhoff EK1100 coupler with EL2008 digital output). Run `sudo ./slaveinfo eth0` and verify you can read the slave's vendor ID and product code. Measure the cycle time with `perf stat`.

3. **Introduce a real-time violation**: Intentionally run a CPU-intensive task on the isolated core (e.g., `taskset -c 1 stress --cpu 1`). Observe how the EtherCAT master's cycle time jitter increases. Then move the stress to a non-isolated core and confirm jitter returns to baseline. This demonstrates why core isolation is critical.

## Next Up

Tomorrow, I'm benchmarking Zephyr RTOS against PREEMPT_RT Linux on identical hardware—a dual-core ARM Cortex-A72—running a simple periodic task at 10 kHz. We'll compare worst-case latency, jitter, and power consumption. Spoiler: the results might surprise you.
