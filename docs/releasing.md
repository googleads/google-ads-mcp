# Publishing releases

This guide is for maintainers publishing `google-ads-mcp` to TestPyPI, PyPI,
and GitHub Releases. The release workflow uses PyPI Trusted Publishing and
short-lived OpenID Connect (OIDC) credentials. Do not create a `PYPI_TOKEN` or
store a PyPI password in GitHub.

The workflow file name and GitHub environment names are part of the trusted
identity. If any of them changes, update the publisher configuration on the
corresponding package index before attempting another publication.

## Required access

The maintainer performing the one-time setup needs:

- repository administration access for `googleads/google-ads-mcp`;
- Owner or Maintainer access to `google-ads-mcp` on PyPI; and
- access to the corresponding project on TestPyPI, or permission to create a
  pending publisher there.

## Configure GitHub environments

In the repository, open **Settings > Environments** and create these two
environments:

- `pypi` for production releases; and
- `testpypi` for manual rehearsals.

For `pypi`, configure at least one required reviewer and restrict deployments
to tags matching `v*`. Do not allow administrators to bypass the production
approval unless the repository's incident procedure explicitly requires it.
Required reviewers are optional for `testpypi`, but the environment must still
exist because its name is included in the OIDC identity.

## Register the PyPI Trusted Publisher

Follow PyPI's guide for [adding a publisher to an existing
project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/):

1. Sign in to PyPI and open **Your projects**.
2. Select **Manage** for `google-ads-mcp`.
3. Open **Publishing**.
4. Add a GitHub Actions publisher with these exact values:

   | Field | Value |
   | --- | --- |
   | Owner | `googleads` |
   | Repository name | `google-ads-mcp` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

After registration, the `publish-pypi` job can request a short-lived token.
The job grants `id-token: write` only for that publication and uses PyPA's
official [Trusted Publishing
action](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Register the TestPyPI Trusted Publisher

Sign in to [TestPyPI](https://test.pypi.org/) and register a separate GitHub
Actions publisher. Use the same values as production except for the environment:

| Field | Value |
| --- | --- |
| Owner | `googleads` |
| Repository name | `google-ads-mcp` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

PyPI and TestPyPI are separate services. Registering the production publisher
does not configure TestPyPI.

## Rehearse a release on TestPyPI

The manual workflow is available after `release.yml` has been merged into the
repository's default branch.

1. Open **Actions > Release > Run workflow**.
2. Select the revision to test and start the workflow.
3. Approve the `testpypi` environment if reviewers are configured.
4. Wait for both **Build and validate distributions** and **Publish to
   TestPyPI** to finish.
5. Verify the new release on TestPyPI. Its version is derived from the declared
   version and the unique workflow run ID, for example
   `0.0.1.dev123456789`.
6. Download the Actions artifact and verify that it contains one wheel, one
   source distribution, and `SHA256SUMS`.

The version change exists only in the runner workspace. It is never committed
and the TestPyPI distributions are never reused for production. If a rehearsal
must be repeated after it has published, start a new workflow run instead of
rerunning the completed publication job; the new run receives a new version.

## Publish a production release

### Prepare the version

1. Choose a new, unused `X.Y.Z` version that follows PEP 440.
2. Create a pull request that changes only `project.version` in
   `pyproject.toml`.
3. Run and approve all required CI checks.
4. Merge the version pull request into `main`.
5. Confirm that the version does not already exist on PyPI.

### Create the release tag

From an up-to-date `main`, create and push an annotated tag:

```shell
git switch main
git pull --ff-only
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Do not create the tag on an unmerged commit. Do not move or reuse it after it
has been pushed.

The workflow rejects a production tag unless all of these conditions hold:

- the tag uses the exact `vX.Y.Z` format;
- it is annotated;
- `X.Y.Z` matches `project.version`;
- the tagged commit belongs to `origin/main`; and
- the version does not already exist on PyPI.

### Approve and verify publication

1. Approve the `pypi` environment deployment.
2. Confirm that **Publish to PyPI** succeeds.
3. Confirm that **Create GitHub Release** succeeds afterward.
4. Verify the wheel and source distribution on PyPI.
5. Verify that the GitHub Release contains those same files and
   `SHA256SUMS`.
6. Install the exact published version:

   ```shell
   pipx run --spec "google-ads-mcp==X.Y.Z" google-ads-mcp
   ```

7. Close the release issue only after at least one new production version is
   available and installable.

## Failure recovery

- **Failure before PyPI publication:** correct the source through a pull
  request, choose a new version, and create a new tag. Do not move a pushed
  release tag.
- **PyPI succeeded but GitHub Release failed:** use **Re-run failed jobs** so
  the release job resumes its draft or verifies the already published assets.
  Do not rerun the successful PyPI job.
- **Defective published version:** yank it on PyPI when appropriate and publish
  a corrected version. PyPI distributions cannot be overwritten.
- **Interrupted TestPyPI rehearsal:** start a new manual run if the package was
  already uploaded, because every uploaded version is immutable.

## Troubleshooting

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Trusted Publisher reports an invalid publisher | Owner, repository, workflow, or environment differs from the registered identity | Compare all four values character for character and update the index configuration if the workflow was renamed. |
| The workflow cannot request an OIDC token | The publication job lacks `id-token: write` or is not using the registered environment | Keep `id-token: write` on the publication job and select the exact `pypi` or `testpypi` environment. |
| Publication waits indefinitely | A protected environment is awaiting review | Ask an allowed reviewer to approve or reject the deployment in GitHub Actions. |
| PyPI says a file or version already exists | The version was already uploaded | Never enable `skip-existing` for production. Choose a new version and tag. |
| Production validation rejects the tag | The tag is lightweight, mismatches `project.version`, or is not on `main` | Merge the version change first, then create a new annotated tag from the merged commit. |
| A TestPyPI rerun reports a duplicate version | The successful dispatch was rerun with the same run ID | Start a new manual workflow run to generate a new `.dev` version. |
