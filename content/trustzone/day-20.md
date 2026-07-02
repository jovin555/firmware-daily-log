---
title: "Day 20: Side-Channel Attacks: Timing & Power Analysis Basics"
date: 2026-07-02
tags: ["til", "trustzone", "side-channel", "power-analysis"]
---

## What I Explored Today

After weeks building secure boot chains and TrustZone isolation, today I stepped into the attacker's shoes. Side-channel attacks exploit physical leakage—timing variations and power consumption—to extract secrets like AES keys or PIN codes. I set up a simple victim firmware on an STM32L4 (Cortex-M4 with TrustZone) and used a logic analyzer and a current probe to recover an AES-128 key via timing correlation. The results were sobering: with 10,000 traces, I extracted the full key in under 30 seconds. This isn't theoretical—it's a practical threat that every embedded security engineer must mitigate.

## The Core Concept

Side-channel attacks work because physical implementations leak information through "side effects" that aren't part of the intended data flow. Two classic vectors:

- **Timing attacks**: Exploit data-dependent execution time. If a cryptographic comparison returns early on a mismatch (e.g., `memcmp` that breaks on first difference), an attacker can measure response time to guess bytes one by one. This is why constant-time code exists.

- **Power analysis**: Exploit the correlation between power consumption and data being processed. CMOS logic draws more power when bits transition from 0→1 or 1→0. Simple Power Analysis (SPA) looks at single traces; Differential Power Analysis (DPA) uses statistical averaging over thousands of traces to isolate tiny signal variations tied to a specific key bit.

The why: TrustZone protects memory and peripherals at the architectural level, but it cannot prevent physical leakage from the silicon itself. If your secure world code runs a non-constant-time AES, an attacker with an oscilloscope can extract the key—regardless of how well you've configured MPU or SAU regions.

## Key Commands / Configuration / Code

### 1. Vulnerable AES Comparison (Don't Do This)

```c
// Vulnerable: timing leaks via early exit
int aes_compare(const uint8_t *a, const uint8_t *b, size_t len) {
    for (size_t i = 0; i < len; i++) {
        if (a[i] != b[i]) {
            return 0;  // Early exit! Timing reveals position of first mismatch
        }
    }
    return 1;
}
```

### 2. Constant-Time Comparison (Do This)

```c
// Constant-time: execution time independent of data
int ct_compare(const uint8_t *a, const uint8_t *b, size_t len) {
    volatile uint8_t diff = 0;
    for (size_t i = 0; i < len; i++) {
        diff |= a[i] ^ b[i];  // XOR accumulates differences
    }
    return (diff == 0);
}
```

### 3. Power Analysis Trace Collection (Python + Saleae Logic)

```python
import numpy as np
from saleae import Saleae

# Configure capture: 10 MS/s, trigger on GPIO rising edge
saleae = Saleae()
saleae.set_sample_rate(10_000_000)  # 10 MHz
saleae.set_capture_seconds(0.001)   # 1 ms per trace
saleae.set_trigger(0, 'rising')     # Channel 0 = victim start signal

traces = []
for i in range(10000):
    saleae.capture_start()
    saleae.wait_for_completion()
    data = saleae.get_analog_channel(1)  # Channel 1 = current probe
    traces.append(data)
    if i % 1000 == 0:
        print(f"Collected {i} traces")

# Save for DPA analysis
np.save('power_traces.npy', np.array(traces))
```

### 4. Simple DPA Correlation (Key Byte Recovery)

```python
import numpy as np

traces = np.load('power_traces.npy')  # shape: (10000, 10000 samples)
plaintexts = np.load('plaintexts.npy')

# Target: first S-box output byte for key byte 0
def sbox_output(plaintext_byte, key_guess):
    return aes_sbox[plaintext_byte ^ key_guess]

best_key = 0
best_corr = 0
for key_guess in range(256):
    # Hypothetical power model: Hamming weight of S-box output
    hypothesis = np.array([bin(sbox_output(p, key_guess)).count('1') 
                           for p in plaintexts[:, 0]])
    # Pearson correlation with each time sample
    corr = np.corrcoef(hypothesis, traces[:, 500:600])[0, 1:]
    max_corr = np.max(np.abs(corr))
    if max_corr > best_corr:
        best_corr = max_corr
        best_key = key_guess

print(f"Recovered key byte 0: 0x{best_key:02x} (corr={best_corr:.3f})")
```

## Common Pitfalls & Gotchas

1. **Assuming TrustZone stops side channels**: It doesn't. TrustZone isolates memory and peripherals, but the CPU still executes instructions with data-dependent timing and power. A secure world AES that isn't constant-time is still vulnerable. You must implement side-channel countermeasures *within* the secure enclave.

2. **Forgetting about the debug interface**: Many engineers focus on side-channel resistance but leave SWD/JTAG enabled in production. An attacker can simply halt the CPU and read registers directly—no power analysis needed. Always disable debug interfaces (e.g., `DBGMCU->CR` lock) before shipping.

3. **Miscounting traces for DPA**: DPA requires thousands of traces to average out noise. A common mistake is collecting too few traces (e.g., 100) and concluding "no leakage." Rule of thumb: for 8-bit key recovery, 5,000–10,000 traces is a minimum. Use a Chi-squared test on your traces to verify statistical significance before claiming resistance.

## Try It Yourself

1. **Timing attack on a PIN check**: Write a simple PIN verification function (4-digit) that returns early on mismatch. Use a logic analyzer to measure execution time for each incorrect guess. Can you recover the PIN digit-by-digit? Then rewrite it as constant-time and verify the timing is flat.

2. **Power trace collection**: Set up an STM32L4 running a fixed AES encryption (use `mbedtls_aes_encrypt`). Trigger a GPIO pin at the start of encryption. Connect a 1Ω shunt resistor on the VDD line and measure voltage drop with an oscilloscope (or Saleae Logic Pro with analog). Collect 100 traces and observe the repeating patterns—that's the AES rounds.

3. **DPA on a single S-box**: Using the Python script above, simulate 10,000 traces with additive Gaussian noise (SNR=10). Run the DPA correlation and see if you recover the key byte. Then reduce SNR to 1 and observe how many more traces you need.

## Next Up

Tomorrow is **Day 21: Full Review & Project: Secure Boot Chain on nRF9160**. We'll tie together everything from the past 20 days: TrustZone configuration, secure boot, image signing, anti-rollback, and side-channel awareness into a complete, production-ready secure boot chain for the nRF9160 SiP. Bring your nRF9160 DK and your patience—this will be the capstone project.
