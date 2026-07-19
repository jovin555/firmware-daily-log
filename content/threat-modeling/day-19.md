---
title: "Day 19: Denial-of-Service Resilience: Input Validation & Rate Limiting"
date: 2026-07-19
tags: ["til", "threat-modeling", "dos-resilience"]
---

## What I Explored Today

Today I dug into the practical side of defending embedded systems against Denial-of-Service (DoS) attacks at the application layer. While network-level DDoS mitigation is often handled upstream, our firmware must survive resource exhaustion from malformed or excessive inputs. I focused on two complementary defenses: input validation that rejects obviously abusive payloads before they reach processing logic, and rate limiting that prevents a single source from monopolizing CPU, memory, or I/O bandwidth. The key insight: in embedded systems, we don't have the luxury of infinite cloud resources—every byte we accept costs real cycles and RAM.

## The Core Concept

DoS resilience in embedded firmware isn't about stopping every possible attack—it's about bounding worst-case resource consumption. Input validation and rate limiting form a two-layer gate: validation rejects inputs that violate structural or semantic constraints (e.g., a temperature sensor reading of 9999°C), while rate limiting ensures that even valid inputs can't be delivered faster than the system can safely process them.

Why this matters: a single unvalidated input can trigger an exponential blowup in memory allocation (think decompression bombs), or a tight loop that pegs a CPU at 100% while waiting for a timeout. Rate limiting prevents the "slow drip" attack where a low-bandwidth stream of valid requests gradually exhausts connection pools or file descriptors. Together, they enforce a contract: the system guarantees it will never spend more than X microseconds or Y bytes on any single client's request.

## Key Commands / Configuration / Code

### 1. Input Validation: Reject Early, Reject Cheaply

```c
// Example: MQTT topic filter validation for embedded broker
// Reject topics with wildcards in illegal positions or excessive length
bool validate_mqtt_topic(const char *topic, size_t len) {
    // Reject oversized topics before any parsing
    if (len == 0 || len > MAX_TOPIC_LEN) {  // MAX_TOPIC_LEN = 256
        return false;
    }
    
    // Reject null bytes in the middle (potential injection)
    if (memchr(topic, '\0', len) != NULL) {
        return false;
    }
    
    // Reject multi-level wildcard '#' unless it's the last character
    const char *hash = memchr(topic, '#', len);
    if (hash != NULL && hash != topic + len - 1) {
        return false;
    }
    
    // Reject single-level wildcard '+' unless it occupies an entire level
    // (between '/' separators or at start/end)
    for (size_t i = 0; i < len; i++) {
        if (topic[i] == '+') {
            // Must be at start, end, or adjacent to '/'
            if (!(i == 0 || topic[i-1] == '/') ||
                !(i == len-1 || topic[i+1] == '/')) {
                return false;
            }
        }
    }
    return true;
}
```

### 2. Token Bucket Rate Limiter (Fixed-Window with Burst)

```c
// Token bucket state per-client (stored in hash table keyed by source IP)
typedef struct {
    uint32_t tokens;         // Current token count
    uint32_t last_refill_ms; // Last refill timestamp in ms
    uint8_t  violations;     // Consecutive violation counter
} rate_limiter_t;

#define MAX_TOKENS      10    // Max burst size
#define REFILL_RATE_MS  100   // 1 token per 100ms = 10 req/s sustained
#define VIOLATION_LIMIT 5     // Ban after 5 consecutive violations

bool rate_limit_check(rate_limiter_t *rl, uint32_t now_ms) {
    // Refill tokens based on elapsed time
    uint32_t elapsed = now_ms - rl->last_refill_ms;
    if (elapsed >= REFILL_RATE_MS) {
        uint32_t new_tokens = elapsed / REFILL_RATE_MS;
        rl->tokens = min(rl->tokens + new_tokens, MAX_TOKENS);
        rl->last_refill_ms += new_tokens * REFILL_RATE_MS;
    }
    
    // Check if we have a token
    if (rl->tokens > 0) {
        rl->tokens--;
        rl->violations = 0;  // Reset on success
        return true;         // Allow request
    }
    
    // Rate limited: increment violation counter
    rl->violations++;
    if (rl->violations >= VIOLATION_LIMIT) {
        // Ban client for 60 seconds (implemented via separate ban table)
        ban_client(now_ms + 60000);
    }
    return false;
}
```

### 3. Configuration: FreeRTOS Task Stack and Queue Sizing

```c
// In FreeRTOSConfig.h — prevent stack overflow from deep recursion
#define configCHECK_FOR_STACK_OVERFLOW    2  // Enable runtime check
#define configMINIMAL_STACK_SIZE           128  // Words, not bytes

// Network task: limit queue depth to prevent memory exhaustion
#define NETWORK_EVENT_QUEUE_LEN    20  // Max pending events
#define NETWORK_EVENT_QUEUE_SIZE   sizeof(network_event_t)

// Create queue with bounded depth
QueueHandle_t net_queue = xQueueCreate(NETWORK_EVENT_QUEUE_LEN, 
                                       NETWORK_EVENT_QUEUE_SIZE);
// If queue is full, xQueueSend() with 0 timeout will return errQUEUE_FULL
// Never block indefinitely waiting to enqueue
if (xQueueSend(net_queue, &event, 0) != pdPASS) {
    // Drop event — client must retry
    log_warn("Network queue full, dropping event");
}
```

## Common Pitfalls & Gotchas

1. **Rate limiting on connection-oriented protocols without per-client state cleanup.** If you track rate limit state by source IP in a hash table, you must evict entries for clients that disconnect cleanly. Otherwise, a single client cycling through many short-lived connections can fill your state table (a memory exhaustion DoS in itself). Implement an LRU eviction policy or a fixed-size circular buffer.

2. **Input validation that itself allocates memory.** A common mistake is to copy the input into a dynamically allocated buffer before validating it. If an attacker sends a 64KB payload that fails validation, you've already burned 64KB of heap. Validate length and structural constraints *before* any allocation. Use stack buffers for temporary checks when possible.

3. **Assuming rate limiting granularity matches your threat model.** A single token bucket per IP works for a single-threaded server, but if your system has multiple worker tasks (e.g., one per protocol), a client can send one request to each worker and bypass the per-IP limit. You need either a global rate limiter with atomic operations, or per-worker limits that sum to the global budget.

## Try It Yourself

1. **Audit your input validation path.** Pick one protocol handler in your firmware (e.g., HTTP, MQTT, or a custom binary protocol). Trace the path from `recv()` to the first processing function. Identify every point where you could reject the input before allocating memory or starting a loop. Add at least one early rejection check for length or structure.

2. **Implement a token bucket rate limiter.** Write a test harness that simulates 100 requests from a single client in 200ms. Your limiter should allow the first 10 (burst) and then throttle to 10 requests/second. Verify that after 1 second of idle time, the burst capacity resets.

3. **Measure worst-case processing time.** Add a high-resolution timer around your input validation function. Feed it the worst-case valid input and the worst-case invalid input (e.g., maximum length with all characters requiring deep inspection). Ensure both complete in under 1ms on your target hardware. If not, optimize the validation to fail fast on obviously bad inputs.

## Next Up

Tomorrow: **Supply Chain Threats: Third-Party Libraries & SBOM** — how to inventory every dependency, detect known vulnerabilities in your RTOS and middleware, and generate a Software Bill of Materials that your security team actually trusts.
