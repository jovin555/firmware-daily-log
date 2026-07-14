---
title: "Day 14: Deployment Gates: Manual Approval Before Field Rollout"
date: 2026-07-14
tags: ["til", "embedded-cicd", "deployment-gate"]
---

## What I Explored Today

Today I wired a manual approval gate into our embedded firmware release pipeline. After weeks of automating builds, static analysis, and hardware-in-the-loop tests, the last mile—pushing firmware to field devices—still needed a human in the loop. I implemented a deployment gate using GitLab CI's `when: manual` directive combined with a protected environment that requires explicit sign-off from a release manager before the OTA update job can proceed. The result: every field rollout now requires a named approver, an audit trail, and a mandatory "go" click.

## The Core Concept

Deployment gates are checkpoints in your pipeline that pause execution until a condition is met. For embedded systems, the most critical gate is the one between "passed all tests in the lab" and "now shipping to real devices." Why force a human to click a button when everything is green? Because automated tests cannot capture every field condition: RF interference patterns, power supply quirks, or a sensor that drifts differently at 2 AM in a factory in Malaysia.

The gate serves three purposes:
1. **Accountability** — Someone with domain knowledge explicitly accepts risk.
2. **Coordination** — The gate enforces a "stop and think" moment. Did the QA team finish their exploratory testing? Is the field support team ready for the rollout?
3. **Audit trail** — Every deployment is tied to a person, a timestamp, and (ideally) a release note.

In practice, a deployment gate is not just a boolean flag. It's a structured approval process: the pipeline produces a release artifact (the signed firmware binary), uploads it to a staging bucket, and then blocks. The approver reviews the release notes, the test summary, and the diff from the last fielded version. Only then do they approve, which triggers the actual OTA distribution.

## Key Commands / Configuration / Code

Here's the GitLab CI configuration I used today. The critical piece is the `deploy-to-field` job with `when: manual`. The `needs` keyword ensures it only runs after all validation jobs pass.

```yaml
# .gitlab-ci.yml (excerpt)
stages:
  - build
  - validate
  - gate
  - deploy

variables:
  FIRMWARE_VERSION: "2.4.1-rc3"
  OTA_BUCKET: "s3://firmware-releases/prod/"

build-firmware:
  stage: build
  script:
    - make clean
    - make RELEASE=${FIRMWARE_VERSION}
    - sha256sum build/firmware.bin > build/firmware.sha256
  artifacts:
    paths:
      - build/firmware.bin
      - build/firmware.sha256

run-hil-tests:
  stage: validate
  needs: ["build-firmware"]
  script:
    - python3 scripts/run_hil_suite.py --target stm32h7 --firmware build/firmware.bin
    - python3 scripts/check_results.py --min-pass-rate 98

# The manual gate — requires a GitLab user with "Maintainer" role to click "play"
deploy-to-field:
  stage: deploy
  needs: ["run-hil-tests"]
  when: manual
  environment:
    name: production/field
    url: https://ota.internal.example.com/releases/${FIRMWARE_VERSION}
  script:
    - aws s3 cp build/firmware.bin ${OTA_BUCKET}${FIRMWARE_VERSION}/firmware.bin
    - aws s3 cp build/firmware.sha256 ${OTA_BUCKET}${FIRMWARE_VERSION}/firmware.sha256
    - python3 scripts/trigger_ota.py --version ${FIRMWARE_VERSION} --batch-size 100
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
```

The `environment: production/field` line is key. In GitLab, you can configure protected environments that require approval from specific users or groups. I set this up in the project settings:

```bash
# GitLab API call to add required approvers (run once)
curl --request POST \
  --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  --data "name=production/field&deployment_approval_required=true" \
  "https://gitlab.example.com/api/v4/projects/123/environments"

# Add a user as required approver
curl --request POST \
  --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  --data "user_id=42" \
  "https://gitlab.example.com/api/v4/projects/123/environments/production/field/approvers"
```

For a simpler approach (no API calls), you can use GitLab's UI: Settings → CI/CD → Protected Environments → add `production/field` and select the users/groups who can approve.

The approval workflow in the UI: the pipeline shows a "blocked" icon on the `deploy-to-field` job. The approver clicks the "play" button, and GitLab logs who approved and when. You can also add an approval comment (e.g., "Approved after reviewing HIL logs — no new failures").

## Common Pitfalls & Gotchas

1. **Approval bypass via pipeline retry** — If someone retries a pipeline from the beginning, the manual job resets to "blocked" state. But if they retry *only* the deploy job (skipping the gate), GitLab by default reuses the previous approval. Fix: set `retry: 0` on the deploy job or use GitLab's "prevent outdated approval" setting (available in Ultimate tier). For CE users, add a script check that verifies the approval timestamp is within the last hour.

2. **Environment name mismatch** — The `environment: name` in your YAML must exactly match the protected environment name in GitLab settings. A trailing space or different case will silently skip the protection. I wasted an hour because I named it `production/field` in YAML but `production/field ` (with a space) in the UI. Always copy-paste, never retype.

3. **Artifact expiration** — The firmware binary artifact from the `build` stage has a default expiration of 30 days. If your approval gate sits for two weeks (vacation, emergency bug fix), the artifact may be gone when the approver finally clicks "play." Set `expire_in: 1 year` on the build artifact, or upload the binary to a permanent storage location during the build stage and reference that URL in the deploy job.

## Try It Yourself

1. **Add a manual gate to your existing pipeline.** Pick one deploy job (ideally the one that touches real hardware or a production OTA endpoint) and add `when: manual`. Run the pipeline and verify the job shows as "blocked" in the UI. Approve it and confirm the deploy runs.

2. **Create a protected environment.** In your CI platform (GitLab, GitHub Actions, Jenkins), configure an environment named `production/field` and add yourself as the only approver. Update your deploy job to reference this environment. Push a commit and verify that only you can trigger the deploy.

3. **Add an approval comment requirement.** If your platform supports it, make the approval require a comment. Then write a post-deploy script that logs the comment to your release notes database. This creates an audit trail that ties each deployment to a human rationale.

## Next Up

Tomorrow I'm tackling canary and staged deployment pipelines for firmware. Instead of blasting the update to 10,000 devices at once, I'll roll out to 1% of devices, monitor crash rates for 24 hours, then ramp to 10%, 50%, and finally 100%. We'll look at rollout strategies using feature flags and phased OTA batches.
