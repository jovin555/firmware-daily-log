---
title: "Day 09: Analog-to-Digital Conversion: ADC Types & Sampling Theory"
date: 2026-07-18
tags: ["til", "circuit-design", "adc", "sampling"]
---

## What I Explored Today

Today I dove into the practical realities of getting analog signals into a microcontroller without losing the information you care about. I’ve been burned before by aliasing and poor ADC selection, so I spent the day comparing SAR, delta-sigma, and pipeline ADC architectures, then worked through the sampling theorem with real-world constraints like aperture jitter and anti-aliasing filter design. The goal was to internalize not just which ADC to pick, but how to calculate the exact sampling rate and filter corner needed for a given signal bandwidth.

## The Core Concept

The fundamental tension in ADC design is between **resolution** (how finely you measure voltage) and **speed** (how often you measure it), with **power** and **cost** as the constraints. Every ADC architecture is a different trade-off in this space.

**Successive Approximation Register (SAR)** ADCs are the workhorses of embedded systems. They use a binary search through a capacitive DAC, converting one bit per clock cycle. For a 12-bit SAR at 1 MSPS, you need a 12 MHz clock (plus overhead). They offer excellent power efficiency and no pipeline delay, making them ideal for multiplexed sensor readings and control loops.

**Delta-sigma (ΔΣ)** ADCs oversample the input (often 64x to 256x the Nyquist rate) and use noise shaping to push quantization noise out of the band of interest. They trade speed for resolution—you can get 24 bits at a few kSPS. They require a digital decimation filter, which introduces latency. Use them for precision measurements like strain gauges or audio.

**Pipeline ADCs** divide the conversion across several stages, each resolving a few bits. They achieve high speed (hundreds of MSPS) with moderate resolution (8–16 bits). The catch is a fixed latency of several clock cycles and higher power. They dominate in communications and radar.

The **Nyquist-Shannon sampling theorem** states you must sample at least twice the highest frequency component in your signal. But in practice, you need a margin: the **anti-aliasing filter** cannot be a brick wall. If your signal has content at 20 kHz and you sample at 44.1 kHz, you need a filter that attenuates everything above 22.05 kHz by at least the ADC’s dynamic range (e.g., 60 dB for a 10-bit ADC). That usually means a 2nd- or 4th-order active filter with a corner at 15–18 kHz.

Aperture jitter—the uncertainty in when the sample is actually taken—limits the effective resolution at high frequencies. For a 10-bit ADC sampling a 1 MHz signal, jitter must be below ~50 ps. Many MCU internal ADCs have jitter in the 100–200 ps range, so you lose bits above a few hundred kHz.

## Key Commands / Configuration / Code

Here’s a real configuration for an STM32G4’s 12-bit SAR ADC, sampling a 10 kHz signal at 100 kSPS with a 20 kHz anti-aliasing filter:

```c
// STM32G4 ADC1 configuration for single-channel, continuous conversion
// Target: 100 kSPS, 12-bit resolution, hardware oversampling disabled

#include "stm32g4xx_hal.h"

ADC_HandleTypeDef hadc1;

void MX_ADC1_Init(void)
{
    ADC_MultiModeTypeDef multimode = {0};
    ADC_ChannelConfTypeDef sConfig = {0};

    __HAL_RCC_ADC12_CLK_ENABLE();  // Enable ADC clock

    hadc1.Instance = ADC1;
    hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4; // 170 MHz / 4 = 42.5 MHz
    hadc1.Init.Resolution = ADC_RESOLUTION_12B;
    hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
    hadc1.Init.ContinuousConvMode = ENABLE;  // Continuous mode
    hadc1.Init.DiscontinuousConvMode = DISABLE;
    hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
    hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
    hadc1.Init.NbrOfConversion = 1;
    hadc1.Init.DMAContinuousRequests = DISABLE;
    hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    hadc1.Init.LowPowerAutoWait = DISABLE;
    hadc1.Init.Overrun = ADC_OVR_DATA_PRESERVED;
    HAL_ADC_Init(&hadc1);

    // Configure channel 0 (PA0) with 47.5 cycle sampling time
    // Total conversion time = 12.5 (SAR) + 47.5 = 60 cycles
    // At 42.5 MHz: 60 / 42.5e6 = 1.41 µs → ~708 kSPS max
    // We'll use a timer trigger to get exactly 100 kSPS
    sConfig.Channel = ADC_CHANNEL_0;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
    sConfig.SingleDiff = ADC_SINGLE_ENDED;
    sConfig.OffsetNumber = ADC_OFFSET_NONE;
    sConfig.Offset = 0;
    HAL_ADC_ConfigChannel(&hadc1, &sConfig);
}
```

For the anti-aliasing filter, a 2nd-order Sallen-Key low-pass with corner at 20 kHz:

```python
# Sallen-Key low-pass filter design for ADC anti-aliasing
# Corner: 20 kHz, Q = 0.707 (Butterworth)
import numpy as np

f_c = 20e3  # Hz
C1 = 1e-9   # 1 nF
C2 = 2 * C1 # 2 nF for Q=0.707
R = 1 / (2 * np.pi * f_c * np.sqrt(C1 * C2))
print(f"R = {R:.0f} Ω")  # Typically ~5.6 kΩ (use nearest standard value)
```

## Common Pitfalls & Gotchas

1. **Aliasing from out-of-band noise**: Even if your signal is band-limited, wideband noise (from switching regulators or digital lines) can fold into your passband. Always place the anti-aliasing filter *before* the ADC input, not after. I once spent a day debugging 60 Hz noise that was actually 10 kHz switching noise aliased down.

2. **Input impedance mismatch**: SAR ADCs draw a current spike during the sampling phase. If your source impedance is too high (above ~1 kΩ for a 12-bit ADC at 1 MSPS), the sampling capacitor won’t charge fully, causing gain error and nonlinearity. Always buffer with an op-amp, or use a longer sampling time.

3. **Reference voltage noise**: The ADC’s resolution is relative to its reference. A noisy VREF directly becomes measurement noise. Use a dedicated reference IC (e.g., REF3033) and a 10 µF + 100 nF decoupling cap within 5 mm of the VREF pin. Don’t share the reference with digital supplies.

## Try It Yourself

1. **Calculate your required sampling rate**: Take a sensor with a 1 kHz bandwidth. Add a 2nd-order Butterworth anti-aliasing filter with a corner at 800 Hz. What sampling rate do you need to achieve 60 dB of alias rejection? (Hint: calculate the filter’s attenuation at the Nyquist frequency.)

2. **Measure ADC aperture jitter**: Set up a microcontroller ADC to sample a clean 100 kHz sine wave from a function generator. Compare the RMS noise in the samples when sampling at 1 MSPS vs. 100 kSPS. The increase in noise at higher input frequency reveals the jitter.

3. **Design a delta-sigma decimation filter**: In Python or MATLAB, implement a simple sinc3 filter (moving average of moving average of moving average) for a 24-bit ΔΣ ADC running at 6.4 MHz. Decimate by 128 to get 50 kSPS output. Plot the frequency response.

## Next Up

Tomorrow: **Digital-to-Analog Conversion: DAC Architectures & Applications** — we’ll cover R-2R ladders, string DACs, and how to generate clean analog waveforms from digital data, including glitch reduction and reconstruction filter design.
