---
title: "Day 16: Integrating Static Analysis in CI: Fail on Warnings"
date: 2026-06-28
tags: ["til", "formal-verification", "ci", "static-analysis", "gates"]
---

## What I Explored Today

Today I tackled the practical reality of making static analysis a hard gate in CI pipelines. The goal: configure a pipeline so that any new warning from tools like `clang-tidy`, `cppcheck`, or `Coverity` causes the build to fail. I worked through the exact configuration for GitHub Actions, Jenkins, and GitLab CI, handling exit codes, baseline suppression, and the inevitable friction with legacy codebases.

## The Core Concept

Static analysis is only as good as its enforcement. Running analysis and posting results to a dashboard is useful for trend tracking, but it doesn't prevent regressions. The real power comes when you **fail the pipeline on new warnings**.

The principle is simple: treat static analysis warnings like compiler warnings. If you wouldn't let a `-Werror` build pass with a new warning, don't let a static analysis build pass either. This creates a tight feedback loop: every commit must either fix the issue or explicitly suppress it with a documented justification.

The challenge is that most real-world codebases have thousands of pre-existing warnings. You can't flip the switch overnight. The solution is a **baseline file** — a snapshot of current warnings that the CI system subtracts from the current run. Only *new* warnings trigger a failure.

## Key Commands / Configuration / Code

### GitHub Actions with `clang-tidy` and baseline

```yaml
# .github/workflows/static-analysis.yml
name: Static Analysis Gate

on: [push, pull_request]

jobs:
  clang-tidy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate compile_commands.json
        run: cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

      - name: Run clang-tidy with baseline
        run: |
          # Generate current warnings, filter against baseline
          clang-tidy --quiet \
            -p build \
            src/*.cpp 2>&1 \
            | tee current_warnings.txt

          # Compare with baseline (exit 1 if new warnings)
          python3 scripts/check_baseline.py \
            --baseline .clang-tidy-baseline.txt \
            --current current_warnings.txt
```

### Baseline comparison script (Python)

```python
#!/usr/bin/env python3
# scripts/check_baseline.py
import sys, re

def parse_warnings(filepath):
    """Extract warning signatures: file:line:column:warning-id"""
    warnings = set()
    pattern = r'([^:]+:\d+:\d+): (warning: .+?)(?: \[.+\])?$'
    with open(filepath) as f:
        for line in f:
            m = re.search(pattern, line)
            if m:
                warnings.add(m.group(0).strip())
    return warnings

if __name__ == '__main__':
    baseline = parse_warnings(sys.argv[2])  # --baseline file
    current = parse_warnings(sys.argv[4])   # --current file
    new_warnings = current - baseline

    if new_warnings:
        print(f"FAIL: {len(new_warnings)} new warning(s) detected:")
        for w in sorted(new_warnings):
            print(f"  {w}")
        sys.exit(1)
    else:
        print("PASS: No new warnings.")
        sys.exit(0)
```

### GitLab CI with `cppcheck` and error-level gate

```yaml
# .gitlab-ci.yml
static-analysis:
  stage: test
  script:
    - cppcheck --enable=all --suppress=*:legacy/* --error-exitcode=1 src/
  only:
    - merge_requests
```

The `--error-exitcode=1` flag makes `cppcheck` return a non-zero exit code when any warning (not just errors) is found. The `--suppress=*:legacy/*` pattern suppresses all warnings in the `legacy/` directory — a pragmatic escape hatch for code you can't fix yet.

### Jenkins pipeline with `Coverity` and baseline

```groovy
// Jenkinsfile
pipeline {
    agent any
    stages {
        stage('Coverity Analysis') {
            steps {
                sh '''
                    cov-build --dir cov-int make -j$(nproc)
                    cov-analyze --dir cov-int --all
                    # Fail if new defects found (baseline stored in S3)
                    cov-diff --dir cov-int \
                        --baseline s3://my-bucket/baseline/cov-baseline.json \
                        --report new-defects.json
                    if [ -s new-defects.json ]; then
                        echo "New defects found!"
                        exit 1
                    fi
                '''
            }
        }
    }
}
```

## Common Pitfalls & Gotchas

**1. Baseline drift and stale suppressions**
Your baseline file will grow stale as you fix warnings. If you never regenerate it, the baseline becomes a permanent pass for old warnings you've already fixed. Solution: regenerate the baseline after every release or sprint by running the analysis on a known-good commit and overwriting the baseline file. Automate this with a weekly cron job.

**2. False positives from missing `compile_commands.json`**
`clang-tidy` needs a compilation database to understand macros, includes, and preprocessor defines. Without it, you'll get spurious warnings about missing headers or undefined symbols. Always generate `compile_commands.json` via CMake (`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`) or Bear (`bear -- make`). Verify the file exists before running analysis.

**3. The "warning avalanche" from a single header change**
A change to a widely-included header can trigger hundreds of new warnings across translation units. This is frustrating because the developer who made the change may not have touched those files. Mitigation: run analysis only on changed files (using `git diff --name-only`) and enforce the gate only on those files. This keeps the feedback local and actionable.

## Try It Yourself

1. **Set up a baseline for your project**: Run `clang-tidy` on your entire codebase, capture the output to a file, and commit it as `.clang-tidy-baseline.txt`. Then implement the `check_baseline.py` script above and run it locally to verify it correctly identifies new warnings.

2. **Add a CI gate for a single directory**: In your CI config, add a step that runs `cppcheck --error-exitcode=1` on only one module (e.g., `src/new_feature/`). Make a deliberate change that introduces a new warning (like an uninitialized variable) and confirm the pipeline fails.

3. **Implement the "changed files only" filter**: Write a script that uses `git diff --name-only HEAD~1` to get changed files, then passes only those files to `clang-tidy`. Integrate this into your CI pipeline and verify it catches warnings only in the changed files.

## Next Up

Tomorrow we move from code-level verification to system-level reasoning: **Safety Case Documentation: GSN & CAE Notation**. We'll cover how to structure argumentation for critical systems using Goal Structuring Notation and Claims-Arguments-Evidence, and how these diagrams map to your static analysis results.
