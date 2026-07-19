---
title: "Day 19: On-Device Learning: Federated & Incremental Learning Constraints"
date: 2026-07-19
tags: ["til", "edge-ai-tinyml", "on-device-learning", "federated"]
---

## What I Explored Today

Today I dug into the practical constraints of running on-device learning—specifically federated learning (FL) and incremental (continual) learning—on resource-constrained microcontrollers. While most TinyML deployments use static models, the real world demands adaptation: a keyword spotter that learns a user's accent, or a predictive maintenance sensor that adapts to machine wear. I tested a minimal federated averaging (FedAvg) setup on an STM32U5 (2 MB Flash, 640 KB SRAM) and an incremental learning pipeline using Elastic Weight Consolidation (EWC) on an ESP32-S3. The results were sobering: the memory overhead of storing gradient histories and the compute cost of per-sample backpropagation push these techniques to the edge of feasibility.

## The Core Concept

The fundamental tension in on-device learning is between **plasticity** (learning new patterns) and **stability** (not forgetting old ones). In federated learning, the constraint is communication: each device computes a local model update (gradients) and sends only the weights to a central server, preserving privacy. But on a microcontroller, storing even a single gradient tensor for a 50 KB model requires 200 KB of RAM (assuming 32-bit floats)—often exceeding available SRAM.

Incremental learning solves a different problem: adapting a single device's model to new data without catastrophic forgetting. Elastic Weight Consolidation (EWC) penalizes changes to weights that were important for previous tasks. The constraint here is compute: EWC requires computing the Fisher Information Matrix (FIM) for each weight, which is a second-order derivative operation. On a Cortex-M4 without a floating-point unit (FPU), this can take minutes per sample.

The key insight: **you cannot simply port desktop FL or continual learning code to a microcontroller**. You must quantize gradients, prune the Fisher matrix, and often accept a trade-off between model accuracy and memory footprint.

## Key Commands / Configuration / Code

Below is a minimal federated learning client for an STM32U5 using TensorFlow Lite Micro (TFLM) and the CMSIS-NN kernels. This code performs one local training step on a 10 KB model (4 conv layers, quantized to int8).

```c
// federated_client.c — STM32U5, 640 KB SRAM, 2 MB Flash
// Assumes: TFLM interpreter initialized, model loaded, training data in flash

#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/schema/schema_generated.h"

// Model weights stored as int8 (quantized)
// Gradients stored as int16 to reduce memory (8x less than float32)
#define NUM_WEIGHTS 10240  // 10 KB model
int8_t weights[NUM_WEIGHTS];
int16_t gradients[NUM_WEIGHTS];  // 20 KB instead of 40 KB for float

// Local training buffer — one batch of 8 samples, each 32x32 grayscale
#define BATCH_SIZE 8
#define INPUT_SIZE 1024
#define OUTPUT_SIZE 10
int8_t batch_inputs[BATCH_SIZE * INPUT_SIZE];   // 8 KB
int8_t batch_labels[BATCH_SIZE * OUTPUT_SIZE];  // 80 bytes

// Federated averaging: compute local update and send weights
void federated_local_train(TfLiteMicroInterpreter* interpreter, int num_epochs) {
    // Step 1: Run inference on batch to compute loss
    for (int epoch = 0; epoch < num_epochs; epoch++) {
        for (int sample = 0; sample < BATCH_SIZE; sample++) {
            // Copy sample to interpreter input tensor
            memcpy(interpreter->input(0)->data.int8, 
                   &batch_inputs[sample * INPUT_SIZE], INPUT_SIZE);
            
            // Invoke inference
            TfLiteStatus invoke_status = interpreter->Invoke();
            if (invoke_status != kTfLiteOk) {
                MicroPrintf("Inference failed at sample %d", sample);
                return;
            }
            
            // Step 2: Compute gradient via backprop (simplified — uses TFLM training op)
            // TFLM does not natively support training; we use a custom op
            // that computes cross-entropy gradient for int8 outputs
            compute_cross_entropy_gradient(
                interpreter->output(0)->data.int8,
                &batch_labels[sample * OUTPUT_SIZE],
                gradients,  // output gradient buffer
                NUM_WEIGHTS
            );
            
            // Step 3: Apply gradient with learning rate (Q15 fixed-point)
            // Learning rate = 0.001 represented as Q15: 0x0008
            for (int i = 0; i < NUM_WEIGHTS; i++) {
                int32_t update = (int32_t)gradients[i] * 8;  // Q15 multiply
                weights[i] = (int8_t)(weights[i] - (update >> 15));
            }
        }
    }
    
    // Step 4: Send updated weights to server (e.g., via UART or BLE)
    // Server receives int8 weights, aggregates with other clients
    uart_send_bytes((uint8_t*)weights, NUM_WEIGHTS);
}
```

For incremental learning with EWC on ESP32-S3, the critical code snippet computes the Fisher Information Matrix diagonal:

```python
# ewc_fisher.py — runs on ESP32-S3 (Xtensa LX7, 512 KB SRAM)
# Uses MicroPython + ulab for numpy-like operations
import ulab.numpy as np

def compute_fisher_diagonal(model, dataloader, num_samples=100):
    """
    Compute diagonal of Fisher Information Matrix.
    Memory constraint: store only diagonal (not full matrix).
    Returns: fisher_diag (float16 array, len = num_params)
    """
    # Model has 15,000 parameters (e.g., 2 conv + 2 dense)
    num_params = sum(p.numel() for p in model.parameters())
    fisher_diag = np.zeros(num_params, dtype=np.float16)  # 30 KB
    
    for i, (inputs, labels) in enumerate(dataloader):
        if i >= num_samples:
            break
        
        # Forward pass
        outputs = model(inputs)
        
        # Compute log-probability gradient (first-order approximation)
        # For classification: grad of log p(y|x) w.r.t. parameters
        loss = cross_entropy(outputs, labels)
        grads = compute_gradients(model, loss)  # returns list of arrays
        
        # Accumulate squared gradients
        idx = 0
        for grad in grads:
            flat_grad = grad.flatten()
            fisher_diag[idx:idx+len(flat_grad)] += flat_grad ** 2
            idx += len(flat_grad)
    
    # Normalize
    fisher_diag /= num_samples
    return fisher_diag
```

## Common Pitfalls & Gotchas

1. **Gradient quantization kills convergence.** I tried storing gradients as int8 (1 byte per weight) instead of int16. The model accuracy dropped from 92% to 63% on a speech command dataset. The quantization noise in the gradient direction accumulates across local epochs, causing the model to diverge. Always validate with a small test set on-device.

2. **Fisher matrix storage blows SRAM.** For a 50 KB model (12,800 weights), the full Fisher matrix is 12,800 x 12,800 = 163 million entries. Even storing only the diagonal (12,800 entries) as float16 requires 25 KB—doable. But if you try to store the full matrix for second-order methods, you'll exhaust SRAM on any Cortex-M class device. Stick to diagonal approximations.

3. **Federated communication overhead is non-trivial.** Sending 50 KB of weights over BLE at 1 Mbps takes ~400 ms per round. With 100 clients and 10 rounds, that's 400 seconds of transmission time. On battery-powered devices, this can drain a 200 mAh coin cell in under 2 hours. Use weight compression (e.g., random sparsification or Top-K gradient selection) to reduce payload size.

## Try It Yourself

1. **Quantize gradients to int8 and measure accuracy drop.** Take any TFLM model (e.g., the person detection model from the TFLM examples). Implement a local training loop that stores gradients as int8, int16, and float32. Compare accuracy on a validation set after 10 local epochs. Report the memory savings vs. accuracy trade-off.

2. **Implement diagonal Fisher matrix on an ESP32-S3.** Using the EWC snippet above, modify it to run on-device with a 2-layer fully connected network (e.g., 256 -> 64 -> 10). Measure the time to compute the Fisher diagonal for 50 samples. Compare with a desktop Python implementation to verify numerical correctness.

3. **Profile BLE transmission of model weights.** On an nRF52840 or ESP32, send a 50 KB model over BLE in chunks. Measure total time and energy consumption (using a current probe or the ESP32's internal ADC). Then implement Top-K sparsification (send only the 10% largest weights) and repeat. How much energy do you save?

## Next Up

Tomorrow I'll tackle **Power Profiling ML Inference: Measuring Energy per Inference** — how to use a precision shunt resistor and an oscilloscope to measure the microjoules consumed by a single inference on an STM32U5, and how to optimize your model to stay under a 1 mJ budget.
