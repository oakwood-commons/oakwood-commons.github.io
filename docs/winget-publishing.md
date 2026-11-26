# Publishing Oakwood Commons CLIs to Windows Package Manager (`winget`)

This guide captures the end-to-end setup and hard-won lessons from onboarding [`OakwoodCommons.kvx`](https://github.com/microsoft/winget-pkgs/pull/351751) so any Oakwood Commons Go CLI (`scafctl`, `cobra-explorer`, etc.) can publish to `winget` without repeating the initial trial-and-error.

---

## Why Initial Setup Was Tricky (and What Is Already Done Org-Wide)

When `kvx` was first onboarded (see [`kvx#30`](https://github.com/oakwood-commons/kvx/pull/30), [`kvx#32`](https://github.com/oakwood-commons/kvx/pull/32), and [`kvx#33`](https://github.com/oakwood-commons/kvx/pull/33)), three non-obvious constraints surfaced:

1. **Two-token split is mandatory (GitHub App vs. cross-fork PR):**
   - A GitHub App installation token scoped to `oakwood-commons` **can** push manifest branches (e.g., `scafctl-0.48.0`) to our fork (`oakwood-commons/winget-pkgs`), **but cannot open a cross-organization pull request against `microsoft/winget-pkgs`**.
   - Therefore, GoReleaser's `winget[].repository.pull_request.enabled` **must be set to `false`**. GoReleaser pushes the branch to `oakwood-commons/winget-pkgs` using `WINGET_GITHUB_TOKEN` (minted by `OC_AUTOMATION_APP_ID`), and a separate workflow step opens the PR to `microsoft/winget-pkgs` using `WINGET_PR_PAT` (a classic user PAT with `public_repo` scope whose owner has signed the Microsoft CLA).
2. **Publisher identifier must be PascalCase (`OakwoodCommons.<tool>`):**
   - `microsoft/winget-pkgs` manifest validation enforces `manifests/o/OakwoodCommons/<tool>/<version>/` without hyphens in the publisher segment (i.e., `OakwoodCommons.scafctl`, **not** `oakwood-commons.scafctl`).
3. **First submission for a new package is manually moderated:**
   - GoReleaser generates the initial multi-file YAML manifest directory automatically on the first release tag — you do **not** need `wingetcreate` on Windows to bootstrap the manifest.
   - However, the **very first PR** for a brand-new `PackageIdentifier` on `microsoft/winget-pkgs` requires human moderator approval (typically 1–5 days) after automated validation passes. Subsequent version bumps auto-merge once validation bots pass.

### Org-Level Infrastructure Already Provisioned (Do Not Recreate)

| Asset | Status | Purpose |
| --- | --- | --- |
| `oakwood-commons/winget-pkgs` | Live fork of `microsoft/winget-pkgs` | Staging repo where GoReleaser pushes `<tool>-<version>` manifest branches |
| `OC_AUTOMATION_APP_ID` + `OC_AUTOMATION_APP_PRIVATE_KEY` | Configured for `oakwood-commons` | Mints short-lived `WINGET_GITHUB_TOKEN` (and `HOMEBREW_TAP_GITHUB_TOKEN`) |
| `WINGET_PR_PAT` + Microsoft CLA | Configured on `kvx` (share at org/repo level) | Classic PAT (`public_repo`) used by `gh pr create --repo microsoft/winget-pkgs` |
| Publisher namespace `OakwoodCommons` | Established in `microsoft/winget-pkgs` | Houses `OakwoodCommons.kvx` (`manifests/o/OakwoodCommons/...`) |

---

## Step-by-Step Checklist for Adding a New CLI (e.g. `scafctl`)

### 1. Ensure Windows Archive Format Is `.zip` in `.goreleaser.yaml`

Portable CLI packages in `winget` expect `.zip` archives on Windows (`windows/amd64` and `windows/arm64`):

```yaml
archives:
  - format_overrides:
      - goos: windows
        formats: ['zip']
```

### 2. Add the `winget` Section to `.goreleaser.yaml`

Replace `<tool>` and metadata fields as appropriate. Keep `pull_request.enabled: false` and `skip_upload: auto` (so `-rc` / `-beta` prerelease tags skip `winget`):

```yaml
winget:
  - name: scafctl
    publisher: OakwoodCommons
    short_description: "Configuration discovery and scaffolding CLI using CEL for dynamic evaluation"
    license: "Apache-2.0"
    publisher_url: "https://oakwood-commons.org"
    publisher_support_url: "https://github.com/oakwood-commons/scafctl/issues"
    package_identifier: "OakwoodCommons.scafctl"
    homepage: "https://scafctl.oakwood-commons.org"
    description: "scafctl is a CLI tool for declarative data resolution, CEL transformation, and composable scaffolding workflows."
    license_url: "https://github.com/oakwood-commons/scafctl/blob/main/LICENSE"
    release_notes_url: "https://github.com/oakwood-commons/scafctl/releases/tag/{{ .Tag }}"
    tags:
      - cli
      - cel
      - configuration
      - scaffolding
      - devops
    skip_upload: auto
    repository:
      owner: oakwood-commons
      name: winget-pkgs
      branch: "scafctl-{{ .Version }}"
      token: "{{ .Env.WINGET_GITHUB_TOKEN }}"
      pull_request:
        enabled: false
```

### 3. Grant Repo Access to Secrets / Variables

Ensure the target repository has access to:

- Organization variable `OC_AUTOMATION_APP_ID` and secret `OC_AUTOMATION_APP_PRIVATE_KEY` (and verify `oakwood-commons/winget-pkgs` is enabled in the GitHub App's repository access list — already enabled from `kvx`).
- Secret `WINGET_PR_PAT` (classic PAT with `public_repo` scope).

### 4. Wire Token Generation & PR Submission in `.github/workflows/release.yml`

1. Mint `WINGET_GITHUB_TOKEN` before running GoReleaser and pass it in `env:`:

```yaml
      - name: Generate winget token
        id: winget-token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          app-id: ${{ vars.OC_AUTOMATION_APP_ID }}
          private-key: ${{ secrets.OC_AUTOMATION_APP_PRIVATE_KEY }}
          owner: oakwood-commons
          repositories: winget-pkgs
```

2. Add the cross-fork PR step after GoReleaser finishes (note: **avoid shell `<<EOF` heredocs** inside workflow `run:` blocks — use `printf` as fixed in [`kvx#33`](https://github.com/oakwood-commons/kvx/pull/33)):

```yaml
      - name: Submit winget PR
        if: success()
        env:
          WINGET_PR_PAT: ${{ secrets.WINGET_PR_PAT }}
          GH_TOKEN: ${{ secrets.WINGET_PR_PAT }}
        run: |
          TAG="${GITHUB_REF#refs/tags/}"
          VERSION="${TAG#v}"
          BRANCH="scafctl-${VERSION}"

          if [[ "$VERSION" == *-* ]]; then
            echo "::notice::Skipping winget PR for prerelease version $VERSION"
            exit 0
          fi

          if [ -z "$WINGET_PR_PAT" ]; then
            echo "::warning::No WINGET_PR_PAT secret found. Submit manually with: task winget-pr"
            exit 0
          fi

          BODY_FILE="$(mktemp)"
          printf '## Automated winget manifest update\n\nRelease: https://github.com/oakwood-commons/scafctl/releases/tag/%s\n' "$TAG" > "$BODY_FILE"

          if gh pr create \
            --repo microsoft/winget-pkgs \
            --head "oakwood-commons:$BRANCH" \
            --base master \
            --title "New version: OakwoodCommons.scafctl version $VERSION" \
            --body-file "$BODY_FILE"; then
            echo "::notice::Winget PR created successfully."
          else
            echo "::warning::Failed to create winget PR. Submit manually with: task winget-pr"
          fi
          rm -f "$BODY_FILE"
```

### 5. Add a Manual Fallback Task (`task winget-pr`) in `taskfile.yaml`

Adding `task winget-pr` lets any maintainer submit the already-pushed `oakwood-commons:<tool>-<version>` branch from their local `gh` CLI if `WINGET_PR_PAT` ever expires or hits a transient GitHub API error:

```yaml
  winget-pr:
    desc: Open a winget PR to microsoft/winget-pkgs for the latest stable release
    cmds:
      - |
        VERSION="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n1)"
        BRANCH="scafctl-${VERSION#v}"
        BODY_FILE="$(mktemp)"
        printf '## Automated winget manifest update\n\nRelease: https://github.com/oakwood-commons/scafctl/releases/tag/%s\n' "$VERSION" > "$BODY_FILE"
        gh pr create \
          --repo microsoft/winget-pkgs \
          --head "oakwood-commons:$BRANCH" \
          --base master \
          --title "New version: OakwoodCommons.scafctl version ${VERSION#v}" \
          --body-file "$BODY_FILE"
        rm -f "$BODY_FILE"
```

### 6. Verify & Update Install Docs Once PR #1 Merges

Once the first `microsoft/winget-pkgs` PR merges:

1. Test on Windows: `winget install OakwoodCommons.scafctl`
2. Add `winget install OakwoodCommons.scafctl` to the project's `README.md`, `home/_index.md`, and [`catalog.json`](../catalog.json) on `oakwood-commons.org`.
