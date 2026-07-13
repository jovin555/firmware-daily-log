---
title: "Day 13: AWS IoT & Azure Device Update Fleet OTA Pipelines"
date: 2026-07-13
tags: ["til", "secure-ota", "aws-iot", "azure-adu"]
---

## What I Explored Today

Today I dug into the two dominant cloud-managed OTA pipelines for fleet management: AWS IoT Device Management's OTA Update Jobs and Azure Device Update for IoT Hub (ADU). Both platforms promise "one-click" fleet updates, but the devil is in the deployment details—signing chains, rollback policies, and artifact storage. I built a dual-pipeline test harness using a Raspberry Pi 4 running Yocto Linux, pushing firmware blobs to both clouds and measuring end-to-end latency, failure modes, and recovery behavior.

## The Core Concept

Why do you need a cloud-managed OTA pipeline instead of rolling your own MQTT-based updater? Three reasons: **auditability**, **graduated rollout**, and **device state reconciliation**.

When you manage 10,000+ devices, you cannot afford to have a device silently fail an update and stay on a vulnerable firmware version. Cloud pipelines enforce a state machine: `Downloading → Verifying → Applying → Reboot → Reporting`. If a device stalls at any step, the cloud job marks it as `FAILED` and triggers alerts. Both AWS and Azure provide this as a managed service, but they differ in how they handle artifact signing, deployment groups, and rollback.

AWS IoT Jobs uses a "document-based" approach: you define a job document (JSON) that tells the device what to download and where to put it. The device agent (or your custom code) interprets this document. Azure ADU uses a more opinionated "update manifest" with built-in compatibility checks and a two-phase approval workflow (import → deploy).

The critical architectural difference: AWS leaves artifact signing to your own KMS/Code Signing for IoT pipeline, while Azure ADU bakes signing into the import process using a root certificate you upload. Both are secure, but the operational overhead differs.

## Key Commands / Configuration / Code

### AWS IoT OTA Job Creation (CLI)

```bash
# Step 1: Create a signing profile (first time only)
aws iot create-signing-profile \
    --profile-name "firmware-signer" \
    --platform "Raspbian" \
    --certificate-validation-visibility "CHECK" \
    --signing-parameters '{"certificateArn":"arn:aws:acm:us-east-1:123456789012:certificate/abc-123"}'

# Step 2: Create the OTA update (this generates the job document)
aws iot create-ota-update \
    --ota-update-id "v2.1.3-firmware" \
    --targets "arn:aws:iot:us-east-1:123456789012:thinggroup/production-fleet" \
    --target-selection "SNAPSHOT" \
    --files "fileLocation={s3Bucket={bucket=ota-artifacts,key=firmware-v2.1.3.bin},codeSigning={awsSigningJobId=$(aws iot start-signing-job ...)}" \
    --role-arn "arn:aws:iam::123456789012:role/ota-service-role" \
    --protocols "MQTT" \
    --additional-parameters '{"aws:iot:ota:numOfRetries":3,"aws:iot:ota:maxDurationSeconds":3600}'

# Step 3: Monitor job execution
aws iot list-job-executions-for-thing \
    --thing-name "device-42" \
    --status "IN_PROGRESS"
```

### Azure ADU Import & Deployment (Azure CLI + REST)

```bash
# Step 1: Import update manifest (must be signed with your root cert)
az iot du update import \
    --instance "my-adu-instance" \
    --manifest "import-manifest.json" \
    --content "https://mystorage.blob.core.windows.net/updates/firmware-v2.1.3.bin" \
    --wait

# import-manifest.json structure (simplified)
# {
#   "updateId": { "provider": "contoso", "name": "firmware", "version": "2.1.3" },
#   "compatibility": [{ "deviceManufacturer": "contoso", "deviceModel": "rpi4" }],
#   "instructions": { "steps": [{ "type": "inline", "handler": "microsoft/script:1", "files": ["firmware-v2.1.3.bin"] }] },
#   "files": [{ "filename": "firmware-v2.1.3.bin", "sizeInBytes": 4194304, "hashes": { "sha256": "abc..." } }]
# }

# Step 2: Create a deployment group (canary first)
az iot du device-group create \
    --instance "my-adu-instance" \
    --group-id "canary-rpi4" \
    --tags "{\"environment\":\"canary\",\"model\":\"rpi4\"}" \
    --update-compliance "LatestUpdate"

# Step 3: Deploy to group
az iot du deployment create \
    --instance "my-adu-instance" \
    --group-id "canary-rpi4" \
    --deployment-id "deploy-v2.1.3-canary-001" \
    --update-id "{\"provider\":\"contoso\",\"name\":\"firmware\",\"version\":\"2.1.3\"}" \
    --rollback-policy "{\"update\":{\"id\":{\"provider\":\"contoso\",\"name\":\"firmware\",\"version\":\"2.0.9\"}}}" \
    --microsoft-connected-cache "{\"level\":\"MicrosoftConnectedCache\"}"
```

### Device-Side Agent (C, simplified for AWS IoT Jobs)

```c
// Callback when a new job document arrives via MQTT topic: $aws/things/{thingName}/jobs/notify-next
void job_execution_callback(const char *job_id, const char *job_document) {
    // Parse JSON for "url", "fileSize", "fileHash"
    cJSON *doc = cJSON_Parse(job_document);
    cJSON *url = cJSON_GetObjectItem(doc, "url");
    cJSON *expected_hash = cJSON_GetObjectItem(doc, "fileHash");

    // Download to /tmp/update.bin
    http_download(url->valuestring, "/tmp/update.bin");

    // Verify SHA-256
    uint8_t actual_hash[32];
    sha256_file("/tmp/update.bin", actual_hash);
    if (memcmp(actual_hash, expected_hash->valuestring, 32) != 0) {
        report_job_status(job_id, JOB_FAILED, "Hash mismatch");
        return;
    }

    // Apply update (e.g., call swupdate or rauc)
    system("rauc install /tmp/update.bin");
    report_job_status(job_id, JOB_SUCCEEDED, "Update applied, rebooting");
}
```

## Common Pitfalls & Gotchas

1. **Signing key management is not optional.** Both platforms enforce signed updates, but the failure mode differs. AWS will reject an unsigned job document at the device agent level (your code must check the signature). Azure ADU rejects unsigned manifests at the cloud import step—you cannot even stage the update. I spent two hours debugging why Azure ADU kept returning `400 BadRequest` on import; the error message said "signature verification failed" but the portal showed a generic "invalid manifest" error. Always check the `adu-import.log` on the device side.

2. **Device group membership is eventually consistent.** In Azure ADU, when you add a tag to a device, it can take up to 5 minutes for the device to appear in the correct deployment group. AWS IoT thing groups are near-instantaneous. If you deploy to a group immediately after creating it, you may miss devices. Always add a 10-minute buffer between group creation and deployment initiation.

3. **Rollback is not automatic—you must define it.** AWS IoT Jobs does not have a built-in rollback mechanism; you must create a separate job to push the previous firmware. Azure ADU allows you to define a rollback policy in the deployment, but it only works if the previous version is still imported and compatible. I learned this the hard way when a botched update bricked 12 devices in my canary group because the rollback target firmware had been deleted from the artifact store. Always keep at least one previous version imported.

## Try It Yourself

1. **Set up a dual-pipeline test with one device.** Register a Raspberry Pi (or VM) with both AWS IoT Core and Azure IoT Hub. Create a simple firmware blob (e.g., a text file that changes a LED blink pattern). Push the same update through both pipelines and compare the end-to-end time from "deploy" to "device reports success." Note the differences in job creation steps.

2. **Force a hash mismatch and observe the failure mode.** Modify the firmware blob after signing but before upload. In AWS, watch the job execution status change to `FAILED` with reason "Hash mismatch." In Azure ADU, the device will report `DownloadFailed` in the deployment status. Capture the MQTT topics where these failure messages are published.

3. **Implement a rollback job in AWS IoT.** Create a second OTA update job that targets the same thing group but points to the previous firmware version. Use the `--target-selection "SNAPSHOT"` flag to ensure only devices currently online receive the rollback. Monitor the job execution list to confirm all devices roll back within 5 minutes.

## Next Up

Tomorrow, I’ll tackle **Staged Rollouts: Canary Groups & Percentage-Based Deployment**—how to safely push updates to 1% of your fleet, monitor for regressions, and automatically halt the rollout when error rates spike. We’ll build a canary pipeline that uses AWS IoT Device Defender metrics as a gating condition.
