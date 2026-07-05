---
title: "Day 05: Converting Models: TensorFlow to TFLite to TFLite Micro"
date: 2026-07-05
tags: ["til", "edge-ai-tinyml", "tflite-conversion"]
---

## What I Explored Today

Today I dug into the full conversion pipeline from a trained TensorFlow Keras model all the way down to a TFLite Micro-compatible flatbuffer. The goal was to understand exactly what happens at each stage — not just the API calls, but the structural and numerical transformations that can make or break a deployment on a Cortex-M4 with 256KB of RAM. I walked through three distinct conversion steps: exporting to `.tflite`, applying post-training quantization, and then verifying the model is compatible with the TFLite Micro runtime's operator subset.

## The Core Concept

The conversion pipeline exists because the hardware targets for TinyML are radically different from the GPU/TPU environments where models are trained. A standard TensorFlow model is a graph of operations with 32-bit float weights, designed for XLA compilation and cuDNN kernels. A TFLite model is a serialized flatbuffer that replaces the training graph with an inference-only graph, fusing operations like `Conv2D + BiasAdd + ReLU` into a single custom op. The TFLite Micro interpreter then strips out the memory allocator and threading primitives, leaving only a flatbuffer parser and a minimal operator resolver.

The critical insight is that **quantization is not just compression — it's a computational model change**. When you convert from float32 to int8, you're not just rounding numbers; you're replacing floating-point multiply-accumulate (MAC) operations with integer MACs that require zero-point subtraction and scale multiplication. The converter handles this by inserting quantization/dequantization nodes and recording scale and zero-point parameters per tensor. If you skip understanding this, your model will either silently produce garbage output or fail to fit in the target's SRAM.

## Key Commands / Configuration / Code

Here's the complete pipeline I ran today. I started with a simple 2-layer CNN trained on the CIFAR-10 dataset (not shown, assume `model.h5` exists).

```python
import tensorflow as tf
import numpy as np

# Step 1: Load the trained Keras model
model = tf.keras.models.load_model('cifar10_cnn.h5')

# Step 2: Convert to float32 TFLite (baseline)
converter = tf.lite.TFLiteConverter.from_keras_model(model)
float32_tflite = converter.convert()
with open('model_float32.tflite', 'wb') as f:
    f.write(float32_tflite)

# Step 3: Convert with post-training int8 quantization
# Requires a representative dataset for calibration
def representative_dataset():
    # Load 100 samples from CIFAR-10 training set
    (x_train, _), _ = tf.keras.datasets.cifar10.load_data()
    for i in range(100):
        # Normalize to [0,1] as model expects
        yield [x_train[i].astype(np.float32) / 255.0]

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
# Force full int8 quantization (inputs/outputs also int8)
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8
int8_tflite = converter.convert()
with open('model_int8.tflite', 'wb') as f:
    f.write(int8_tflite)

# Step 4: Verify TFLite Micro compatibility
# Load the flatbuffer and inspect operators
interpreter = tf.lite.Interpreter(model_content=int8_tflite)
interpreter.allocate_tensors()

# Get the operator codes used
from tflite_micro.tensorflow.lite.micro.python.interpreter import tflm_python
# Check against TFLM supported ops list
# Common unsupported ops: STRIDED_SLICE, TANH, SOFTMAX (some variants)
# We'll use the TFLM Python wrapper to test inference
tflm_interpreter = tflm_python.Interpreter(model_content=int8_tflite)
tflm_interpreter.allocate_tensors()

# Run a single inference to confirm no runtime errors
input_details = tflm_interpreter.get_input_details()
output_details = tflm_interpreter.get_output_details()
test_input = np.random.randint(-128, 127, size=input_details[0]['shape'], dtype=np.int8)
tflm_interpreter.set_input(test_input, 0)
tflm_interpreter.invoke()
output = tflm_interpreter.get_output(0)
print(f"TFLM inference output shape: {output.shape}, dtype: {output.dtype}")
```

**Key flags explained:**
- `tf.lite.Optimize.DEFAULT`: Enables quantization, but without `TFLITE_BUILTINS_INT8` it leaves some ops in float16 or float32.
- `supported_ops = [TFLITE_BUILTINS_INT8]`: Forces the converter to quantize all ops to int8. If an op can't be quantized, conversion fails — that's a feature, not a bug.
- `inference_input_type = tf.int8`: The model expects int8 input directly, avoiding a dequantize op at the boundary.

## Common Pitfalls & Gotchas

**1. The representative dataset must match the training preprocessing exactly.**
I spent an hour debugging a 15% accuracy drop after quantization. The issue: my training pipeline normalized images to `[-1, 1]`, but my representative dataset used `[0, 1]`. The calibration statistics (min/max per channel) were wrong, causing the quantization scalers to be off by a factor of 2. Always feed the exact same preprocessing pipeline to the representative dataset generator.

**2. Not all TensorFlow ops have TFLite Micro kernels.**
The TFLite runtime supports ~150 ops; TFLite Micro supports ~80. Common missing ops include `SelectV2`, `BatchMatMulV2` (used in some attention layers), and `StridedSlice` with non-constant begin/end. Run `tflite_micro.tensorflow.lite.micro.python.interpreter` on your model before committing to a hardware target. If an op is missing, you either need to rewrite the model or implement a custom op in C++.

**3. Quantization-aware training (QAT) vs. post-training quantization (PTQ) — they are not interchangeable.**
PTQ works well for models with >100K parameters and ReLU activations. For models with Swish/GELU activations or very narrow layers (e.g., 4 filters), PTQ can cause >5% accuracy loss. QAT simulates quantization during training and typically recovers most of that loss. If your model has non-ReLU activations, use QAT from the start.

## Try It Yourself

1. **Quantize a model with and without `TFLITE_BUILTINS_INT8`.** Compare the file sizes and run both on a sample input. Use `np.max(np.abs(output_float32 - output_int8))` to measure the numerical difference. You'll see that without the forced int8 flag, some ops remain in float16, increasing model size by 30-50%.

2. **Write a representative dataset generator that applies random crops.** Most real-world deployments have input augmentation. See if the quantization calibration changes when you add slight variations (e.g., ±2 pixel shifts) to the calibration samples. This tests the robustness of your quantization ranges.

3. **Take a model with a `Softmax` layer and convert it.** Then check if TFLite Micro supports the softmax op. If not, replace it with a custom `logits_to_probs` function using only supported ops (e.g., `Exp` + `Sum` + `Div`). Measure the accuracy difference.

## Next Up

Tomorrow I'll dive into the **TensorFlow Lite for Microcontrollers: Runtime Architecture** — specifically how the flatbuffer interpreter allocates tensor arenas, resolves operators, and manages the scratch buffer on a memory-constrained MCU. We'll look at the `MicroInterpreter` source code and understand why your model might fail at `AllocateTensors()` with an "arena size too small" error.
