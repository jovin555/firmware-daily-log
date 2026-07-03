---
title: "Day 03: Model Quantization: int8, Fixed-Point & Quantization-Aware Training"
date: 2026-07-03
tags: ["til", "edge-ai-tinyml", "quantization", "int8"]
---

## What I Explored Today

Today I dug into the practical reality of squeezing a trained neural network into 8-bit integer arithmetic. After two days of setting up toolchains and profiling a baseline model, the numbers were sobering: my 4.2 MB FP32 MobileNetV2 would never fit the 256 KB SRAM on my target Cortex-M4. Quantization is the first real weapon in the TinyML arsenal, and I spent the day benchmarking post-training quantization (PTQ) against quantization-aware training (QAT) on a keyword-spotting model. The results confirmed what the literature says: PTQ is fast but fragile, while QAT is robust but requires retraining.

## The Core Concept

Quantization maps a continuous range of floating-point values into a discrete set of integers. The fundamental equation is:

```
real_value = scale * (quantized_value - zero_point)
```

For int8 quantization, we map the range [min, max] of a tensor into [-128, 127] (symmetric) or [0, 255] (asymmetric). The scale is a floating-point number, and the zero_point is an integer that aligns the real zero with a quantized value.

Why does this matter for edge devices? Three reasons:
1. **Memory bandwidth**: int8 uses 4× less memory than FP32. For a 4 MB model, that's 1 MB on flash.
2. **Compute efficiency**: Most MCUs have single-cycle integer multiply-accumulate (MAC) units. FP32 MACs take 2-4 cycles on a Cortex-M4 with FPU, and are emulated in software on M0+/M3 cores.
3. **Energy**: Integer operations consume roughly 1/10th the energy of FP32 operations at the same clock speed.

The critical insight is that quantization is not free. The scale and zero_point introduce a quantization error proportional to the step size: `Δ = (max - min) / 255`. If your activation distribution has long tails (e.g., outliers from ReLU), you waste quantization bins on rarely-used values, crushing precision where it matters.

## Key Commands / Configuration / Code

I used TensorFlow Lite's converter with both PTQ and QAT. Here's the exact workflow.

### Post-Training Quantization (PTQ)

```python
import tensorflow as tf

# Load your trained Keras model
model = tf.keras.models.load_model('kws_model_fp32.h5')

# Representative dataset: ~100 samples from your training set
def representative_dataset():
    for i in range(100):
        # Assuming input shape (1, 49, 10, 1) for MFCC features
        yield [x_train[i:i+1].astype(np.float32)]

# Convert with int8 quantization
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
# Force full int8 quantization (inputs/outputs also int8)
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8

tflite_quant_model = converter.convert()
with open('kws_model_int8_ptq.tflite', 'wb') as f:
    f.write(tflite_quant_model)

# Check size
import os
size_kb = os.path.getsize('kws_model_int8_ptq.tflite') / 1024
print(f"Quantized model size: {size_kb:.1f} KB")  # Expect ~1050 KB from 4.2 MB
```

### Quantization-Aware Training (QAT)

QAT simulates quantization during training so the model learns to be robust to it.

```python
import tensorflow_model_optimization as tfmot

# Apply quantization to the entire model
quantize_model = tfmot.quantization.keras.quantize_model

# Clone and quantize the architecture (weights stay FP32 during training)
qat_model = quantize_model(model)

# Recompile — note: use same optimizer but possibly lower learning rate
qat_model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),  # 10x lower than original
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

# Fine-tune for 5-10 epochs (not full training)
qat_model.fit(
    x_train, y_train,
    batch_size=32,
    epochs=5,
    validation_data=(x_val, y_val),
    callbacks=[tf.keras.callbacks.ReduceLROnPlateau()]
)

# Convert to TFLite — same converter code as PTQ
converter = tf.lite.TFLiteConverter.from_keras_model(qat_model)
# ... (same quantization config as above)
tflite_qat_model = converter.convert()
```

### Fixed-Point Fallback (for bare-metal inference)

When you can't use TFLite Micro, you implement the quantized inference manually. The core kernel for a quantized convolution:

```c
// int8 quantized convolution, single output pixel
// Assumes per-tensor quantization (not per-channel for simplicity)
int32_t acc = 0;
for (int k = 0; k < kernel_size; k++) {
    int32_t input_q = (int32_t)input_data[input_idx + k] - input_zero_point;
    int32_t weight_q = (int32_t)weights[k] - weight_zero_point;
    acc += input_q * weight_q;
}
// Apply scale: real = scale_product * acc
// scale_product = input_scale * weight_scale / output_scale
// Use fixed-point multiply: acc * scale_product_fixed >> shift
int32_t result = (acc * scale_product_fixed) >> shift;
result += output_zero_point;
// Clamp to int8 range
output_data[out_idx] = (int8_t)CLAMP(result, -128, 127);
```

## Common Pitfalls & Gotchas

1. **Per-tensor vs per-channel quantization**: Most TFLite converters default to per-tensor quantization for activations (one scale for the whole tensor) and per-channel for weights. This is fine for most models, but if you have depthwise convolutions (MobileNet), per-channel quantization of weights is critical. Without it, accuracy can drop 5-10% on keyword spotting. Verify with `tflite_model.get_tensor_details()`.

2. **Representative dataset size**: I initially used 10 samples for PTQ. Accuracy dropped from 92% to 78%. With 100 samples, it recovered to 89%. With 500, it hit 90.5%. The rule of thumb: use at least 100-200 diverse samples covering all classes. Too few, and the calibration misses activation ranges.

3. **QAT learning rate sensitivity**: If you use the same learning rate as full-precision training, QAT often diverges. The quantization noise acts as a regularizer. I found that reducing the LR by 10x (from 1e-3 to 1e-4) and training for only 5 epochs gave the best trade-off. More epochs can overfit to the quantization simulation.

## Try It Yourself

1. **Benchmark PTQ vs QAT**: Take any trained Keras model (even a simple MLP for MNIST). Convert with PTQ and QAT. Measure accuracy on a test set. Then profile the inference time on your target MCU using the TFLite Micro benchmark tool. Record the accuracy vs speed trade-off.

2. **Inspect quantization parameters**: Load your quantized TFLite model and print the scale and zero_point for each tensor. Identify which layers have the largest quantization step sizes (Δ). Those are your accuracy bottlenecks. Try retraining with QAT and see if those steps shrink.

3. **Implement a quantized matmul in C**: Write a bare-metal function that takes two int8 matrices and computes their product using the fixed-point scale multiplication shown above. Verify against a NumPy reference. This is the kernel that runs on every inference.

## Next Up

Tomorrow I'm tackling **Model Pruning & Distillation for Constrained Devices**. Quantization got us from 4.2 MB to 1 MB, but I need to hit 256 KB. Pruning can remove 50-90% of weights with minimal accuracy loss, and distillation can compress a teacher model into a student that's 10× smaller. I'll be comparing magnitude-based pruning with iterative structured pruning on the keyword spotter, and testing whether a distilled tiny transformer can beat a pruned CNN.
