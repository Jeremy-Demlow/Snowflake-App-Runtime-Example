# Ski Resort BI Explorer — custom SPCS image
#
# Why a custom image (not the SiS `type: streamlit` runtime): the app's
# "free-range explorer" uses the Cortex Code SDK, which shells out to the
# `cortex` CLI *binary*. That binary is curl-installed (not pip-installable),
# so it cannot live in the managed SiS runtime. Here we bake it into our own
# image and deploy as a Snowpark Container Services (SPCS) service.
#
# Build with --platform linux/amd64 (SPCS only accepts amd64), or build
# in-Snowflake via Kaniko (see build_spec.yaml + setup.sql).

FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git jq \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# 1) Install the Cortex Code CLI binary (the SDK explorer shells out to it).
#    Same installer used locally; lands in ~/.local/bin.
RUN curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh -o /tmp/install.sh \
    && (sh /tmp/install.sh || true) && rm -f /tmp/install.sh
ENV PATH="/home/appuser/.local/bin:${PATH}"
RUN mkdir -p /home/appuser/.snowflake/keys

# 2) App code + dependencies. cortex-code-agent/ must sit beside streamlit/
#    (streamlit/_bootstrap.py imports it as cortex_code_agent via the sibling dir).
COPY --chown=appuser:appuser requirements.txt ./
COPY --chown=appuser:appuser vendor/ ./vendor/
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user ./vendor/cocosdkagent-0.1.0-py3-none-any.whl
COPY --chown=appuser:appuser streamlit/ ./streamlit/
COPY --chown=appuser:appuser cortex-code-agent/ ./cortex-code-agent/
COPY --chown=appuser:appuser entrypoint.sh ./

EXPOSE 8080
ENTRYPOINT ["bash", "entrypoint.sh"]
