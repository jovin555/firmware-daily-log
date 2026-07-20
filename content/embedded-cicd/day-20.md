---
title: "Day 20: Cross-Team Pipelines: Coordinating Firmware, Cloud & Mobile Releases"
date: 2026-07-20
tags: ["til", "embedded-cicd", "cross-team", "coordination"]
---

## What I Explored Today

Today I tackled the coordination problem that emerges when your embedded product ships three interdependent artifacts: firmware for the device, a cloud backend API, and a mobile app. Each team owns its pipeline, but the release must be atomic from the user's perspective. I spent the day designing a cross-team release pipeline using GitLab CI/CD with a shared release manifest, artifact promotion gates, and a coordination layer that prevents the mobile app from hitting an API endpoint that expects firmware features not yet deployed.

## The Core Concept

The fundamental tension is that firmware, cloud, and mobile have different release cadences. Firmware might ship monthly, cloud weekly, and mobile bi-weekly with app store review delays. Yet a new feature—say, OTA rollback support—requires changes in all three. If the mobile app ships before the firmware supports the new API, users get errors. If the cloud API changes before the firmware can handle it, devices break.

The solution is a **release compatibility matrix** stored as a versioned manifest in a shared repository. Each pipeline publishes its build artifacts and declares which versions of the other components it is compatible with. A coordination pipeline (triggered by any team) reads the manifest, validates that a set of candidate versions forms a compatible graph, and only then promotes the artifacts to production. This is essentially a dependency resolution problem, but with the added constraint that firmware cannot be rolled back easily once deployed to field devices.

## Key Commands / Configuration / Code

### 1. Release Manifest Schema (YAML)

Stored in a shared `release-manifests/` repo, each team commits a manifest for their release candidate:

```yaml
# firmware-v2.3.1-manifest.yaml
apiVersion: v1
kind: ReleaseManifest
component: firmware
version: "2.3.1"
compatible:
  cloud: ">=1.8.0 <2.0.0"
  mobile: ">=3.2.0"
artifacts:
  - type: binary
    url: "s3://firmware-releases/v2.3.1/fw.bin"
    checksum: "sha256:abc123..."
  - type: ota-package
    url: "s3://firmware-releases/v2.3.1/ota.pkg"
```

### 2. Coordination Pipeline (GitLab CI)

This pipeline runs when any team triggers a release candidate. It validates compatibility before promoting:

```yaml
# .gitlab-ci.yml in coordination repo
stages:
  - validate
  - promote

validate-compatibility:
  stage: validate
  image: alpine:3.19
  script:
    - apk add --no-cache yq jq curl
    # Fetch all candidate manifests from the release branch
    - |
      for comp in firmware cloud mobile; do
        curl -s "https://gitlab.com/api/v4/projects/123/repository/files/${comp}-manifest.yaml/raw?ref=release-candidate" \
          -o "/manifests/${comp}.yaml"
      done
    # Run compatibility check using semver range matching
    - |
      fw_cloud=$(yq '.compatible.cloud' /manifests/firmware.yaml)
      cloud_version=$(yq '.version' /manifests/cloud.yaml)
      if ! semver -r "$fw_cloud" "$cloud_version"; then
        echo "ERROR: Firmware requires cloud $fw_cloud, but cloud is $cloud_version"
        exit 1
      fi
    # Repeat for all pairs (firmware-mobile, cloud-mobile)
    - echo "All compatibility constraints satisfied"

promote-artifacts:
  stage: promote
  needs: [validate-compatibility]
  script:
    # Tag each component's artifact as "production-ready"
    - |
      for comp in firmware cloud mobile; do
        version=$(yq '.version' "/manifests/${comp}.yaml")
        # Move artifact from staging to production bucket
        aws s3 cp "s3://staging-artifacts/${comp}/${version}/" \
                  "s3://production-artifacts/${comp}/${version}/" --recursive
        # Tag the git commit in each team's repo
        curl -X POST "https://gitlab.com/api/v4/projects/${comp_project_id}/repository/tags" \
          -H "PRIVATE-TOKEN: $CI_JOB_TOKEN" \
          -d "tag_name=v${version}&ref=release-candidate"
      done
```

### 3. Mobile App Version Pinning (Swift Example)

The mobile app reads the compatibility manifest at build time to decide which API base URL to use:

```swift
// ReleaseCoordinator.swift
struct ReleaseManifest: Decodable {
    let firmwareVersion: String
    let cloudVersion: String
    let minAPIVersion: String
}

func configureAPIEndpoint() {
    guard let manifestURL = Bundle.main.url(forResource: "release-manifest", withExtension: "json"),
          let data = try? Data(contentsOf: manifestURL),
          let manifest = try? JSONDecoder().decode(ReleaseManifest.self, from: data) else {
        fatalError("Missing release manifest")
    }
    // If firmware is older than 2.3.0, use legacy API path
    if manifest.firmwareVersion < "2.3.0" {
        API.baseURL = "https://api.legacy.example.com/v1"
    } else {
        API.baseURL = "https://api.example.com/v2"
    }
}
```

## Common Pitfalls & Gotchas

1. **Semver range parsing inconsistencies** — Different tools (npm semver, Python `semver`, Rust `semver`) have subtle differences in how they handle prerelease tags and ranges. Firmware versions often include build metadata (e.g., `2.3.1+build42`), which some parsers ignore and others treat as a higher version. Standardize on one parser across all pipelines, and pin its version. We use the Rust `semver` crate via a small CLI tool compiled once and distributed as a Docker image.

2. **The "stale manifest" problem** — If the cloud team updates their manifest while the coordination pipeline is running, the validation step might pass with stale data. Solution: lock the release branch at the start of the coordination pipeline using GitLab's `merge_request:lock` API, preventing any further commits until the pipeline completes or times out.

3. **Firmware cannot be rolled back** — Unlike cloud or mobile, you cannot force-update a device in the field if a compatibility issue is discovered post-release. The coordination pipeline must include a **manual approval gate** for firmware promotion, and the release manifest should include a `rollbackPolicy` field (e.g., "safe" or "critical") that blocks automatic promotion if the firmware version is marked as critical.

## Try It Yourself

1. **Build a compatibility checker script** — Write a Python or Bash script that reads three YAML manifests (firmware, cloud, mobile) and validates all pairwise semver constraints. Use the `semver` library (Python) or `yq` + `semver-tool` (Bash). Test it with a deliberately incompatible set (e.g., firmware requires cloud `>=2.0`, but cloud manifest says `1.9.0`).

2. **Add a manual approval gate** — In your CI platform (GitLab, GitHub Actions, Jenkins), add a `manual` job between validation and promotion that requires a human to approve the firmware release. In GitLab, this is `when: manual` with `allow_failure: false`. Verify that the pipeline blocks promotion until approved.

3. **Simulate a cross-team release** — Create three dummy repositories (firmware, cloud, mobile) each with a simple CI pipeline that produces a versioned artifact. Set up a fourth coordination repo that triggers on new tags in any of the three. Implement the manifest validation and promotion flow. Run a full cycle: commit a firmware change, tag it, watch the coordination pipeline validate and promote all three.

## Next Up

Tomorrow: **Chaos Engineering for Firmware Release Pipelines** — We'll inject network failures, corrupted OTA packages, and API latency into our cross-team pipeline to see if the coordination layer actually survives real-world chaos. Spoiler: your semver parser will be the least of your worries.
