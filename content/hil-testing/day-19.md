---
title: "Day 19: Full Review & Project: Complete HIL Pipeline"
date: 2026-07-01
tags: ["til", "hil-testing", "review", "project", "pipeline"]
---

## What I Explored Today

Today marks the end of our first major block — a full review of the HIL pipeline we've built over the past 18 days. Instead of introducing new concepts, I spent the day stitching together every component into a single, end-to-end project: a production-grade HIL pipeline for a simulated automotive ECU (Electronic Control Unit) running on a Speedgoat real-time target. The pipeline covers firmware compilation, automated test execution on the HIL simulator, real-time data collection, pass/fail reporting, and CI/CD integration with Jenkins. This is the capstone exercise that forces every piece to work together — and trust me, the first integration run revealed exactly where my assumptions were wrong.

## The Core Concept

A complete HIL pipeline is not just about running tests on hardware — it's about creating a closed-loop feedback system that validates firmware changes against real-time hardware behavior, then surfaces results to developers within minutes. The "why" is simple: without a full pipeline, you get manual testing that takes hours, inconsistent test conditions, and bugs that escape to production. The pipeline we've built ensures that every commit to the firmware repository triggers a build, deploys the new binary to the HIL simulator, runs a suite of hardware-in-the-loop tests, collects sensor and actuator data, and reports pass/fail status back to the team. The critical insight is that the pipeline must be deterministic — the same firmware commit must produce the same test results every time, regardless of who runs it or when. This requires careful management of test fixtures, seed values, and hardware state initialization.

## Key Commands / Configuration / Code

Here's the complete Jenkins pipeline definition that ties everything together. This is a Declarative Pipeline that runs on a Jenkins agent with access to the HIL simulator via Ethernet.

```groovy
// Jenkinsfile — Complete HIL Pipeline
pipeline {
    agent { label 'hil-agent' }
    
    environment {
        // Path to firmware binary on the build server
        FIRMWARE_BIN = "${WORKSPACE}/build/firmware.bin"
        // HIL simulator IP (static on isolated network)
        HIL_IP = '192.168.1.100'
        // Test report output directory
        REPORT_DIR = "${WORKSPACE}/reports"
    }
    
    stages {
        stage('Build Firmware') {
            steps {
                // Cross-compile for ARM Cortex-M4 target
                sh 'make -C firmware clean'
                sh 'make -C firmware all'
                // Archive the binary for later stages
                archiveArtifacts artifacts: 'build/firmware.bin'
            }
        }
        
        stage('Deploy to HIL Simulator') {
            steps {
                // Use SCP to transfer binary to Speedgoat real-time target
                sh """
                    scp -o StrictHostKeyChecking=no \
                        ${FIRMWARE_BIN} \
                        hiluser@${HIL_IP}:/home/hiluser/firmware.bin
                """
                // Trigger deployment script on HIL target
                sh """
                    ssh hiluser@${HIL_IP} \
                        '/home/hiluser/deploy_firmware.sh /home/hiluser/firmware.bin'
                """
            }
        }
        
        stage('Run HIL Tests') {
            steps {
                // Execute Python test harness that communicates with HIL via UDP
                sh """
                    python3 test_harness.py \
                        --hil-ip ${HIL_IP} \
                        --test-suite tests/hil_suite.json \
                        --output-dir ${REPORT_DIR} \
                        --timeout 120
                """
            }
        }
        
        stage('Generate Report') {
            steps {
                // Parse test results and generate JUnit XML for Jenkins
                sh """
                    python3 report_generator.py \
                        --input ${REPORT_DIR}/raw_results.json \
                        --output ${REPORT_DIR}/junit_results.xml
                """
                // Publish test results to Jenkins UI
                junit 'reports/junit_results.xml'
            }
        }
    }
    
    post {
        always {
            // Archive all test artifacts regardless of pass/fail
            archiveArtifacts artifacts: 'reports/**/*'
            // Clean up workspace
            cleanWs()
        }
        failure {
            // Send notification to Slack channel
            slackSend(
                channel: '#hil-alerts',
                color: 'danger',
                message: "HIL Pipeline FAILED: ${env.BUILD_URL}"
            )
        }
    }
}
```

The test harness (`test_harness.py`) uses a simple UDP protocol to send test vectors and receive responses from the HIL simulator. Here's the core loop:

```python
# test_harness.py — Core test execution loop (simplified)
import socket, json, time

def run_test_case(test_spec, hil_ip, port=5005):
    """Send test vector to HIL, collect response, validate."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    
    # Send test stimulus (e.g., throttle position, brake pressure)
    stimulus = {
        'test_id': test_spec['id'],
        'inputs': test_spec['inputs'],  # dict of sensor values
        'timestamp': time.time()
    }
    sock.sendto(json.dumps(stimulus).encode(), (hil_ip, port))
    
    # Wait for response from HIL (actuator commands, state)
    data, addr = sock.recvfrom(4096)
    response = json.loads(data.decode())
    
    # Validate against expected outputs
    for key, expected in test_spec['expected_outputs'].items():
        actual = response['outputs'].get(key)
        tolerance = test_spec.get('tolerance', 0.01)
        if abs(actual - expected) > tolerance:
            return {'test_id': test_spec['id'], 'status': 'FAIL',
                    'reason': f'{key}: expected {expected}, got {actual}'}
    
    return {'test_id': test_spec['id'], 'status': 'PASS'}
```

## Common Pitfalls & Gotchas

**1. Network Timeouts on HIL Deployment**  
The SCP and SSH commands in the deploy stage are notoriously flaky if the HIL target is busy running a previous test. Always add retry logic — I use a simple bash loop with a 10-second backoff. Without it, a transient network blip kills the entire pipeline.

**2. Test Non-Determinism from Uninitialized Hardware State**  
If your HIL test suite doesn't reset the simulator to a known state before each test, you'll get different results depending on the previous test's side effects. Always include a `reset_hil()` call at the start of each test case that sets all digital I/O to a default state and clears any internal state machines in the FPGA.

**3. Binary Compatibility Between Build and Target**  
The firmware binary must be compiled with the exact same toolchain version and flags as the HIL simulator expects. I've wasted a day debugging a mysterious crash only to find the build server had updated its ARM GCC toolchain but the HIL target still expected the old ABI. Pin your toolchain version in the Jenkinsfile and use a Docker container for builds.

## Try It Yourself

1. **Extend the test suite**: Add three new test cases to `tests/hil_suite.json` that test an edge case (e.g., maximum sensor input, zero input, and rapid toggling of a digital input). Run the pipeline and verify they pass.

2. **Add a performance metric**: Modify `test_harness.py` to measure the round-trip latency for each test case. Log the minimum, maximum, and average latency to a separate CSV file. Then add a stage in the Jenkinsfile that fails the build if average latency exceeds 50ms.

3. **Implement a hardware watchdog**: In the `post` block of the Jenkinsfile, add a step that pings the HIL simulator after the pipeline completes. If the ping fails, send an email to the team indicating the HIL target may be hung and needs a manual power cycle.

## Next Up

Tomorrow begins **Day 20: Full Review & Project: Complete HIL Pipeline (Part 2)** — we'll dive into advanced failure analysis, add a hardware-in-the-loop regression dashboard, and implement automated rollback of firmware that fails critical safety tests.
