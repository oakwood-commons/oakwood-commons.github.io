# oakwood-commons.github.io

Organization landing site for [Oakwood Commons](https://oakwood-commons.org/), deployed via GitHub Pages.

## Custom Domain & URL Routing (`oakwood-commons.org`)

DNS is hosted in Cloudflare (`DNS only` / unproxied so GitHub Pages automatically provisions and renews Let's Encrypt TLS certificates):

| URL | Target Repository | Mechanism |
| --- | --- | --- |
| `https://oakwood-commons.org/` | `oakwood-commons/oakwood-commons.github.io` | Apex `A` / `AAAA` records + org Pages custom domain |
| `https://www.oakwood-commons.org/` | Redirects to `https://oakwood-commons.org/` | `CNAME` to `oakwood-commons.github.io` |
| `https://scafctl.oakwood-commons.org/` | `oakwood-commons/scafctl` | `CNAME` to `oakwood-commons.github.io` + repo Pages custom domain |
| `https://kvx.oakwood-commons.org/` | `oakwood-commons/kvx` | `CNAME` to `oakwood-commons.github.io` + repo Pages custom domain |
| `https://oakwood-commons.org/<repo>/` | Any other repo in `oakwood-commons` with GitHub Pages enabled (e.g. `sln-agentic-code`) | Automatic inheritance from `oakwood-commons.github.io` |

## Adding a New Project Site

- **Default subpath (`https://oakwood-commons.org/<repo>/`):** Enable GitHub Pages (GitHub Actions workflow) on the repository. No Cloudflare DNS changes are needed.
- **Dedicated subdomain (`https://<project>.oakwood-commons.org/`):** Add a `DNS only` `CNAME` record in Cloudflare pointing `<project>` to `oakwood-commons.github.io`, then set `<project>.oakwood-commons.org` as the Custom Domain under the repository's **Settings -> Pages**.

## License

Apache-2.0 — see [LICENSE](LICENSE).
