---
title: "Day 13: Model Size vs Accuracy Tradeoffs for Flash-Constrained MCUs"
date: 2026-07-13
tags: ["til", "edge-ai-tinyml", "model-size", "tradeoffs"]
---

## What I Explored Today

Today I dug into the brutal reality of fitting a neural network into a microcontroller with 256 KB of flash — and what you have to sacrifice to get there. I’ve been working with a Cortex-M4 target that has exactly 512 KB of flash total, and after reserving space for the bootloader, RTOS kernel, and application code, I’m left with roughly 180 KB for the model. That forces hard choices: do I prune aggressively and lose 3% accuracy, or quantize to 8-bit and risk edge-case failures? I spent the day systematically measuring the Pareto frontier of model size vs. accuracy for a keyword-spotting CNN, using TensorFlow Lite for Microcontrollers (TFLM) and the Speech Commands dataset.

## The Core Concept

The fundamental tension is simple: model parameters are stored in flash, and flash is finite. Every weight and bias takes up space, and the number of parameters grows roughly quadratically with layer width and linearly with depth. On a desktop GPU, you can throw a 50 MB model at a problem. On an MCU, you’re fighting for every kilobyte.

The key insight is that not all accuracy loss is equal. A 2% drop in top-1 accuracy might be acceptable for a wake-word detector that only triggers on “Hey, device,” but catastrophic for a medical anomaly detector. The tradeoff is governed by three levers:

1. **Quantization**: Reducing weight precision from float32 to int8 cuts model size by 4×, but introduces quantization noise that can shift decision boundaries.
2. **Pruning**: Removing the smallest-magnitude weights reduces parameter count, but can create dead neurons if done too aggressively.
3. **Architecture scaling**: Shrinking the number of filters, kernel sizes, or dense layer units directly reduces parameter count, but also reduces representational capacity.

The Pareto-optimal frontier is the set of configurations where you cannot reduce model size without sacrificing accuracy. Finding it requires sweeping these three knobs and measuring both flash footprint and validation accuracy on-device — not just in simulation, because the MCU’s limited memory bandwidth and cache behavior can introduce additional latency or numerical drift.

## Key Commands / Configuration / Code

I used TensorFlow 2.16 with the TFLM converter. Here’s the exact workflow for quantizing and measuring a 1D CNN for keyword spotting.

**Step 1: Define a baseline model and train it.**

```python
import tensorflow as tf
from tensorflow.keras import layers

def build_cnn(input_shape=(49, 10), num_classes=12):
    model = tf.keras.Sequential([
        layers.Input(shape=input_shape),
        layers.Conv1D(64, 3, activation='relu'),
        layers.MaxPooling1D(2),
        layers.Conv1D(128, 3, activation='relu'),
        layers.GlobalAveragePooling1D(),
        layers.Dense(num_classes, activation='softmax')
    ])
    return model

model = build_cnn()
model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
# Assume train_ds, val_ds are tf.data.Dataset objects from Speech Commands
model.fit(train_ds, validation_data=val_ds, epochs=10)
```

**Step 2: Convert to TFLite with full integer quantization using a representative dataset.**

```python
def representative_dataset():
    for batch in val_ds.take(100):
        yield [tf.cast(batch[0], tf.float32)]

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8
tflite_quant_model = converter.convert()

# Save and check size
with open('model_quant.tflite', 'wb') as f:
    f.write(tflite_quant_model)
print(f"Quantized model size: {len(tflite_quant_model) / 1024:.1f} KB")
```

**Step 3: Evaluate accuracy on-device using TFLM’s Python interpreter (or a dev board).**

```python
import numpy as np
from tflite_micro.python.interpreter import tflite_micro_interpreter

interpreter = tflite_micro_interpreter.MicroInterpreter(
    model_content=tflite_quant_model,
    device_tree='cortex_m4'
)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

correct = 0
total = 0
for x, y in val_ds.unbatch().take(500):
    # Scale input to int8 range
    input_scale, input_zero = input_details[0]['quantization']
    x_int8 = np.clip(np.round(x / input_scale + input_zero), -128, 127).astype(np.int8)
    interpreter.set_input(x_int8, 0)
    interpreter.invoke()
    output = interpreter.get_output(0)
    if np.argmax(output) == y.numpy():
        correct += 1
    total += 1
print(f"On-device accuracy: {correct/total:.3f}")
```

**Step 4: Sweep filter counts to find the Pareto frontier.**

```python
for filters in [16, 32, 64, 128]:
    model = build_cnn(filters=filters)  # modify build_cnn to accept filters param
    # ... train, quantize, measure size and accuracy ...
    results.append({'filters': filters, 'size_kb': size, 'accuracy': acc})
```

## Common Pitfalls & Gotchas

1. **Representative dataset mismatch.** If your representative dataset for quantization doesn’t cover the full input distribution, the calibration step will compute wrong quantization ranges. I once used 10 samples from a single speaker, and the quantized model dropped from 92% to 60% accuracy because the activation ranges were too narrow. Always use at least 100 samples spanning all classes.

2. **Assuming float32 accuracy carries over to int8.** I’ve seen models lose 5–8% accuracy after quantization due to a single outlier layer with high dynamic range. Always run the TFLM interpreter (not just the TFLite Python interpreter) because the micro interpreter uses different kernel implementations that can introduce additional rounding errors. Test on actual hardware or the TFLM simulator.

3. **Ignoring the model’s constant data.** The `.tflite` file size includes operator metadata, lookup tables, and buffer alignments. A model with many small tensors can have 30% overhead from metadata alone. Use `flatbuffers` inspection tools to see the breakdown: `flatc --raw-binary model_quant.tflite` reveals the actual tensor buffer sizes vs. the file size.

## Try It Yourself

1. **Sweep the quantization bit-width.** Convert the same model to int8, int16, and float32 (if flash allows). Plot model size vs. accuracy for each. On a Cortex-M4, int16 often gives a sweet spot with only 0.5% accuracy loss vs. float32 but half the size.

2. **Apply magnitude-based pruning.** Use TensorFlow Model Optimization Toolkit to prune 50%, 75%, and 90% of weights, then quantize. Measure the on-device accuracy and flash footprint. You’ll likely find that 50% pruning costs <1% accuracy but saves 40% of flash.

3. **Profile the model’s layer-by-layer flash usage.** Use the TFLM memory planner to print arena size and tensor allocations. Identify the largest layer (usually the first conv or dense) and try reducing its filter count by half. Retrain and compare the new Pareto point.

## Next Up

Tomorrow, I’ll walk through the entire Edge Impulse pipeline — from sensor data collection on an STM32 to deploying a quantized model — and show you how to avoid the common pitfalls that waste hours of debugging. We’ll build an end-to-end TinyML pipeline for embedded sensors, covering data logging, impulse design, and on-device inference.
