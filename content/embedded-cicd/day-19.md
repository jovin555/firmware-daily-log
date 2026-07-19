---
title: "Day 19: Managing Secrets in CI: Signing Keys & Provisioning Credentials"
date: 2026-07-19
tags: ["til", "embedded-cicd", "secrets-management", "ci"]
---

## What I Explored Today

Today I tackled one of the most sensitive aspects of embedded CI/CD: managing secrets like code signing keys, provisioning profiles, and hardware authentication tokens. In our firmware pipeline, we need to sign bootloaders with a hardware-backed HSM key, provision device certificates from a PKI infrastructure, and inject Wi-Fi credentials at flash time — all without exposing secrets to developers or CI logs. I explored how to integrate HashiCorp Vault with GitHub Actions and Jenkins, and how to handle hardware security modules (HSMs) in ephemeral CI runners.

## The Core Concept

The fundamental tension in embedded CI is that **secrets must be available to the build but invisible to the builder**. Unlike web apps where secrets are often environment variables, embedded systems require binary blobs (signing keys, provisioning certificates) that get embedded into firmware images. If a signing key leaks, an attacker can sign malicious firmware that a device will accept as authentic.

The solution is a **secrets broker** — a dedicated service (Vault, AWS Secrets Manager, Azure Key Vault) that authenticates the CI runner via short-lived tokens (OIDC, JWT) and serves secrets only for the duration of the build. The CI runner never stores secrets on disk; it requests them at build time, uses them in memory, and discards them. For hardware-backed keys (HSMs, TPMs), the CI runner sends a signing request to the HSM and receives only the signature, never the private key.

The key architectural pattern is **zero-trust secrets delivery**: the CI system proves its identity to the secrets broker, the broker verifies the pipeline context (branch, repo, job), and only then releases the secret scoped to that specific build.

## Key Commands / Configuration / Code

### 1. Vault OIDC Authentication in GitHub Actions

```yaml
# .github/workflows/firmware-sign.yml
jobs:
  sign-firmware:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # Required for OIDC token
      contents: read
    steps:
      - uses: actions/checkout@v4

      # Authenticate to Vault using GitHub's OIDC token
      - name: Authenticate to Vault
        id: vault-auth
        run: |
          # Fetch JWT from GitHub's OIDC provider
          JWT=$(curl -s -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=vault" | jq -r '.value')
          
          # Exchange JWT for Vault token
          VAULT_TOKEN=$(curl -s \
            --request POST \
            --data "{\"role\":\"firmware-signer\",\"jwt\":\"$JWT\"}" \
            https://vault.internal:8200/v1/auth/github/login | jq -r '.auth.client_token')
          
          echo "VAULT_TOKEN=$VAULT_TOKEN" >> $GITHUB_ENV

      # Fetch signing key (never printed to logs)
      - name: Fetch signing key
        run: |
          curl -s -H "X-Vault-Token: $VAULT_TOKEN" \
            https://vault.internal:8200/v1/secret/data/firmware/signing-key \
            | jq -r '.data.data.private_key' > /tmp/signing_key.pem
          # Immediately revoke Vault token
          curl -s --request POST \
            -H "X-Vault-Token: $VAULT_TOKEN" \
            https://vault.internal:8200/v1/auth/token/revoke-self

      - name: Sign firmware
        run: |
          # Use the key in memory, then wipe
          openssl dgst -sha256 -sign /tmp/signing_key.pem -out firmware.sig firmware.bin
          shred -u /tmp/signing_key.pem
```

### 2. HSM Signing via PKCS#11 (SoftHSM for CI)

```bash
# In CI runner, using SoftHSM as a proxy to real HSM
# Install SoftHSM2 and configure token
sudo apt-get install softhsm2 opensc
softhsm2-util --init-token --slot 0 --label "CI_SIGNING" --pin 1234 --so-pin 5678

# Load key from Vault into HSM session (key never touches disk)
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so \
  --login --pin 1234 \
  --write-object <(vault read -field=private_key secret/firmware/signing-key) \
  --type privkey --id 01 --label "firmware_key"

# Sign using HSM (key stays in HSM)
openssl dgst -sha256 -engine pkcs11 -keyform engine \
  -key "pkcs11:token=CI_SIGNING;object=firmware_key;pin-value=1234" \
  -out firmware.sig firmware.bin
```

### 3. Provisioning Credentials Injection (Wi-Fi + Device Cert)

```python
# scripts/inject_provisioning.py
# Called in CI after firmware build
import os, sys, json
from cryptography import x509
from cryptography.hazmat.primitives import serialization

def fetch_and_inject():
    # Get short-lived token from CI environment
    vault_token = os.environ['VAULT_TOKEN']
    
    # Fetch Wi-Fi credentials (expire after build)
    wifi_creds = json.loads(
        requests.get('https://vault.internal/v1/secret/data/prod/wifi',
                     headers={'X-Vault-Token': vault_token}).text
    )['data']['data']
    
    # Fetch device certificate chain
    cert_pem = requests.get('https://vault.internal/v1/pki/issue/device-2026',
                            headers={'X-Vault-Token': vault_token}).text
    
    # Inject into firmware partition image
    with open('firmware.bin', 'r+b') as fw:
        fw.seek(0x10000)  # Provisioning partition offset
        fw.write(wifi_creds['ssid'].encode().ljust(32, b'\x00'))
        fw.write(wifi_creds['password'].encode().ljust(64, b'\x00'))
        fw.write(cert_pem.encode())
    
    # Revoke token
    requests.post('https://vault.internal/v1/auth/token/revoke-self',
                  headers={'X-Vault-Token': vault_token})

if __name__ == '__main__':
    fetch_and_inject()
```

## Common Pitfalls & Gotchas

1. **Secret leakage through build artifacts**: The most common mistake is forgetting to strip secrets from intermediate build artifacts (object files, debug symbols). I once saw a team whose `.elf` file contained the full provisioning certificate in a debug string. Always run `strings firmware.elf | grep -i 'BEGIN CERTIFICATE\|password\|secret'` in CI and fail the build if secrets appear.

2. **Long-lived Vault tokens in CI**: Some teams generate a Vault token manually and store it as a GitHub secret. This defeats the purpose — if that token leaks, an attacker has indefinite access. Always use OIDC/JWT authentication with short TTLs (5-10 minutes). If your CI doesn't support OIDC, use AWS Secrets Manager with IAM roles instead.

3. **HSM state across CI runs**: SoftHSM tokens are ephemeral in containers. If you restart the runner, the token is gone. Either re-initialize the HSM token each build (slow) or use a persistent Docker volume. For production, use a network HSM (like AWS CloudHSM) that maintains state.

## Try It Yourself

1. **Set up Vault OIDC with GitHub Actions**: Create a Vault policy that allows reading a test secret only from your repo's `main` branch. Configure GitHub's OIDC provider and verify that a PR from a fork cannot access the secret.

2. **Implement a CI check for secret leakage**: Add a step to your firmware build that runs `strings` and `grep` for common secret patterns (e.g., `PRIVATE KEY`, `password`). Fail the build if any are found in the output binary.

3. **Build a provisioning injection script**: Write a Python script that reads Wi-Fi credentials from an environment variable, encrypts them with a device-specific public key (stored in the firmware), and writes them to a provisioning partition. Run it in CI with a mock Vault server.

## Next Up

Tomorrow: **Cross-Team Pipelines: Coordinating Firmware, Cloud & Mobile Releases** — how to orchestrate a release that updates the firmware, the cloud backend, and the mobile app simultaneously without breaking device compatibility.
