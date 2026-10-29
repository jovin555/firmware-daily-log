---
title: "Day 19: Releases, Tags, Changelogs & GitHub Packages (GHCR)"
date: 2026-10-29
tags: ["til", "github-mastery", "releases", "ghcr"]
---

# Day 19: Releases, Tags, Changelogs & GitHub Packages (GHCR)

## What I Explored Today

Today I closed the loop between "code that works" and "artifact that ships." Tags, Releases, and GitHub Packages are often treated as three unrelated features, but they're really one pipeline: a tag marks a commit, a Release attaches metadata and binaries to that tag, and GHCR (GitHub Container Registry) gives you a place to publish the actual build output. I spent the day wiring these together — annotated tags with signed commits, auto-generated release notes, a `CHANGELOG.md` that follows Keep a Changelog, and a workflow that pushes a multi-arch image to `ghcr.io` on tag push. The interesting part wasn't any single command; it was understanding the *contract* each layer enforces so the next one can consume it reliably.

## The Core Concept

The reason these features exist as separate layers is **immutability and provenance**. A lightweight tag is just a pointer — cheap, mutable, and easy to move with `git tag -f`. An **annotated tag** is a real Git object: it has an author, a date, a message, and can be GPG-signed. That's what a Release should hang off of, because a Release is a *promise* that "this exact tree, at this exact commit, is version 1.4.0." If you tag a lightweight tag and later force-move it, you've silently broken every downstream consumer that pinned to it.

Releases add two things tags can't: **human-readable notes** and **binary assets**. GitHub can auto-generate notes from merged PRs and commit history, but the real value is that release assets are served from a stable URL (`https://github.com/OWNER/REPO/releases/download/v1.4.0/artifact.tar.gz`) that you can `curl` in CI, in Dockerfiles, and in install scripts. That URL only works because the tag is immutable.

GHCR is the same idea applied to OCI artifacts. When you `docker push ghcr.io/owner/repo:v1.4.0`, the registry stores a manifest keyed by digest. Tags like `v1.4.0` and `latest` are just pointers into that content-addressed store. The reason to publish to GHCR instead of Docker Hub is **permissions**: GHCR inherits your repo's `GITHUB_TOKEN` scopes, so a workflow can push without any external secrets, and package visibility is tied to repository access. That's the whole trick — no PATs to rotate, no cross-account trust.

## Key Commands / Configuration / Code

**Creating a proper annotated, signed tag:**

```bash
# -a = annotated, -s = GPG-signed, -m = message (required for annotated)
git tag -s v1.4.0 -m "Release 1.4.0: streaming parser, 40% faster cold start"

# Verify the signature before pushing
git tag -v v1.4.0

# Push ONLY this tag (not --tags, which pushes everything)
git push origin v1.4.0
```

**Auto-generating release notes via the CLI:**

```bash
# Requires `gh` authenticated. --generate-notes uses GitHub's PR/commit grouping.
gh release create v1.4.0 \
  --title "v1.4.0" \
  --notes-file CHANGELOG.md \
  --generate-notes \
  ./dist/app-linux-amd64.tar.gz \
  ./dist/app-darwin-arm64.tar.gz
```

**Workflow that builds, tags, and pushes to GHCR on tag push:**

```yaml
name: release
on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: write   # needed to create the Release
  packages: write   # needed to push to GHCR

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

**Pulling from GHCR in a downstream Dockerfile:**

```dockerfile
# Public packages need no auth; private ones require a PAT with read:packages
FROM ghcr.io/owner/app:1.4.0
```

## Common Pitfalls & Gotchas

**1. `GITHUB_TOKEN` can't trigger other workflows.** If your release workflow pushes a tag or creates a Release, downstream workflows listening on `release: [published]` won't fire — GitHub suppresses events caused by the default token to prevent recursion. Use a fine-grained PAT or a GitHub App token if you need chaining.

**2. Package visibility is separate from repo visibility.** A public repo can still have a *private* GHCR package if the first push happened before you flipped repo visibility, or if you set it explicitly. Check `Settings → Packages` on the repo, not just the repo itself. Anonymous `docker pull` will 401 with a confusing "denied" message.

**3. `docker/metadata-action`'s `latest` tag is not automatic.** The `type=raw,value=latest` line above is doing real work — without it, only semver tags get pushed. Also note that `type=semver` requires the tag to match `v*.*.*` exactly; `v1.4` or `1.4.0` will silently produce no tags and your build will push nothing.

## Try It Yourself

1. **Sign and verify a tag.** Generate a GPG key (`gpg --full-generate-key`), add it to GitHub under Settings → SSH and GPG keys, then create a signed tag on any commit and run `git tag -v <tag>` locally. Confirm GitHub shows the "Verified" badge on the tag page.

2. **Publish a trivial image to GHCR.** Create a two-line Dockerfile (`FROM alpine` + `CMD ["echo","hi"]`), push it to `ghcr.io/<you>/test:0.1.0` using the workflow above, then `docker pull` it from a *different* machine without logging in — observe the 401 and then fix package visibility.

3. **Break a release on purpose.** Create a Release, then `git tag -f v1.4.0 <other-commit>` and `git push --force origin v1.4.0`. Watch what happens to the Release page and to the asset download URLs. This is the failure mode annotated tags exist to prevent.

## Next Up

Tomorrow: **GitHub Pages: Deploying Static Sites from Actions** — moving from shipping *artifacts* to shipping *sites*, with `actions/deploy-pages`, custom domains, and the environment protection rules that keep a bad deploy from going live.
