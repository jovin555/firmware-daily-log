---
title: "Day 22: Code Scanning with CodeQL, Secret Scanning & Push Protection"
date: 2026-11-01
tags: ["til", "github-mastery", "codeql", "secret-scanning"]
---

## What I Explored Today

Today I dug into GitHub's three-layer security stack for repositories: CodeQL code scanning, secret scanning, and push protection. The first two are detection tools — CodeQL runs semantic analysis over your codebase to find injection flaws, path traversal, and other taint-tracking bugs, while secret scanning looks for credentials in commits and issues. Push protection is the enforcement layer: it blocks a push at the client-server boundary before a secret ever lands in history. What surprised me most is how much of this is now free for public repos and how little configuration is needed to get meaningful coverage. I spent the afternoon wiring up a CodeQL workflow, testing push protection with a fake token, and reading through the alert triage UI.

## The Core Concept

The reason these three features exist together is that they address different failure modes in the software supply chain.

**CodeQL** treats code as data. It compiles your source into a queryable database and runs queries written in QL that model taint flow — "does untrusted input from an HTTP request reach a SQL string concatenation without sanitization?" This catches real bugs that linters miss because it understands data flow across function boundaries and even across files. The default query suite (`security-extended` is the sweet spot) covers the OWASP Top 10 and CWE Top 25.

**Secret scanning** is pattern-matching at scale. GitHub maintains a registry of ~200 token formats (AWS keys, GitHub PATs, Stripe keys, Slack webhooks, etc.) and scans every push, every commit in history, and even issue/PR bodies. When it finds a match, it notifies the provider — many providers will auto-revoke the leaked credential. That auto-revocation is the killer feature: detection alone is useless if the key stays valid for hours.

**Push protection** flips the model from detect-after-the-fact to prevent-before-commit. When you `git push`, the server inspects the diff for known secret patterns and rejects the push with a specific error. You can bypass with a reason, but the bypass is logged. This matters because secret rotation is expensive and history rewriting (`git filter-repo`, BFG) is painful — preventing the leak is orders of magnitude cheaper than remediating it.

The mental model: CodeQL finds *logic* vulnerabilities, secret scanning finds *credential* leaks, push protection *enforces* the credential policy. Together they cover the two most common ways real breaches start.

## Key Commands / Configuration / Code

**Enable CodeQL via the default setup** (easiest path — no workflow file needed):

```bash
# Requires GitHub CLI authenticated with repo scope
gh api -X PATCH repos/OWNER/REPO/code-scanning/default-setup \
  -f state=configured \
  -f query_suite=security-extended \
  -f languages='["javascript-typescript","python"]'
```

**Or use an advanced workflow** (`.github/workflows/codeql.yml`) for custom build steps:

```yaml
name: "CodeQL"
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'   # weekly Monday 06:00 UTC — catches new queries

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write   # required to upload SARIF
      contents: read
      actions: read
    strategy:
      matrix:
        language: ['javascript-typescript', 'python']
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended
      # For compiled languages (Java, C/C++, Go, C#) you MUST build here:
      # - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{ matrix.language }}"
```

**Run CodeQL locally** (useful for iterating on queries before pushing):

```bash
# Install the CLI
gh extension install github/gh-codeql
gh codeql install-stub

# Create a database and run the default suite
gh codeql database create /tmp/codeql-db --language=javascript --source-root=.
gh codeql database analyze /tmp/codeql-db \
  codeql/javascript-queries:codeql-suites/javascript-security-extended.qls \
  --format=sarif-latest --output=results.sarif
```

**Enable secret scanning + push protection** (public repos get this free; private repos need GitHub Advanced Security):

```bash
# Secret scanning (alerting)
gh api -X PATCH repos/OWNER/REPO \
  -F security_and_analysis.secret_scanning.status=enabled

# Push protection (blocking)
gh api -X PATCH repos/OWNER/REPO \
  -F security_and_analysis.secret_scanning_push_protection.status=enabled
```

**Custom patterns** for internal token formats (e.g., `acme_live_[a-z0-9]{32}`):

```bash
gh api -X POST repos/OWNER/REPO/secret-scanning/custom-patterns \
  -f name="Acme live key" \
  -f pattern='acme_live_[a-z0-9]{32}' \
  -f secret_type="acme_live_key"
```

**Test push protection** with a known-bad string (GitHub's docs use this AWS example key):

```bash
echo 'aws_access_key_id = AKIAIOSFODNN7EXAMPLE' > leak.txt
git add leak.txt && git commit -m "test"
git push   # → rejected: "Push cannot contain secrets"
```

## Common Pitfalls & Gotchas

**1. CodeQL doesn't build compiled languages for you in default setup.** For Java, C/C++, C#, Go, and Swift, the analysis needs a working build. Default setup uses `autobuild`, which fails on anything non-standard (Bazel, custom Makefiles, monorepos with multiple build systems). If your first CodeQL run shows zero results on a Java repo, check the Actions log — it's probably a silent build failure. Switch to an advanced workflow and call `codeql-action/autobuild` explicitly, or replace it with your actual build commands.

**2. Push protection only blocks *known* patterns by default.** Custom internal token formats need a custom pattern configured at the org or repo level, and custom patterns are only enforced after they're published (which can take a few minutes). Also, push protection does not scan *existing* history — if a secret is already in `main`, enabling push protection won't retroactively flag it. You need to run a history scan separately (`gitleaks detect --source . --log-opts="--all"` is a good complement).

**3. CodeQL alerts on PRs are not blocking by default.** The workflow uploads SARIF and the check turns green even when it finds critical issues. To actually gate merges, you must add a branch protection rule requiring the "Code scanning results / CodeQL" check, and configure the repo's code scanning settings to fail on `error` severity. Otherwise you get a dashboard full of alerts nobody reads.

## Try It Yourself

1. **Enable default CodeQL setup on a repo you own** and trigger a run by pushing a trivial commit. Open the Security tab → Code scanning, and inspect at least one alert end-to-end: read the data-flow trace, click through to the source line, and dismiss it with a reason (won't fix / false positive / used in tests). The dismissal reason matters — it feeds into future query tuning.

2. **Test push protection deliberately.** Create a branch, add a file containing `ghp_` followed by 36 random alphanumeric characters (a fake GitHub PAT format), commit, and push. Confirm the push is rejected. Then try the bypass flow (`git push` again, follow the URL in the error) and verify the bypass appears in the Security → Secret scanning → Push protection bypass log.

3. **Write a custom secret pattern** for a fake internal token format like `myco_prod_[A-Za-z0-9]{40}`, then test it by committing a matching string. Confirm it's blocked. Bonus: add a `paths-ignore` to your CodeQL workflow to skip `node_modules/` and `vendor/` — scanning dependencies is wasted compute and generates noise.

## Next Up

Tomorrow: **Security Advisories, SECURITY.md, SBOMs & Artifact Attestations** — how to disclose vulnerabilities responsibly, publish a machine-readable inventory of your dependencies, and cryptographically prove that the binary you shipped was built from the commit you claim. This is where supply-chain security stops being about *finding* problems and starts being about *proving* provenance.
