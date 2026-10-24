---
title: "Day 14: Secrets, Variables, Environments & Deployment Protection Rules"
date: 2026-10-24
tags: ["til", "github-mastery", "secrets", "environments"]
---

# Day 14: Secrets, Variables & Environments & Deployment Protection Rules

## What I Explored Today

Today I dug into the configuration layer that separates a toy workflow from a production-grade one: how GitHub Actions stores and scopes secrets and variables, and how environments act as a gatekeeper for deployments. I'd been treating `secrets.MY_TOKEN` as a flat global namespace, which works until you have a staging and production deploy that need different credentials and different approval requirements. I spent the afternoon wiring up two environments, moving secrets to environment scope, and adding a required reviewer plus a branch restriction so a `main` push can't silently ship to prod. The mental model that finally clicked: secrets and variables are *scoped resources*, and environments are the policy boundary that decides who can consume them and when.

## The Core Concept

The "why" here is blast radius. If every secret lives at the repository level, then any workflow on any branch can read your production database password. That's fine for a solo repo and terrifying for a team. GitHub gives you three concentric scopes — **repository**, **environment**, and **organization** — and the resolution order matters: when a job references `secrets.DB_PASSWORD`, GitHub looks in the environment first (if the job declares one), then falls back to the repository, then the org. That precedence is the whole trick. You put a safe default at the repo level and the real production credential at the `production` environment level, and the same workflow file deploys correctly to both without branching logic.

Environments add a second dimension beyond scoping: **protection rules**. An environment can require human reviewers, restrict which branches may deploy to it, and set a wait timer. When a job targets a protected environment, the run *pauses* — it doesn't fail — and waits for approval. This is the difference between "we have a deploy workflow" and "we have a deploy workflow nobody can abuse." Variables (`vars` context) are the non-secret sibling: same scoping, but stored in plaintext and visible in logs, so they're for things like `AWS_REGION` or `API_BASE_URL`, never credentials.

## Key Commands / Configuration / Code

Creating environments and their protection rules is mostly a UI/API task, but you can script it with `gh`:

```bash
# Create an environment (the API creates it on first reference, but be explicit)
gh api --method PUT repos/OWNER/REPO/environments/production

# Add a required reviewer (user id) to the production environment
gh api --method PUT repos/OWNER/REPO/environments/production \
  -f 'reviewers[][type]=User' \
  -F 'reviewers[][id]=1234567'

# Restrict deployments to the main branch only
gh api --method PUT repos/OWNER/REPO/environments/production \
  -f 'deployment_branch_policy[protected_branches]=false' \
  -f 'deployment_branch_policy[custom_branch_policies]=true'
```

Setting a secret at environment scope (note the `--env` flag — this is the part people miss):

```bash
# Repository-scoped secret (visible to all workflows)
gh secret set DB_PASSWORD --body "staging-pw"

# Environment-scoped secret (only jobs targeting 'production' see it)
gh secret set DB_PASSWORD --env production --body "prod-pw"

# Non-secret variable, same scoping rules
gh variable set AWS_REGION --env production --body "us-east-1"
```

The workflow side — this is where the precedence becomes concrete:

```yaml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging          # resolves secrets from 'staging' env
    steps:
      - run: ./deploy.sh
        env:
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}   # staging value
          REGION: ${{ vars.AWS_REGION }}             # staging value

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment:
      name: production            # triggers protection rules
      url: https://app.example.com
    steps:
      - run: ./deploy.sh
        env:
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}   # production value
          REGION: ${{ vars.AWS_REGION }}             # production value
```

Same `${{ secrets.DB_PASSWORD }}` expression in both jobs, two different values, and the production job blocks on reviewer approval before it runs. The `url:` field also surfaces a clickable deployment link on the PR and repo home.

## Common Pitfalls & Gotchas

**Secrets aren't available in `if:` conditions at the job level.** You cannot write `if: secrets.DEPLOY_KEY != ''` — the `secrets` context isn't evaluated in job-level `if` expressions, and the secret will be empty there. If you need conditional logic based on secret presence, check it inside a step (`if: env.MY_SECRET != ''` after mapping it into `env`), or gate on a variable instead.

**Environment secrets only resolve when the job declares `environment:`.** A job that references `${{ secrets.PROD_KEY }}` but has no `environment:` block will *not* see the environment-scoped secret — it falls back to repo scope and gets nothing (empty string, not an error). This silently produces empty credentials and confusing auth failures. Always pair environment-scoped secrets with an `environment:` declaration on the consuming job.

**Forked PRs don't get secrets at all.** For `pull_request` events from forks, secrets are withheld and `GITHUB_TOKEN` is read-only. If your workflow needs secrets on PRs, use `pull_request_target` *very* carefully (it runs in the base repo context with secrets — a classic supply-chain footgun) or split into a secret-free test job and a privileged job that runs post-merge.

## Try It Yourself

1. **Build the two-environment deploy.** Create `staging` and `production` environments in a test repo. Set `DB_PASSWORD` at repo scope to a dummy value, then override it at `production` scope with a different dummy. Add a workflow with two jobs as above and confirm each job prints a different value (echo a hash, not the secret).

2. **Add a required reviewer.** Using the `gh api` commands above, attach yourself as a required reviewer to `production`. Push to `main` and watch the run pause at the production job — approve it from the Actions UI and confirm the deploy step proceeds.

3. **Lock down the branch.** Enable "custom branch policies" on `production` and restrict it to `main`. Then try triggering the production job from a feature branch (via `workflow_dispatch` on that branch) and confirm GitHub refuses to deploy.

## Next up

Tomorrow: **Reusable Workflows & Composite Actions** — how to stop copy-pasting that deploy job into every repo. We'll cover `workflow_call` inputs/secrets, the difference between reusable workflows and composite actions (and when each is the right tool), and the nesting limits that bite you at scale.
