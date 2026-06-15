# Onboarding — Your First Snowflake App

Welcome! This guide assumes you have **never installed a developer tool** before.
If you've used Claude or Cowork, you already know how to chat with an AI — that's
most of what you'll do here. Take it one step at a time.

> You will need: a Snowflake account login, and permission to create databases
> and roles (or a teammate who can run the first setup for you).

---

## Step 1 — Install Cortex Code Desktop

Cortex Code Desktop ("CoCo") is Snowflake's desktop app for building things with
an AI assistant. It is the only tool you need to install.

1. Go to the **[Cortex Code download page](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)**.
2. Download the version for your computer (macOS or Windows).
3. Open the downloaded file and follow the installer, just like any other app.
4. Launch **Cortex Code Desktop**.

That's it — no command line, no extra tools.

---

## Step 2 — Connect to Snowflake

The first time CoCo opens, it asks you to sign in to Snowflake.

1. Click **Add connection**.
2. Enter your **account identifier** (your teammate or Snowflake admin can give
   you this — it looks like `abc12345`).
3. Sign in with your username and password (or single sign-on, if your company
   uses it).
4. Pick a **role** and **warehouse** when asked. If you're unsure, choose the
   defaults your admin gave you.

You'll know it worked when CoCo shows your account in the top corner.

---

## Step 3 — Open this project

1. Download this project (your teammate will share a link, or use the green
   **Code → Download ZIP** button on GitHub) and unzip it somewhere easy to find,
   like your Desktop.
2. In Cortex Code Desktop, choose **File → Open Folder** and select the unzipped
   `Snowflake-App-Runtime-Example` folder.
3. You'll see the files listed on the left. You don't need to understand them all.

---

## Step 4 — The data is already set up

The dashboards read from a ready-to-go ski-resort dataset in the
`SKI_RESORT_DEMO` database. **There's nothing to load or prepare** — the data
is already there. The next step just gives you safe, role-based access to it.

---

## Step 5 — Create the roles and warehouse (one time)

This project manages its security setup as code, using **DCM** (Database Change
Management). It creates three roles so access is safe and tidy:

- **`SKI_READONLY`** — can only *read* the data (no changes).
- **`SKI_DEVELOPER`** — can read data *and* deploy apps.
- **`SKI_ADMIN`** — manages everything.

There's just **one** of each — environments are handled at the app layer, not by
duplicating roles per environment.

> **First time only:** open [`governance/manifest.yml`](../governance/manifest.yml)
> and change the `account_identifier` (two places) and `demo_user` values to your
> own account and Snowflake user. They're marked with `# <- change` comments.

Ask CoCo:

> Deploy the DCM governance project.

CoCo will show you a **plan** of exactly what it will create (roles, a warehouse,
the `APPS` and `APPS_DEV` schemas, and read-only grants), then ask you to confirm
before doing anything. Read it, then say **yes**.

---

## Step 6 — Ship an app

Now the fun part. Ask CoCo:

> Deploy the Next.js dashboard.

…and when it finishes, open the URL it gives you. You just deployed a web app
running on Snowflake!

Then try the other one to see the **same workflow** ship a different kind of app:

> Deploy the Streamlit dashboard.

Both show the same ski-resort KPIs. That's the whole point: **one loop, two apps.**

### Want to run an app on your laptop first?

You can preview either dashboard locally before deploying. Each app's README has
copy-paste steps: [`apps/nextjs-dashboard/README.md`](../apps/nextjs-dashboard/README.md)
and [`apps/streamlit-dashboard/README.md`](../apps/streamlit-dashboard/README.md).

---

## Step 7 — Make a change and deploy with GitHub (the team workflow)

When you're working with a team, you don't deploy from your laptop — you let
**GitHub Actions** do it automatically:

1. Create a **feature branch** (CoCo can do this: *"create a feature branch
   called my-change"*).
2. Make an edit, then ask CoCo to **commit and push** it.
3. GitHub automatically deploys your branch to its **own throwaway apps** in
   `APPS_DEV` (named after your branch) so you can test it in isolation.
4. When the team merges your change into **`main`**, GitHub waits for a
   **reviewer to approve** before deploying to **PROD** (the `APPS` schema).
   Production is locked down — nothing reaches it without a human saying yes.
5. When your PR closes, GitHub automatically **removes your branch's apps** so
   nothing piles up.

### One-time GitHub setup (an admin does this)

The CI uses the official [`snowflakedb/snowflake-cli-action`](https://github.com/snowflakedb/snowflake-cli-action)
and deploys **only the apps** — DCM governance is one-time setup (see below). An
admin adds these in the GitHub repo under
**Settings → Secrets and variables → Actions**:

| Secret | What it is |
|--------|------------|
| `SNOWFLAKE_ACCOUNT` | Your account identifier |
| `SNOWFLAKE_USER` | A service user for deployments |
| `SNOWFLAKE_ROLE` | Role to deploy as (needs CREATE on the app schemas + SPCS privileges, e.g. `SKI_DEVELOPER` or an admin role) |
| `SNOWFLAKE_PRIVATE_KEY_RAW` | The raw private key contents (key-pair auth) |
| `PRIVATE_KEY_PASSPHRASE` | (Optional) passphrase, if the key has one |

And under **Settings → Environments**, create an environment named **`production`**
with a **Required reviewer** — this is what makes PROD wait for approval.

### One-time governance setup (run once)

CI deploys only the apps, so the roles, warehouse, and grants must exist first.
Ask CoCo, or run:

```bash
# Create roles, warehouse, APPS + APPS_DEV schemas, grants
snow dcm deploy SKI_RESORT_DEMO.PUBLIC.SKI_GOVERNANCE --target MAIN
snow sql -f governance/post_deployment_grants.sql -D "DB=SKI_RESORT_DEMO"
```

That's it — one database, one governance deploy serves every environment.

---

## Stuck?

- Ask CoCo directly — describe what you see and what you expected.
- To start over completely, see [TEARDOWN.md](TEARDOWN.md) — it removes everything
  this project created so you can run it fresh.
