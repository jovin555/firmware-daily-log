---
title: "Day 10: Digital-to-Analog Conversion: DAC Architectures & Applications"
date: 2026-07-19
tags: ["til", "circuit-design", "dac"]
---

## What I Explored Today

Today I dove into the practical side of Digital-to-Analog Converters (DACs)—the unsung heroes that bridge the digital compute world with the analog physical world. While ADCs get most of the attention in mixed-signal design, a poorly chosen DAC architecture can ruin an otherwise perfect signal chain. I explored the three dominant architectures used in real embedded systems: resistor-ladder (R-2R), string DACs, and delta-sigma (oversampling) DACs. I also wired up a simple audio waveform generator using an R-2R ladder on a breadboard to feel the tradeoffs firsthand.

## The Core Concept

A DAC converts a discrete digital value (usually binary) into a continuous analog voltage or current. The fundamental challenge is resolution vs. linearity vs. speed. The "why" matters here: every DAC architecture makes a different tradeoff.

- **String DACs** (a series of equal resistors with taps) are simple and inherently monotonic—ideal for low-resolution, low-speed control loops like setting a reference voltage. They’re power-hungry at high resolution because you need 2^N resistors.
- **R-2R Ladder DACs** use only two resistor values (R and 2R) in a repeating pattern. They’re the workhorse for medium-resolution (8–12 bits) applications like waveform generation because they’re fast, cheap, and easy to build with discrete components.
- **Delta-Sigma (Σ-Δ) DACs** use oversampling and noise shaping to achieve high resolution (16–24 bits) at the cost of latency and output noise. They dominate audio and precision instrumentation.

The key insight: you don’t always need the highest resolution. A 10-bit R-2R DAC with a clean reference can outperform a noisy 16-bit Σ-Δ DAC in a fast control loop.

## Key Commands / Configuration / Code

Let’s look at a practical example: generating a 1 kHz sine wave using an R-2R ladder DAC driven by an STM32 microcontroller. We’ll use the built-in DAC peripheral (12-bit, string architecture) for comparison.

### Example 1: STM32 DAC with DMA (12-bit string DAC)

```c
// STM32G474 HAL example: DAC1 output on PA4, triggered by TIM2
// Generates a 256-point sine wave at 1 kHz

#include "stm32g4xx_hal.h"

// 12-bit sine lookup table (256 points, amplitude centered at 2048)
const uint16_t sine_table[256] = {
    2048, 2098, 2148, 2198, 2247, 2295, 2342, 2388, 2433, 2476, 2518, 2558, 2596, 2632, 2666, 2698,
    // ... (truncated for brevity, full table would be 256 entries)
    2048  // last entry wraps
};

void DAC_Init(void) {
    __HAL_RCC_DAC1_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_4;          // DAC1_OUT1 on PA4
    gpio.Mode = GPIO_MODE_ANALOG;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);

    DAC_HandleTypeDef hdac = {0};
    hdac.Instance = DAC1;
    HAL_DAC_Init(&hdac);

    DAC_ChannelConfTypeDef sConfig = {0};
    sConfig.DAC_Trigger = DAC_TRIGGER_T2_TRGO;  // TIM2 trigger output
    sConfig.DAC_OutputBuffer = DAC_OUTPUTBUFFER_ENABLE;
    HAL_DAC_ConfigChannel(&hdac, &sConfig, DAC_CHANNEL_1);
}

void TIM2_Init(void) {
    // TIM2 frequency = 170 MHz / (prescaler+1) / (period+1)
    // For 256 samples at 1 kHz: sample rate = 256 kHz
    // 170 MHz / 664 = 256 kHz → prescaler=0, period=663
    __HAL_RCC_TIM2_CLK_ENABLE();
    TIM_HandleTypeDef htim = {0};
    htim.Instance = TIM2;
    htim.Init.Prescaler = 0;
    htim.Init.Period = 663;          // 256 kHz update rate
    htim.Init.CounterMode = TIM_COUNTERMODE_UP;
    HAL_TIM_Base_Init(&htim);

    TIM_MasterConfigTypeDef sMasterConfig = {0};
    sMasterConfig.MasterOutputTrigger = TIM_TRGO_UPDATE;
    HAL_TIMEx_MasterConfigSynchronization(&htim, &sMasterConfig);
    HAL_TIM_Base_Start(&htim);
}

// Start DAC with DMA (circular mode)
HAL_DAC_Start_DMA(&hdac, DAC_CHANNEL_1, (uint32_t*)sine_table, 256, DAC_ALIGN_12B_R);
```

**Key takeaway:** The DMA circular mode lets the DAC run autonomously—no CPU intervention after startup. The trigger from TIM2 ensures precise timing.

### Example 2: Discrete R-2R Ladder (8-bit, breadboard)

For a hands-on build, use 10 kΩ (R) and 20 kΩ (2R) resistors. Connect 8 digital outputs (e.g., from an Arduino Uno) to the ladder inputs (MSB to LSB). The output voltage is:

```
Vout = Vref * (D / 256)
```

Where D is the 8-bit digital value (0–255). With Vref = 5 V, you get ~19.5 mV per step. Add an op-amp buffer (e.g., LM358) to drive a load.

```cpp
// Arduino sketch: 8-bit R-2R sine wave on pins D2–D9 (D2 = LSB, D9 = MSB)
const uint8_t sine8[256] = {128, 131, 134, ...};  // 8-bit sine table

void setup() {
    DDRD = 0xFC;  // Pins D2–D7 as outputs (bits 2–7)
    DDRB = 0x03;  // Pins D8–D9 as outputs (bits 0–1)
}

void loop() {
    for (int i = 0; i < 256; i++) {
        uint8_t val = sine8[i];
        // Write to PORTD (bits 2–7) and PORTB (bits 0–1)
        PORTD = (PORTD & 0x03) | (val << 2);
        PORTB = (PORTB & 0xFC) | (val >> 6);
        delayMicroseconds(39);  // ~256 kHz sample rate → 1 kHz sine
    }
}
```

**Note:** The `delayMicroseconds()` call introduces jitter. For clean output, use a hardware timer interrupt instead.

## Common Pitfalls & Gotchas

1. **Reference voltage noise is your enemy.** The DAC output is directly proportional to Vref. A noisy Vref (e.g., from a switching regulator) will appear as distortion on the output. Always use a low-noise LDO or a precision reference (e.g., REF5050) for the DAC reference pin. Bypass with 10 µF + 0.1 µF ceramic.

2. **R-2R ladder resistor tolerance kills linearity.** For an 8-bit DAC, you need resistors with at least 1% tolerance. For 10 bits, use 0.1% or better. The MSB resistors matter most—a 1% error in the MSB resistor creates a 0.5% full-scale error (about 1 LSB at 8 bits).

3. **Output loading causes gain error.** The R-2R ladder output impedance is exactly R (e.g., 10 kΩ). If you drive a 10 kΩ load directly, you get a 50% voltage divider error. Always buffer with a unity-gain op-amp (JFET input for high impedance, e.g., OPA2134).

## Try It Yourself

1. **Build an 8-bit R-2R ladder on a breadboard** using 10 kΩ and 20 kΩ resistors (1% tolerance). Connect to an Arduino’s digital outputs and generate a sawtooth wave. Measure the output with an oscilloscope—observe the step size and glitch energy at major carry transitions (e.g., 127→128).

2. **Compare DAC architectures on an STM32 Nucleo board.** Use the built-in 12-bit DAC (string type) to generate a 1 kHz sine wave. Then implement a PWM-based DAC using a timer and RC filter. Compare the THD (total harmonic distortion) using an FFT on a scope or sound card.

3. **Add a reconstruction filter.** After your DAC output, design a 2nd-order Sallen-Key low-pass filter with cutoff at 3 kHz (for a 1 kHz sine). Measure the reduction in stair-step artifacts. Calculate the required resistor and capacitor values using the standard formula: `fc = 1 / (2π√(R1 R2 C1 C2))`.

## Next Up

Tomorrow: **Sensor Signal Conditioning: Amplification & Noise Reduction** — We’ll take a tiny millivolt-level sensor signal (thermocouple, strain gauge) and turn it into a clean, amplified signal suitable for an ADC. Expect op-amp topologies, filtering, and the dreaded 50/60 Hz hum rejection.
