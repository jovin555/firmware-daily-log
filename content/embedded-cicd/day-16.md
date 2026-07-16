---
title: "Day 16: Metrics & Dashboards: Tracking Build Health & Flaky Tests"
date: 2026-07-16
tags: ["til", "embedded-cicd", "metrics", "dashboards"]
---

## What I Explored Today

Today I dove into the metrics and dashboarding layer of our embedded CI/CD pipeline. After weeks of building test infrastructure, we now need to know whether our tests are actually getting better or just noisier. I set up Prometheus metrics export from our Jenkins pipeline, wired them into Grafana, and built a real-time dashboard that tracks build duration, test pass/fail ratios, and—critically—flaky test detection. For embedded systems, where hardware-in-the-loop tests are expensive and time-sensitive, knowing which tests are unreliable is more valuable than raw pass counts.

## The Core Concept

Most embedded teams look at a green/red build status and call it a day. That’s dangerous. A passing build with flaky tests is a ticking time bomb—it masks real regressions until they compound into a broken release. The core insight is that **test health is a time-series signal, not a binary state**. By tracking metrics over time, we can distinguish between:
- **Systematic failures**: A test that fails consistently (e.g., a broken driver) → needs a fix.
- **Flaky failures**: A test that passes and fails unpredictably (e.g., timing-dependent GPIO reads) → needs quarantine or rewrite.
- **Infrastructure failures**: A test that fails because the target board rebooted mid-test → needs retry logic.

The standard approach is to export build-level metrics (duration, pass/fail counts, flake rate) to a time-series database, then build dashboards that show trends. For embedded, we also export board-level metrics: connection stability, flash time, and serial port availability. These are the canaries in the coal mine.

## Key Commands / Configuration / Code

We use Jenkins Pipeline with the Prometheus plugin to expose metrics. Here’s a minimal `Jenkinsfile` snippet that exports custom metrics:

```groovy
// Jenkinsfile — exports build metrics for Prometheus
pipeline {
    agent any
    environment {
        // Unique identifier for this build's target board
        BOARD_ID = "${env.BUILD_TAG}-stm32f4"
    }
    stages {
        stage('Build') {
            steps {
                // Record build start time for duration tracking
                script {
                    build_start = System.currentTimeMillis()
                }
                sh 'make -j4'
            }
        }
        stage('Test') {
            steps {
                script {
                    // Run tests and capture results
                    def testResults = sh(script: 'pytest --junitxml=results.xml', returnStdout: true)
                    def passed = testResults.readLines().findAll { it.contains('PASSED') }.size()
                    def failed = testResults.readLines().findAll { it.contains('FAILED') }.size()
                    // Export as Prometheus gauge metrics
                    prometheus.gauge('embedded_tests_passed', passed, ['board': BOARD_ID])
                    prometheus.gauge('embedded_tests_failed', failed, ['board': BOARD_ID])
                    prometheus.gauge('embedded_build_duration_ms', System.currentTimeMillis() - build_start)
                }
            }
        }
    }
    post {
        always {
            // Track flaky tests: compare current run with last 5 runs
            script {
                def flakyThreshold = 0.4  // 40% pass rate over last 5 runs = flaky
                def testHistory = loadTestHistory()  // custom function reading from DB
                testHistory.each { testName, passRates ->
                    if (passRates.size() >= 5) {
                        def passRate = passRates.sum() / passRates.size()
                        if (passRate > 0.0 && passRate < flakyThreshold) {
                            prometheus.gauge('embedded_test_flaky', 1, ['test': testName, 'board': BOARD_ID])
                        } else {
                            prometheus.gauge('embedded_test_flaky', 0, ['test': testName, 'board': BOARD_ID])
                        }
                    }
                }
            }
        }
    }
}
```

For the Grafana dashboard, here’s a PromQL query to detect flaky tests over the last 24 hours:

```promql
# PromQL: Flaky test detection — tests with pass rate between 10% and 90%
avg_over_time(embedded_tests_passed{board=~"$board"}[1h])
/
(avg_over_time(embedded_tests_passed{board=~"$board"}[1h]) + avg_over_time(embedded_tests_failed{board=~"$board"}[1h]))
> 0.1
and
< 0.9
```

This query returns tests whose pass rate is between 10% and 90% over the last hour—our definition of flaky. We alert on any result.

## Common Pitfalls & Gotchas

1. **Metric cardinality explosion**: If you label every test name and every board serial number, Prometheus will choke. I learned this the hard way after 10,000 unique time series from a single CI run. Solution: aggregate by test suite or board type, not individual instances. Use a separate database for per-test granularity.

2. **Flaky detection without history windows**: A single pass/fail toggle doesn’t mean flaky. You need at least 5–10 runs to compute a meaningful pass rate. I see teams alert on every test that fails once after passing—that’s just noise. Set a minimum sample size (e.g., `count > 5`) in your PromQL.

3. **Ignoring infrastructure metrics**: In embedded, a “test failure” is often a board crash or USB disconnect. If you don’t track board connection stability, you’ll chase phantom regressions. Export a `board_connection_status` metric (0/1) and correlate it with test failures.

## Try It Yourself

1. **Add a build duration metric to your pipeline**: Instrument your CI job to export `build_duration_ms` as a Prometheus gauge. Create a Grafana panel that shows a 7-day trend. If you see spikes, investigate what changed (e.g., new compiler flags, larger firmware image).

2. **Implement flaky test detection with a 5-run window**: Modify your pipeline to store the last 5 pass/fail results for each test. Export a `flaky_score` metric (0.0 = stable pass, 1.0 = stable fail, 0.5 = completely flaky). Set an alert for scores between 0.2 and 0.8.

3. **Build a board health dashboard**: Create a Grafana dashboard with panels for: board connection uptime, flash duration, and serial port errors. Correlate these with test failure rates. You’ll quickly spot which boards need hardware maintenance.

## Next Up

Tomorrow, we’ll tackle **Rollback Pipelines: Automating Recovery from a Bad Release**. When a firmware update bricks a field device, you need a pipeline that can detect the failure, revert to the last known-good build, and reflash the target—all without human intervention. We’ll build a rollback strategy using Git tags, artifact versioning, and a safety interlock that prevents cascading failures.
