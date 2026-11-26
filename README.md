# oakwood-commons.github.io

Organization landing site and repository directory for [Oakwood Commons](https://oakwood-commons.org/), deployed via GitHub Pages.

## How the Directory Works

- [`catalog.json`](catalog.json) controls:
  - **`featured`**: Pinned flagship hero cards at the top of `https://oakwood-commons.org/`, supported OS/arch chips, and multi-OS install tabs (`macOS / Linux`, `Windows (winget)`, binaries, `go install`).
  - **`groups`**: Category sections and prefix rules (`CLIs, TUIs & Apps`, `Solutions & Templates`, `scafctl Provider Plugins`, `scafctl Auth Plugins`, `Go Libraries & SDKs`).
  - **`exclude`**: Sandbox/internal repositories hidden from the public directory.
  - **`fallback_descriptions`**: Summary copy used only when a repository's GitHub `About` description is empty.
- [`scripts/build_site.py`](scripts/build_site.py) queries the `oakwood-commons` GitHub org API and generates [`site/index.html`](site/index.html) at build time (and daily via scheduled GitHub Actions in [`.github/workflows/pages.yml`](.github/workflows/pages.yml)), so new `sln-*` or `scafctl-plugin-*` repositories show up automatically.

To preview locally:

```bash
python3 scripts/build_site.py
python3 -m http.server -d site 8080
```

## Maintainer Guides

- **[Publishing Oakwood Commons CLIs to `winget`](docs/winget-publishing.md)** — Reusable setup and CI automation playbook (two-token GitHub App + PAT split, `.goreleaser.yaml` config, and `task winget-pr` fallback) modeled on `OakwoodCommons.kvx`.

## Custom Domain & URL Routing (`oakwood-commons.org`)

DNS is hosted in Cloudflare (`DNS only` / unproxied so GitHub Pages automatically provisions and renews Let's Encrypt TLS certificates):

| URL | Target Repository | Mechanism |
| --- | --- | --- |
| `https://oakwood-commons.org/` | `oakwood-commons/oakwood-commons.github.io` | Apex `A` / `AAAA` records + org Pages custom domain |
| `https://www.oakwood-commons.org/` | Redirects to `https://oakwood-commons.org/` | `CNAME` to `oakwood-commons.github.io` |
| `https://scafctl.oakwood-commons.org/` | `oakwood-commons/scafctl` | `CNAME` to `oakwood-commons.github.io` + repo Pages custom domain |
| `https://kvx.oakwood-commons.org/` | `oakwood-commons/kvx` | `CNAME` to `oakwood-commons.github.io` + repo Pages custom domain |
| `https://oakwood-commons.org/<repo>/` | Any other repo in `oakwood-commons` with GitHub Pages enabled (e.g. `sln-agentic-code`) | Automatic inheritance from `oakwood-commons.github.io` |

## License

Apache-2.0 — see [LICENSE](LICENSE).
