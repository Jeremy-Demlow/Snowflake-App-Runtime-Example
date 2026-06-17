## Context (now grounded in a proven internal recipe)

The explorer shells out to the `cortex` CLI **binary**, which is curl-installed (not pip). So the managed SiS `streamlit` runtime can't host it; the path is a **custom image on SPCS**. The internal guide `Cortex_Code_CLI_SPCS_Snowsight_Only_Guide.docx` (#feat-coco-cli) proves this works and gives the recipe:

- **Kaniko build inside Snowflake — no local Docker.** Upload `Dockerfile` + `build_spec.yaml` to a stage; a Kaniko service builds + pushes the image to an image repository.
- **Proven Dockerfile**: Debian base; `apt` ca-certificates/jq; `RUN curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh -o /tmp/install.sh && (sh /tmp/install.sh || true)`; `ENV PATH="/home/cortexuser/.local/bin:${PATH}"`; `mkdir -p ~/.snowflake`. Guide's `CMD` is `ttyd`; ours is `streamlit run`.
- **EAI required for Cortex Agent API calls** (deploy-to-spcs skill feedback). Auth nuance: OAuth/SPCS token vs our proven key-pair `connections.toml`.

Auth choice: **mount the private key as a Snowflake SECRET and have the entrypoint write `connections.toml`** — identical to how we run the CLI headless locally all session, lowest-risk. (OAuth/service-token is the guide's alternative; fall back to it only if key-pair-in-SPCS is disallowed.)

## Phase 0 — Minimal CLI smoke in SPCS (the real gate)
1. SQL setup (from guide): `CREATE DATABASE/SCHEMA`, `CREATE IMAGE REPOSITORY`, `CREATE STAGE ... DIRECTORY=(ENABLE=TRUE)`; `SHOW IMAGE REPOSITORIES` for the repo URL.
2. Author a **minimal** `Dockerfile` (base + curl-install cortex CLI only) + `build_spec.yaml` (Kaniko). Upload both to the build stage; run the Kaniko build job; confirm the image lands in the repo.
3. Create a key-pair `SECRET` + an `EXTERNAL ACCESS INTEGRATION` for the account/Cortex host(s) + a compute pool.
4. Run the image as a short-lived service/job (interactive `ttyd` or a one-shot command) and verify **inside SPCS**: `cortex --version`; `connections.toml` written from the secret; one `cocosdkagent.Chat` explorer turn (multiple `sql_execute`) against the data DB succeeds.
   **GATE:** green → proceed. Red (auth/egress/sandbox) → report; fall back to SiS-native REST+SQL example.

## Phase 1 — Full Streamlit app image
5. Extend the Dockerfile: `pip install streamlit cortex_code_agent_sdk` + `cocosdkagent` (vendored wheel) + copy `streamlit/` + `cortex-code-agent/`; entrypoint writes `connections.toml` then `streamlit run streamlit/app.py --server.port 8080`; `EXPOSE 8080`.
6. Rebuild via Kaniko; push.
7. Service spec: image, `secrets:` mount (key), `env` (account/host), public `endpoint` on 8080, EAI, compute pool. `CREATE SERVICE`.
8. `SHOW ENDPOINTS` → stable `https://<hash>-<org>-<acct>.snowflakecomputing.app`. Open it; confirm dashboard + Explore-only + Agent-aware all work; debug via `SYSTEM$GET_SERVICE_LOGS`.

## Phase 2 — Integration / productionize
9. Home + data DB: land in `/Users/jdemlow/00_Code/github/Snowflake-App-Runtime-Example` as a **custom-container app** (document it uses SPCS, not the repo's SiS `streamlit` CI). Decide `AM_SKI_RESORT` vs re-point to `SKI_RESORT_DEMO` + confirm the `RESORT_EXECUTIVE` agent FQN there.
10. Vendor `cocosdkagent` (wheel) so the image build is self-contained; document the publish-and-remove migration.
11. Iterate loop: edit -> Kaniko rebuild -> `ALTER SERVICE ... FROM SPECIFICATION`; confirm endpoint URL stays stable.

## Verification
- Phase 0 gate: `cortex --version` + one explorer turn succeed inside an SPCS container against the target account.
- Phase 1: endpoint serves the app; both prompt modes work; logs clean of auth/egress errors.
- Phase 2: fresh Kaniko build from the integrated repo (no sibling `cocoagent` dep) reproduces a working image + endpoint.

## Open items
- Exact EAI host list the CLI/agent calls need (capture from Phase 0 logs / guide).
- Confirm key-pair-secret auth is permitted in SPCS, else switch to OAuth/service-token.
- Whether to build via Kaniko (no local Docker, matches guide) or local `docker build` if Docker is available (faster inner loop) — default Kaniko.

## Critical files
- `Dockerfile` (new) - base + curl-install cortex CLI + deps + app; the whole feasibility hinges on it
- `build_spec.yaml` (new) - Kaniko in-Snowflake build (no local Docker)
- service spec YAML (new) - SECRET mount + EAI + endpoint
- [streamlit/bridge.py](streamlit/bridge.py) - spawns the cortex CLI; needs connections.toml the entrypoint creates
- [cortex-code-agent/_jwt_auth.py](cortex-code-agent/_jwt_auth.py) - key-pair auth the mounted SECRET must satisfy
