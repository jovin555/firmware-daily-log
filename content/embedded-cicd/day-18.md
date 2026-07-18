---
title: "Day 18: Nightly & Long-Running Soak Test Orchestration"
date: 2026-07-18
tags: ["til", "embedded-cicd", "nightly-build", "soak-test"]
---

## What I Explored Today

Today I tackled the orchestration of nightly builds and long-running soak tests—the kind of automated verification that runs for 8, 12, or even 48 hours to catch memory leaks, thermal drift, and race conditions that unit tests never expose. I wired up a Jenkins pipeline that triggers at 02:00 UTC, deploys firmware to a fleet of physical devices, runs a multi-hour stress workload, and collects telemetry for post-processing. The key insight: soak tests are not just longer unit tests—they require different infrastructure, different failure handling, and different reporting.

## The Core Concept

Nightly builds serve a dual purpose in embedded CI/CD. First, they catch regressions that slipped through the commit-triggered pipeline—often because the full test matrix (all targets, all configurations) is too expensive to run on every push. Second, they host long-running soak tests that measure system stability over time.

Soak tests are fundamentally different from functional tests. A functional test checks "does feature X work?" A soak test checks "does the system still work after 12 hours of continuous operation?" The failure modes are different: memory fragmentation, watchdog timer resets, flash wear, clock drift, and thermal throttling. You cannot simulate these in a 30-second CI job.

The orchestration challenge is threefold:
1. **Device management** — reserving physical hardware for the duration of the test
2. **Telemetry collection** — streaming logs, metrics, and core dumps without filling device storage
3. **Graceful abort** — detecting when a test has already failed and stopping early to free resources

## Key Commands / Configuration / Code

Here's a Jenkins declarative pipeline for a nightly soak test that runs on a pool of Raspberry Pi 4 devices acting as embedded targets:

```groovy
// Jenkinsfile.nightly-soak
pipeline {
    agent { label 'soak-runner' }
    
    triggers {
        // Run every night at 2 AM UTC
        cron('0 2 * * *')
    }
    
    parameters {
        string(name: 'SOAK_DURATION_HOURS', defaultValue: '12')
        string(name: 'FIRMWARE_VERSION', defaultValue: 'latest')
    }
    
    environment {
        DEVICE_POOL = 'soak-pool-01'
        TELEMETRY_BUCKET = 's3://embedded-telemetry/soak/'
    }
    
    stages {
        stage('Reserve Devices') {
            steps {
                script {
                    // Use a lockable resource plugin to reserve 4 devices
                    lock(resource: env.DEVICE_POOL, quantity: 4) {
                        echo "Reserved 4 devices from pool ${env.DEVICE_POOL}"
                    }
                }
            }
        }
        
        stage('Flash Firmware') {
            steps {
                script {
                    def devices = ['device-01', 'device-02', 'device-03', 'device-04']
                    parallel devices.collectEntries { device ->
                        ["Flash-${device}" : {
                            sh """
                                openocd -f interface/raspberrypi-swd.cfg \
                                        -f target/rp2040.cfg \
                                        -c "program ${env.FIRMWARE_VERSION}.elf verify reset exit"
                            """
                        }]
                    }
                }
            }
        }
        
        stage('Run Soak Test') {
            steps {
                timeout(time: env.SOAK_DURATION_HOURS.toInteger() + 1, unit: 'HOURS') {
                    script {
                        // Start telemetry collection in background
                        sh 'nohup python3 collect_telemetry.py --output-dir /tmp/soak-logs &'
                        
                        // Deploy and run the soak workload
                        sh """
                            python3 soak_runner.py \
                                --devices device-01,device-02,device-03,device-04 \
                                --workload stress_memory_network \
                                --duration ${env.SOAK_DURATION_HOURS}h \
                                --health-check-interval 60s \
                                --abort-on-failure
                        """
                    }
                }
            }
        }
        
        stage('Collect Artifacts') {
            steps {
                sh """
                    tar czf soak-results-${BUILD_NUMBER}.tar.gz /tmp/soak-logs/
                    aws s3 cp soak-results-${BUILD_NUMBER}.tar.gz \
                        ${TELEMETRY_BUCKET}${BUILD_NUMBER}/
                """
                archiveArtifacts artifacts: 'soak-results-*.tar.gz'
            }
        }
        
        stage('Generate Report') {
            steps {
                sh """
                    python3 generate_soak_report.py \
                        --input /tmp/soak-logs \
                        --output soak-report-${BUILD_NUMBER}.html \
                        --threshold-memory-leak 5% \
                        --threshold-cpu-avg 80%
                """
                publishHTML(target: [
                    reportName: 'Soak Test Report',
                    reportDir: '.',
                    reportFiles: "soak-report-${BUILD_NUMBER}.html"
                ])
            }
        }
    }
    
    post {
        always {
            // Release devices and clean up
            sh 'python3 release_devices.py --pool ${DEVICE_POOL}'
            cleanWs()
        }
        failure {
            // Send alert with first-failure log snippet
            sh """
                tail -100 /tmp/soak-logs/error.log | \
                mail -s "SOAK FAILURE: Build ${BUILD_NUMBER}" \
                    embedded-team@company.com
            """
        }
    }
}
```

The `soak_runner.py` script (simplified) that handles health checks and early abort:

```python
#!/usr/bin/env python3
# soak_runner.py — orchestrates workload and health checks
import argparse, asyncio, time, json

async def health_check(device):
    """Ping device and check critical metrics"""
    result = await run_ssh(device, "cat /proc/meminfo | grep MemFree")
    mem_free = int(result.split()[1])
    if mem_free < 50000:  # less than 50MB free
        raise DeviceHealthError(f"{device}: memory critically low ({mem_free} kB)")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--devices')
    parser.add_argument('--duration')
    parser.add_argument('--health-check-interval', default=60)
    parser.add_argument('--abort-on-failure', action='store_true')
    args = parser.parse_args()
    
    devices = args.devices.split(',')
    end_time = time.time() + parse_duration(args.duration)
    
    while time.time() < end_time:
        for device in devices:
            try:
                await health_check(device)
            except DeviceHealthError as e:
                if args.abort_on_failure:
                    print(f"ABORT: {e}")
                    sys.exit(1)
        await asyncio.sleep(int(args.health_check_interval))

if __name__ == '__main__':
    asyncio.run(main())
```

## Common Pitfalls & Gotchas

**1. Device drift during long runs**
After 6+ hours, device clocks can drift by seconds, timestamps become misaligned, and SSH connections drop. Always use NTP sync at test start and implement reconnection logic with exponential backoff. I once lost 8 hours of telemetry because a device's RTC battery died and timestamps jumped to 1970.

**2. Log rotation on the device**
Embedded devices have limited flash. If your soak test writes logs at 1 MB/hour, a 48-hour test fills 48 MB—which may exceed available storage and cause the test to fail from disk-full errors, not the actual workload. Pre-allocate a log buffer and use a circular buffer or stream logs off-device in real time.

**3. False positives from watchdog timers**
Many embedded systems have hardware watchdogs that reset the device if the main loop blocks for too long. Your soak workload might legitimately pause for 10 seconds during a flash erase, triggering a watchdog reset. Either disable the watchdog during soak tests or adjust the timeout to match the workload's worst-case latency.

## Try It Yourself

1. **Add a soak test stage to your existing nightly pipeline.** Start with a 1-hour run that exercises memory allocation and deallocation in a loop. Monitor `/proc/meminfo` every minute and fail the build if free memory drops by more than 10% over the run.

2. **Implement an early-abort mechanism.** Write a health check that pings your device every 30 seconds. If three consecutive pings fail, kill the soak test, collect the logs up to that point, and mark the build as unstable (not failed—network issues happen).

3. **Set up telemetry streaming.** Instead of writing logs to device flash, configure your test harness to stream serial output via `socat` to a cloud storage bucket. Verify that you can reconstruct the full timeline even if the device resets mid-test.

## Next Up

Tomorrow we dive into **Managing Secrets in CI: Signing Keys & Provisioning Credentials**—how to store, rotate, and inject private keys for firmware signing without exposing them in logs or build artifacts. We'll cover HashiCorp Vault integration, hardware security module (HSM) access from CI runners, and the dreaded "key in a git repo" horror story.
