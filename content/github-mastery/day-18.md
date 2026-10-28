---
title: "Day 18: GITHUB_TOKEN Permissions & OIDC: Least Privilege in CI"
date: 2026-10-28
tags: ["til", "github-mastery", "github-token", "oidc"]
---

## What I Explored Today

Today I dug into the two mechanisms that decide how much power a workflow actually has: the `GITHUB_TOKEN` permission model and OpenID Connect (OIDC) federation. The default `GITHUB_TOKEN` in a GitHub Actions workflow is not a single all-or-nothing credential — it's a scoped token whose permissions are set at the workflow or job level, and by default it's read-only for most scopes on newer repositories. OIDC is the other half of the story: instead of storing long-lived cloud credentials as secrets, the workflow requests a short-lived signed JWT from GitHub's OIDC provider, and the cloud provider (AWS, GCP, Azure) exchanges it for temporary credentials after verifying the token's claims. Together they let you build CI that can deploy to production without a single static secret sitting in your repository settings.

## The Core Concept

The mental model that finally clicked for me: **a workflow is untrusted code, and every credential it holds is a potential exfiltration target.** A pull request from a fork can run arbitrary code in your CI. If that code has a token with `contents: write`, an attacker can push to your repo. If it has cloud credentials, they can pivot into your infrastructure. Least privilege isn't a nice-to-have here — it's the difference between a compromised PR and a compromised organization.

`GITHUB_TOKEN` is an installation token minted per-job, scoped to the repository, and expired when the job finishes. Its permissions are controlled by a `permissions:` block. The critical detail: **if you specify any `permissions:` key at the workflow level, all unspecified scopes default to `none`.** That's the opposite of the legacy behavior where the token had broad write access. So the safest pattern is to declare `permissions: {}` (or `permissions: read-all`) at the top of the workflow and grant specific scopes only on the jobs that need them.

OIDC flips the secret-management problem on its head. Instead of "here's a password, keep it safe," it's "prove who you are, and I'll give you a 15-minute credential." The workflow calls `ACTIONS_ID_TOKEN_REQUEST_URL` with `ACTIONS_ID_TOKEN_REQUEST_TOKEN` (both injected by the runner) to get a JWT. That JWT contains claims like `sub` (subject, e.g. `repo:org/repo:ref:refs/heads/main`), `repository`, `ref`, and `environment`. The cloud provider's trust policy checks those claims and, if they match, issues temporary credentials. No secret ever leaves GitHub.

The `sub` claim is the security boundary. If your trust policy says `repo:org/repo:*`, any branch — including a PR branch — can assume the role. If it says `repo:org/repo:ref:refs/heads/main`, only pushes to `main` can. This is where most OIDC misconfigurations live.

## Key Commands / Configuration / Code

**1. Lock down `GITHUB_TOKEN` at the workflow level, then grant per-job:**

```yaml
name: CI
on: [push, pull_request]

# Default to no permissions; jobs opt in explicitly.
permissions: {}

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read        # checkout needs this
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test

  release:
    runs-on: ubuntu-latest
    # Only this job can write to the repo.
    permissions:
      contents: write
      packages: write
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/release.sh
```

**2. Verify what the token can actually do (debugging):**

```bash
# Inside a workflow step, inspect the token's scopes.
# GITHUB_TOKEN is exposed as an env var; use the REST API to check.
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/installation/repositories \
  | jq '.repositories[].full_name'
```

**3. OIDC: request the JWT and exchange it for AWS credentials:**

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write       # REQUIRED for OIDC — no other scope grants this
      contents: read
    steps:
      - uses: actions/checkout@v4

      # The runner injects these two env vars automatically when id-token: write is set.
      - name: Get OIDC token
        id: oidc
        run: |
          TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" | jq -r '.value')
          echo "::add-mask::$TOKEN"
          echo "token=$TOKEN" >> "$GITHUB_OUTPUT"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-deploy
          aws-region: us-east-1
          web-identity-token: ${{ steps.oidc.outputs.token }}
```

**4. The AWS trust policy that makes it safe — pin the `sub` claim:**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:my-org/my-repo:ref:refs/heads/main"
      }
    }
  }]
}
```

## Common Pitfalls & Gotchas

**1. `permissions: {}` silently breaks checkout.** `actions/checkout` needs `contents: read`. If you set an empty permissions block and forget to grant it on the job, checkout fails with a confusing 403. Always pair `permissions: {}` at the top with explicit `contents: read` on jobs that check out code.

**2. OIDC `sub` claim wildcards are a footgun.** A trust policy with `repo:my-org/my-repo:*` matches *any* ref, including `refs/pull/123/merge` from a fork PR. If your deploy job runs on `pull_request`, an attacker can assume your production role. Pin to `ref:refs/heads/main` or use `environment:` claims for gated deploys.

**3. `id-token: write` is not implied by anything.** It's a distinct scope. Without it, `ACTIONS_ID_TOKEN_REQUEST_URL` is unset and your curl returns an empty string — the failure looks like a network error, not a permissions error. Add it explicitly on the job that needs OIDC.

## Try It Yourself

1. **Audit an existing workflow.** Add `permissions: {}` at the top of a workflow in one of your repos, run it, and fix the 403s one job at a time by granting the minimum scope. Note which jobs actually needed `contents: write` — I bet fewer than you think.

2. **Decode an OIDC token.** In a workflow with `id-token: write`, fetch the JWT (as in the example above) and paste it into `jwt.io`. Inspect the `sub`, `ref`, and `repository` claims. Then write a trust policy that pins `sub` to your default branch and confirm a PR-triggered run is rejected.

3. **Break it on purpose.** Change a job's `permissions` to `contents: write` and try to push from a `pull_request` event triggered by a fork. Observe the failure — that's the boundary doing its job.

## Next Up

Tomorrow: **Releases, Tags, Changelogs & GitHub Packages (GHCR)** — how to cut a release from a tag, auto-generate changelogs with `gh release create --generate-notes`, and push container images to the GitHub Container Registry using the very `packages: write` scope we just learned to scope down.
