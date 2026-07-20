---
title: "Day 20: Power Profiling ML Inference: Measuring Energy per Inference"
date: 2026-07-20
tags: ["til", "edge-ai-tinyml", "power-profiling", "inference"]
---

## What I Explored Today

Today I dug into the practical mechanics of measuring energy per inference on resource-constrained edge devices. While latency and throughput get most of the attention in ML benchmarks, energy per inference is the metric that determines whether your model runs for 6 hours on a coin cell battery or dies in 20 minutes. I set up a measurement rig using a precision shunt resistor, an ADS1115 ADC, and a Raspberry Pi Pico to capture real-time current draw during inference cycles on a Cortex-M4 microcontroller running TensorFlow Lite Micro.

## The Core Concept

Energy per inference (E<sub>inf</sub>) is the product of average power and inference time: E = P × t. But the devil is in the sampling. Microcontrollers transition between sleep, active compute, and memory access states in microseconds. A naive average-over-10-seconds approach will miss the 50mA spike during a MAC (multiply-accumulate) operation that lasts only 200µs.

The real challenge is aligning your power measurement window precisely with the inference execution. You need a trigger signal from the MCU that goes high when inference starts and low when it ends. This lets you isolate the energy consumed *only* by the inference, excluding idle current, peripheral overhead, and data loading.

Why this matters: A model with 10ms inference time at 30mA average current consumes 300µJ per inference. If your battery has 1000mAh at 3.7V (13,320 J), you get roughly 44 million inferences. Shave 5mA off that average, and you gain 7 million more inferences. That’s the difference between a sensor node lasting one month vs. six weeks.

## Key Commands / Configuration / Code

Here’s the measurement setup I used. The target is an STM32L476RG running TFLM with a person detection model.

**Hardware setup:**
- 10Ω shunt resistor in series with VDD of the MCU
- ADS1115 ADC measuring voltage drop across shunt (differential mode, ±0.256V range, 860 SPS)
- Trigger GPIO (PA0) toggled high at `model->input()` and low after `interpreter->Invoke()`

**Trigger code on the target MCU (C++):**
```cpp
// In main.cpp inference loop
HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_SET);  // Start measurement window
memcpy(interpreter->input(0)->data.f, input_buffer, input_size);
interpreter->Invoke();  // Run inference
HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_RESET); // End measurement window
```

**Host-side capture script (Python with smbus2):**
```python
import smbus2
import time
import numpy as np

# ADS1115 I2C address (ADDR pin to GND)
ADS1115_ADDR = 0x48
# Config: AIN0-AIN1 differential, ±0.256V, 860 SPS, continuous mode
CONFIG_REG = 0x01
CONVERSION_REG = 0x00
config = 0b00000010_10000011  # MSB: gain=2/3, LSB: 860SPS, continuous

bus = smbus2.SMBus(1)
bus.write_i2c_block_data(ADS1115_ADDR, CONFIG_REG, [config >> 8, config & 0xFF])
time.sleep(0.01)  # Allow first conversion

shunt_resistance = 10.0  # Ohms
samples = []
capture_duration = 5.0  # seconds
start = time.time()

while (time.time() - start) < capture_duration:
    # Read conversion register (2 bytes)
    data = bus.read_i2c_block_data(ADS1115_ADDR, CONVERSION_REG, 2)
    raw = (data[0] << 8) | data[1]
    # Convert to signed (16-bit two's complement)
    if raw & 0x8000:
        raw -= 1 << 16
    voltage = raw * 0.0078125 / 1000.0  # LSB=7.8125µV for ±0.256V range
    current = voltage / shunt_resistance  # I = V/R
    samples.append(current)

# Post-process: align with trigger GPIO (monitor on oscilloscope or logic analyzer)
# For this example, assume we captured trigger edges
samples = np.array(samples)
avg_current = np.mean(samples)  # Amps
avg_power = avg_current * 3.3  # VDD = 3.3V
inference_time = 0.015  # seconds (from oscilloscope measurement)
energy_per_inference = avg_power * inference_time  # Joules
print(f"Energy per inference: {energy_per_inference*1e6:.2f} µJ")
```

**Oscilloscope-based verification (alternative, more accurate):**
```bash
# Using a Rigol DS1054Z with math function
# Channel 1: voltage across shunt (10mV/mA)
# Math: CH1 * 3.3 / 10 = instantaneous power in mW
# Cursor measurement over inference window gives average power
# Energy = avg_power * delta_t
```

## Common Pitfalls & Gotchas

**1. Shunt resistor value kills your voltage margin.** A 10Ω shunt at 50mA drops 0.5V. If your MCU VDD_min is 2.7V and you’re running at 3.3V, you’re fine. But at 2.8V supply, that drop pushes you below spec. Always check the dropout voltage against your MCU’s operating range. Use a lower value (1Ω) and a more sensitive ADC if needed.

**2. Sampling rate mismatch.** The ADS1115 at 860 SPS gives one sample every ~1.16ms. If your inference completes in 5ms, you get only 4-5 samples. That’s not enough to capture the current spike profile. Use a faster ADC (e.g., MAX11612 at 200ksps) or a current sense amplifier with analog output to an oscilloscope for sub-millisecond inferences.

**3. Trigger alignment drift.** If you use software timestamps on the host, clock drift between MCU and host PC will misalign your measurement window. Always use a hardware trigger signal that the measurement system can observe directly (e.g., on a second ADC channel or oscilloscope probe). I lost two hours debugging “negative energy” readings before realizing my trigger was 3ms late.

## Try It Yourself

1. **Measure idle vs. inference current:** Run your model on an STM32 or ESP32. Capture 2 seconds of idle current (MCU in sleep), then 2 seconds with continuous inference. Calculate the delta energy per inference. You’ll likely find idle current is 30-50% of your total.

2. **Profile two model variants:** Take the same model quantized to int8 vs. float32. Measure energy per inference at the same clock speed. Note the difference in both time and average current. The int8 model should win on both, but the ratio varies by architecture.

3. **Voltage scaling experiment:** Run your model at 48MHz, 64MHz, and 80MHz. Measure energy per inference at each frequency. Plot energy vs. frequency — you’ll often see a U-shaped curve where the sweet spot is not the lowest frequency due to leakage current dominating at slow speeds.

## Next Up

Tomorrow: Data Collection & Labeling Pipelines for Embedded Sensor Data — how to build a reliable pipeline that generates labeled sensor datasets without spending weeks manually annotating accelerometer traces. We’ll cover trigger-based capture, synthetic data augmentation, and semi-automated labeling with heuristics.
