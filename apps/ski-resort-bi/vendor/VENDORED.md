# Vendored dependency: cocosdkagent

`cocosdkagent-0.1.0-py3-none-any.whl` is vendored here so the container image
builds **self-contained** (no dependency on a sibling checkout) for an early
release.

- **Source:** https://github.com/Jeremy-Demlow/cocoagent (package `cocosdkagent`)
- **Version:** 0.1.0
- **Provenance:** built from the local working tree (repo not yet committed at
  vendor time). nbdev project — source of truth is `nbs/*.ipynb`.

## Do not hand-edit
This wheel is a build artifact. To update it: in the `cocoagent` repo run
`nbdev_export` then `python -m pip wheel . --no-deps -w dist/`, and copy the new
`.whl` here.

## Migration (publish, then remove)
When `cocosdkagent` is published to an index, delete this wheel and replace the
Dockerfile/requirements line with a normal pin, e.g. `cocosdkagent>=0.1.0`.
That is the only change required — no app code touches the import path.
