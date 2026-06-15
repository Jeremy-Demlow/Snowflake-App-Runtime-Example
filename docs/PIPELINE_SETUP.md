# Pipeline Setup — GitHub Actions

How to wire up CI so the workflows in `.github/workflows/` can deploy to your
Snowflake account. One-time setup by a repo admin.

## Credentials: secrets vs variables

Credentials are split between **repo secrets** (sensitive, masked in logs) and
**repo variables** (non-sensitive, shown unmasked so Snowsight URLs and role
names stay readable in CI logs).

### Repo secrets (sensitive)

Settings -> Secrets and variables -> Actions -> **Secrets**:

| Secret | Description |
|--------|-------------|
| `SNOWFLAKE_ACCOUNT` | Account identifier (e.g. `abc12345`) |
| `SNOWFLAKE_USER` | Service user for CI |
| `SNOWFLAKE_PRIVATE_KEY_RAW` | Full PEM private key contents (key-pair auth) |
| `PRIVATE_KEY_PASSPHRASE` | Optional — only if the key has a passphrase |

### Repo variables (non-sensitive)

Settings -> Secrets and variables -> Actions -> **Variables**:

| Variable | Value | Used by |
|----------|-------|---------|
| `SNOWFLAKE_ROLE` | `SKI_DEVELOPER` (or an admin role) | app deploys |
| `SNOWFLAKE_WAREHOUSE` | `SKI_DEMO_WH` | app deploys |
| `SNOWFLAKE_DATABASE` | `SKI_RESORT_DEMO` | app deploys |

> The DCM workflow (`dcm-deploy.yml`) connects as `ACCOUNTADMIN` with `COMPUTE_WH`
> (set in the workflow), because it creates account-level roles + the warehouse.
> App deploys use the lower-privilege `SNOWFLAKE_ROLE` variable.

## GitHub Environments

Settings -> **Environments**:

| Environment | Used by | Protection |
|-------------|---------|------------|
| `dev` | `deploy-dev.yml`, `cleanup-branch.yml`, DCM plan | none |
| `production` | `deploy-prod.yml`, DCM deploy | **Required reviewer** |

The `production` environment is the prod lockdown — deploys pause until a
reviewer approves. Without it, `deploy-prod.yml` and the DCM deploy job fail with
a "deployment protection rule" error.

## Quick setup via gh CLI

These commands do everything above. Requires the [gh CLI](https://cli.github.com)
authenticated as a repo admin (`gh auth login`).

```bash
REPO="Jeremy-Demlow/Snowflake-App-Runtime-Example"
KEY="$HOME/.snowflake/keys/snowflake_tf_key.p8"
OWNER_ID=$(gh api "users/$(echo "$REPO" | cut -d/ -f1)" --jq '.id')

# 1) Environments: dev (no protection), production (required reviewer = repo owner)
echo '{}' | gh api "repos/$REPO/environments/dev" --method PUT --input -
echo "{\"reviewers\":[{\"type\":\"User\",\"id\":$OWNER_ID}]}" \
  | gh api "repos/$REPO/environments/production" --method PUT --input -

# 2) Repo secrets
echo "trb65519" | gh secret set SNOWFLAKE_ACCOUNT -R "$REPO"
echo "JDEMLOW"  | gh secret set SNOWFLAKE_USER    -R "$REPO"
gh secret set SNOWFLAKE_PRIVATE_KEY_RAW -R "$REPO" < "$KEY"
# gh secret set PRIVATE_KEY_PASSPHRASE -R "$REPO"   # only if your key has one

# 3) Repo variables
gh variable set SNOWFLAKE_ROLE      -R "$REPO" --body "SKI_DEVELOPER"
gh variable set SNOWFLAKE_WAREHOUSE -R "$REPO" --body "SKI_DEMO_WH"
gh variable set SNOWFLAKE_DATABASE  -R "$REPO" --body "SKI_RESORT_DEMO"
```

Verify:

```bash
gh secret list   -R "$REPO"
gh variable list -R "$REPO"
gh api repos/$REPO/environments --jq '.environments[].name'
```

## Generate a key pair (if you need one)

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out snowflake_tf_key.p8 -nocrypt
openssl rsa -in snowflake_tf_key.p8 -pubout -out snowflake_tf_key.pub
# In Snowflake (as a user who can alter the CI user):
#   ALTER USER <CI_USER> SET RSA_PUBLIC_KEY='<contents of .pub without headers>';
```

## Workflow overview

| Workflow | Trigger | Environment | What it does |
|----------|---------|-------------|--------------|
| `deploy-dev.yml` | push to non-main / PR | `dev` | discover `apps/*` -> deploy each to `APPS_DEV` (`_<branch>` suffix) |
| `deploy-prod.yml` | push to `main` | `production` | discover `apps/*` -> deploy each to `APPS` (approval gated) |
| `cleanup-branch.yml` | PR closed | `dev` | tear down that branch's `APPS_DEV` apps |
| `dcm-deploy.yml` | `governance/**` changed | `dev` (plan) / `production` (deploy) | plan on PR, deploy `MAIN` on push to main |

## After DCM deploys: post-deployment grants (one time)

`dcm-deploy.yml` applies the declarative governance. FUTURE grants, semantic-view
grants, and account-level SPCS privileges live in a separate script (DCM's
declarative grant set doesn't cover them). Run once as `ACCOUNTADMIN`:

```bash
snow sql -f governance/post_deployment_grants.sql -D "DB=SKI_RESORT_DEMO" -c <connection>
```

## Common failures

| Error | Cause | Fix |
|-------|-------|-----|
| `Failed to connect ... 250001` | Bad account/user/key | Check `SNOWFLAKE_ACCOUNT`/`SNOWFLAKE_USER` secrets |
| `Private key is not in PKCS8 format` | Wrong key format | Regenerate with `openssl pkcs8 -topk8 ... -nocrypt` |
| `Environment 'production' not found` | Env not created | Run the gh environment command above |
| `SQL access control error` on DCM | Role lacks privilege | DCM job must run as `ACCOUNTADMIN` |
| `SNOWFLAKE_ROLE` empty in app deploy | Variable not set | Set the 3 repo variables above |
| App deploy `does not exist or not authorized` | Role missing app-schema grants | Re-run `post_deployment_grants.sql` |
