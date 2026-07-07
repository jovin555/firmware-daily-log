---
title: "Day 07: Artifact Repositories: Storing & Signing Firmware Binaries"
date: 2026-07-07
tags: ["til", "embedded-cicd", "artifact-repo", "signing"]
---

## What I Explored Today

Today I dug into the critical but often-overlooked infrastructure that sits between a successful firmware build and a deployed device: artifact repositories. While most teams have some form of build artifact storage, the specific requirements for embedded systems—binary signing, immutable versioning, OTA package preparation, and hardware-targeted metadata—demand a purpose-built approach. I spent the day evaluating how to structure a repository that treats firmware binaries as first-class, signed, and traceable artifacts rather than just build outputs.

## The Core Concept

In web or mobile development, an artifact is typically a container image or an APK/IPA file. For embedded systems, the artifact is the raw binary that will be flashed onto silicon—often a `.hex`, `.bin`, or `.elf` file, sometimes accompanied by a bootloader image, a filesystem image, and a signature block. The stakes are higher because you can't "hot-patch" a bricked device over the air if the artifact repository served a corrupted binary.

The core concept is **immutable, signed, and metadata-rich storage**. Every firmware binary that leaves your CI pipeline must be:
1. **Immutable** — once published, the binary is never overwritten. Version tags are permanent.
2. **Signed** — using hardware-backed keys (HSM or TPM) so the device can cryptographically verify the binary before accepting an update.
3. **Metadata-enriched** — stored with the git commit SHA, build parameters, target hardware revision, and checksums so you can trace any binary back to its exact source.

A proper artifact repository for embedded systems isn't just a file server. It's a release engineering database that enforces your signing policy, manages key rotation, and provides a clear audit trail from developer commit to field device.

## Key Commands / Configuration / Code

I set up a minimal but production-ready workflow using **GitLab Generic Packages** (works similarly with JFrog Artifactory or AWS CodeArtifact) combined with **signing via OpenSSL** and a hardware security module (HSM) abstraction.

### 1. Publishing a Signed Firmware Binary

```bash
# After a successful build, we have firmware.bin
# Step 1: Generate a detached signature using a private key stored in HSM
# The HSM is accessed via pkcs11-tool or a custom signing service
openssl dgst -sha256 -sign /path/to/hsm-key-proxy.pem \
    -out firmware.bin.sig firmware.bin

# Step 2: Create a metadata manifest
cat > firmware-manifest.json <<EOF
{
  "artifact_name": "sensor-node-v2",
  "version": "2.1.0+build42",
  "git_sha": "${CI_COMMIT_SHA}",
  "target_hw_rev": "B",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "checksum_sha256": "$(sha256sum firmware.bin | cut -d' ' -f1)",
  "signature_algorithm": "sha256WithRSAEncryption"
}
EOF

# Step 3: Upload to artifact repository (GitLab example)
curl --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
     --upload-file firmware.bin \
     "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/firmware/${VERSION}/firmware.bin"

curl --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
     --upload-file firmware.bin.sig \
     "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/firmware/${VERSION}/firmware.bin.sig"

curl --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
     --upload-file firmware-manifest.json \
     "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/firmware/${VERSION}/firmware-manifest.json"
```

### 2. Verification on the Device Side (Bootloader Stub)

```c
// Simplified verification routine in the bootloader
// Assumes the signature and binary are stored contiguously in flash

bool verify_firmware(const uint8_t *binary, size_t bin_len,
                     const uint8_t *signature, size_t sig_len) {
    // Load the public key from a one-time-programmable fuse
    uint8_t public_key[256];
    read_otp_fuse(OTP_PUBLIC_KEY_SLOT, public_key, sizeof(public_key));

    // Use mbedTLS or similar to verify
    mbedtls_rsa_context rsa;
    mbedtls_rsa_init(&rsa, MBEDTLS_RSA_PKCS_V15, 0);
    mbedtls_rsa_import_raw(&rsa, public_key, sizeof(public_key),
                           NULL, NULL, NULL, NULL);

    int ret = mbedtls_rsa_pkcs1_verify(&rsa, NULL, NULL,
                                       MBEDTLS_RSA_PUBLIC,
                                       MBEDTLS_MD_SHA256,
                                       bin_len, binary, signature);
    mbedtls_rsa_free(&rsa);
    return (ret == 0);
}
```

### 3. CI/CD Pipeline Stage for Release Promotion

```yaml
# .gitlab-ci.yml excerpt — promotes from "staging" to "production" repo
promote-to-release:
  stage: release
  script:
    # Copy artifacts from staging to production repository
    - |
      for artifact in firmware.bin firmware.bin.sig firmware-manifest.json; do
        curl --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
             --upload-file "staging/${VERSION}/${artifact}" \
             "${PROD_REPO_URL}/firmware/${VERSION}/${artifact}"
      done
    # Tag the git commit with the release version
    - git tag -a "v${VERSION}" -m "Release ${VERSION}"
    - git push origin "v${VERSION}"
  only:
    - tags
  when: manual  # Requires human approval
```

## Common Pitfalls & Gotchas

1. **Signing keys in CI variables are a security disaster.** I've seen teams store private signing keys as plaintext CI/CD variables. If your CI runner is compromised, every device you've ever shipped is vulnerable. Always use an HSM or a cloud KMS (AWS KMS, Azure Key Vault) with a signing proxy that never exposes the private key material. The CI runner sends a hash to the HSM and gets back a signature.

2. **Forgetting to include the bootloader in the artifact chain.** Your firmware binary is useless if the bootloader that verifies it is a different version or unsigned. Treat the bootloader as a separate artifact with its own signing key and version. Many teams learn this the hard way when an OTA update succeeds but the device won't boot because the bootloader rejected the new firmware.

3. **Metadata drift between CI and artifact repository.** If your CI pipeline calculates checksums and versions in multiple steps, they can diverge. Always compute the checksum immediately after the binary is built, and include it in the manifest *before* uploading. Never re-hash after upload—network transfer corruption is rare but possible, and you want the original build-time checksum for verification.

## Try It Yourself

1. **Set up a local signing workflow.** Create a test firmware binary (any file), generate a self-signed RSA key pair, and sign the binary using `openssl dgst -sha256 -sign`. Then write a short Python script that verifies the signature using the public key. This simulates what your bootloader does.

2. **Configure a generic package repository.** If you have access to GitLab, GitHub Packages, or JFrog Artifactory, create a new repository for firmware artifacts. Publish a dummy binary with a manifest file, then write a CI job that downloads and verifies the checksum matches.

3. **Implement a promotion gate.** Extend your CI pipeline to have two stages: `build-and-sign` and `promote-to-release`. The promotion stage should require manual approval and only run when a git tag is pushed. This mirrors the real-world separation between development builds and official releases.

## Next Up

Tomorrow we tackle **Release Trains: Branching Strategies for Firmware Teams** — how to coordinate multiple hardware variants, hotfixes, and long-term support releases without losing your mind. We'll compare GitFlow, trunk-based development, and the calendar-versioned release train model that works for teams shipping to thousands of devices.
