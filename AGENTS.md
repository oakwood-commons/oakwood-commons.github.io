# Working Rules for `oakwood-commons.github.io`

1. **Never edit `site/index.html` or `site/sitemap.xml` directly.** Both are generated from `catalog.json` and the GitHub org API by `scripts/build_site.py` (including on a daily GitHub Actions cron). Edit `catalog.json` or `scripts/build_site.py` and regenerate locally with:

   ```bash
   GH_TOKEN="$(gh auth token)" python3 scripts/build_site.py
   ```

   Passing `GH_TOKEN` avoids unauthenticated GitHub API `403` rate limits.

2. **Never wipe `site/`.** All other files in `site/` (`404.html`, `robots.txt`, `favicon.ico`, `favicon.png`, `apple-touch-icon.png`, `.nojekyll`, `.well-known/security.txt`) are hand-maintained source files, not build artifacts. Keep `include-hidden-files: true` in `.github/workflows/pages.yml` so `.well-known/` deploys.

3. **`docs/` is maintainer-only.** Files under `docs/` (such as `docs/winget-publishing.md`) are internal runbooks and must not be rendered or copied into `site/` unless explicitly requested.

4. **Commits.** Use Conventional Commits with DCO sign-off and SSH signature (`git commit -s -S`).
