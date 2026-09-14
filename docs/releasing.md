# Releasing bevel-cad

Releases are fully automated from a git tag. No API tokens or secrets are stored in the
repository or in GitHub: PyPI publishing and artifact signing use GitHub's OIDC identity
("Trusted Publishing").

## One-time setup

Do these once, in order. Nothing here is a secret; there is nothing to paste into GitHub.

### 1. PyPI: add a *pending* trusted publisher

`bevel-cad` does not exist on PyPI yet, so the publisher must be registered as *pending*
(it becomes a normal publisher on the first upload, which also creates the project).

1. Log in at <https://pypi.org>, verify your email and enable 2FA if not already done.
2. Go to **Your account → Publishing** (<https://pypi.org/manage/account/publishing/>).
3. Under **Add a new pending publisher → GitHub**, enter exactly:

   | Field | Value |
   |---|---|
   | PyPI project name | `bevel-cad` |
   | Owner | `jimcortez` |
   | Repository name | `bevel-cad` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   The environment name must match; the workflow declares `environment: pypi`.

### 2. GitHub: create the `pypi` environment

1. Repo **Settings → Environments → New environment**, name it `pypi`.
2. Under **Deployment branches and tags** choose **Selected branches and tags** and add a
   tag rule `v*`. This stops any non-tag workflow from ever obtaining the publishing identity.
3. Optional: add yourself as a **Required reviewer** for a manual approval gate before each
   PyPI upload. The workflow will pause at the `publish` job until approved.

### 3. GitHub: Actions and security settings

- **Settings → Actions → General → Workflow permissions** can stay at *Read repository contents
  and packages permissions*. Each job escalates only what it needs (`contents: write`,
  `id-token: write`, `attestations: write` on the publish job).
- **Settings → Code security**: enable *Dependabot alerts* and *Dependabot security updates*.
  Do **not** enable CodeQL *Default setup*; the repo runs CodeQL through
  `.github/workflows/codeql.yml` (advanced setup) and the two conflict.

### 4. Renovate

Install the Mend Renovate GitHub App on the `jimcortez/bevel-cad` repository from
<https://github.com/apps/renovate>. Configuration lives in `.github/renovate.json5`
(weekend schedule, branch automerge, lock-file maintenance). Dependabot handles GitHub Actions.

### 5. Local `gh` CLI

`gh auth login -h github.com` on the machine you release from, so you can watch runs
(`gh run watch`) and verify attestations (`gh attestation verify`).

## Cutting a release

1. Make sure `main` is green in CI and `CHANGELOG.md` has the version's entry with a date.
2. Tag the commit on `main` and push the tag:

   ```bash
   git switch main && git pull
   git tag -a v0.1.0 -m "v0.1.0"
   git push origin v0.1.0
   ```

3. `release.yml` then:
   - checks the tag is a valid PEP 440 version and is reachable from `main`;
   - re-runs the full build + test matrix + clean-install smoke test on the tagged commit;
   - signs a build-provenance attestation for the wheel and sdist;
   - publishes to PyPI with PEP 740 attestations;
   - creates a GitHub Release with auto-generated notes and attaches the wheel and sdist.

The package version comes from the tag (hatch-vcs). `v0.1.0` → `bevel-cad 0.1.0`. Untagged
builds are `0.1.1.devN`. There is no version string to bump in the tree.

## Verifying a release

```bash
# Provenance attestation stored on GitHub
gh attestation verify bevel_cad-0.1.0-py3-none-any.whl --owner jimcortez

# PyPI attestation and a clean install
uv venv /tmp/bevel-check && VIRTUAL_ENV=/tmp/bevel-check uv pip install bevel-cad==0.1.0
/tmp/bevel-check/bin/bevel --version
```

The PyPI project page shows "Verified details" with the publishing workflow and commit.

## If a release fails

- `check-tag` fails: the tag is not on `main` or is not PEP 440. Delete and re-tag.
- `build` fails: fix on `main`, then move the tag (`git tag -f`, `git push -f origin v0.1.0`)
  only if nothing was published yet. Once PyPI has the version, cut a new patch version instead;
  PyPI file names can never be reused.
- `publish` fails at PyPI with an OIDC error: re-check the trusted publisher fields above
  (repository, workflow file name and environment must match exactly).
