#!/usr/bin/env python3
"""Generate site/index.html for oakwood-commons.org from GitHub org repositories + catalog.json."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog.json"
OUT_PATH = ROOT / "site" / "index.html"


def api_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "oakwood-commons-site-builder",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def clean_description(text: str) -> str:
    """Strip inline markdown links like [CEL](https://...) -> CEL for clean card copy."""
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def fetch_repos(org: str) -> list[dict]:
    repos: list[dict] = []
    page = 1
    headers = api_headers()
    while True:
        url = f"https://api.github.com/orgs/{org}/repos?type=public&per_page=100&page={page}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_latest_tag(org: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{org}/{repo}/releases/latest"
    req = urllib.request.Request(url, headers=api_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data.get("tag_name") or "").strip()
    except urllib.error.HTTPError:
        return ""


def docs_url_for(repo: dict, site_url: str, featured_map: dict[str, dict]) -> str:
    name = repo["name"]
    if name in featured_map and featured_map[name].get("docs_url"):
        return featured_map[name]["docs_url"]
    homepage = (repo.get("homepage") or "").strip()
    if homepage:
        return homepage
    if repo.get("has_pages"):
        return f"{site_url.rstrip('/')}/{name}/"
    return ""


def assign_group(name: str, groups: list[dict]) -> str:
    for g in groups:
        if name in g.get("repos", []):
            return g["id"]
    for g in groups:
        if name in g.get("exclude_repos", []):
            continue
        if any(name.startswith(ex) for ex in g.get("exclude_prefixes", [])):
            continue
        if any(name.startswith(p) for p in g.get("prefixes", [])):
            return g["id"]
    for g in groups:
        if g.get("catch_all"):
            return g["id"]
    return groups[-1]["id"]


def render_display_name(name: str, strip_prefix: str | None) -> str:
    esc_name = html.escape(name)
    if strip_prefix and name.startswith(strip_prefix):
        short = html.escape(name[len(strip_prefix):])
        prefix = html.escape(strip_prefix)
        return f'<span class="prefix">{prefix}</span><span>{short}</span>'
    return esc_name


def render_install_widget(card_id: str, tabs: list[dict], latest_tag: str) -> str:
    if not tabs:
        return ""
    version = latest_tag.lstrip("v")
    tab_btns: list[str] = []
    tab_panes: list[str] = []
    copy_svg = (
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/>'
        '<path d="M3.5 10.5h-1a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v1"/>'
        '</svg>'
    )
    for idx, t in enumerate(tabs):
        active_cls = " active" if idx == 0 else ""
        pane_hidden = "" if idx == 0 else " hidden"
        pane_id = f"install-{card_id}-{idx}"
        tab_btns.append(
            f'<button type="button" class="os-tab{active_cls}" data-target="{html.escape(pane_id)}">'
            f'{html.escape(t["label"])}</button>'
        )
        cmd = t.get("cmd", "")
        if latest_tag:
            cmd = cmd.replace("{tag}", latest_tag).replace("{version}", version)
        subnote = t.get("subnote_html", "")
        subnote_block = f'<div class="subnote">{subnote}</div>' if subnote else ""
        if cmd:
            tab_panes.append(
                f'<div id="{html.escape(pane_id)}" class="os-pane{pane_hidden}" data-cmd="{html.escape(cmd)}">'
                f'<pre class="install-cmd"><code>{html.escape(cmd)}</code></pre>'
                f'{subnote_block}'
                f'</div>'
            )
    return (
        f'<div class="install-box" data-install-box>'
        f'<div class="os-tabs">'
        f'<div class="os-tab-list">{"".join(tab_btns)}</div>'
        f'<button type="button" class="copy-btn" aria-label="Copy install command" title="Copy command">{copy_svg}</button>'
        f'</div>'
        f'{"".join(tab_panes)}'
        f'</div>'
    )


def main() -> None:
    cfg = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    org = cfg["org"]
    site_url = cfg["site_url"]
    excluded = set(cfg.get("exclude", []))
    fallbacks = cfg.get("fallback_descriptions", {})
    featured_cfg = cfg.get("featured", [])
    featured_map = {f["name"]: f for f in featured_cfg}
    groups_cfg = cfg["groups"]

    raw_repos = fetch_repos(org)
    active_repos = [
        r for r in raw_repos
        if not r.get("archived")
        and not r.get("fork")
        and not r.get("private")
        and r["name"] not in excluded
    ]
    repo_by_name = {r["name"]: r for r in active_repos}

    grouped: dict[str, list[dict]] = {g["id"]: [] for g in groups_cfg}
    for r in active_repos:
        gid = assign_group(r["name"], groups_cfg)
        grouped[gid].append(r)

    for g in groups_cfg:
        explicit_order = {name: i for i, name in enumerate(g.get("repos", []))}
        grouped[g["id"]].sort(key=lambda r: (explicit_order.get(r["name"], 999), r["name"]))

    # Render Featured Hero Cards
    featured_cards_html: list[str] = []
    for f in featured_cfg:
        r = repo_by_name.get(f["name"])
        if not r:
            continue
        desc = clean_description(r.get("description") or fallbacks.get(r["name"], ""))
        docs_url = docs_url_for(r, site_url, featured_map)
        install_guide_url = f.get("install_guide_url", "")
        gh_url = r["html_url"]
        releases_url = f.get("releases_url", "")
        primary_url = docs_url or gh_url

        latest_tag = fetch_latest_tag(org, r["name"]) if f.get("install_tabs") else ""
        badge_label = f"{f.get('badge', 'Project')} · {latest_tag}" if latest_tag else f.get("badge", "Project")

        platforms = f.get("platforms", [])
        platforms_html = ""
        if platforms:
            chips = "".join(f'<span class="os-chip">{html.escape(p)}</span>' for p in platforms)
            platforms_html = f'<div class="os-chips" aria-label="Supported platforms">{chips}</div>'

        install_html = render_install_widget(r["name"], f.get("install_tabs", []), latest_tag)

        links = []
        if docs_url:
            links.append(f'<a href="{html.escape(docs_url)}">Docs &rarr;</a>')
        if install_guide_url:
            links.append(f'<a href="{html.escape(install_guide_url)}">Install Guide</a>')
        if releases_url:
            links.append(f'<a href="{html.escape(releases_url)}">Releases</a>')
        links.append(f'<a href="{html.escape(gh_url)}">GitHub</a>')

        featured_cards_html.append(f"""
      <article class="card featured-card">
        <div class="card-top">
          <h3>
            <a href="{html.escape(primary_url)}">{html.escape(r["name"])}</a>
            <span class="badge">{html.escape(badge_label)}</span>
          </h3>
          {platforms_html}
          <p>{html.escape(desc)}</p>
          {install_html}
        </div>
        <div class="links">
          {" ".join(links)}
        </div>
      </article>""")

    # Render Filter Pills & Grouped Sections
    total_count = sum(len(v) for v in grouped.values())
    pills_html = [
        f'<button class="pill active" data-filter="all" type="button">All <span class="count">{total_count}</span></button>'
    ]
    sections_html: list[str] = []

    for g in groups_cfg:
        gid = g["id"]
        items = grouped.get(gid, [])
        if not items:
            continue
        pills_html.append(
            f'<button class="pill" data-filter="{html.escape(gid)}" type="button">'
            f'{html.escape(g["title"])} <span class="count">{len(items)}</span></button>'
        )
        cards: list[str] = []
        strip_prefix = g.get("strip_prefix")
        for r in items:
            name = r["name"]
            desc = clean_description(r.get("description") or fallbacks.get(name, "")) or "Open-source Oakwood Commons repository."
            docs_url = docs_url_for(r, site_url, featured_map)
            gh_url = r["html_url"]
            primary_url = docs_url or gh_url
            topics = r.get("topics") or []
            search_blob = f"{name} {desc} {' '.join(topics)} {g['title']}".lower()
            disp_name = render_display_name(name, strip_prefix)

            links = []
            if docs_url:
                links.append(f'<a href="{html.escape(docs_url)}">Docs &rarr;</a>')
                badge_html = '<span class="badge badge-docs">Docs</span>'
            else:
                badge_html = ""
            if name in featured_map and featured_map[name].get("releases_url"):
                links.append(f'<a href="{html.escape(featured_map[name]["releases_url"])}">Releases</a>')
            links.append(f'<a href="{html.escape(gh_url)}">GitHub</a>')

            cards.append(f"""
        <article class="card repo-card" data-group="{html.escape(gid)}" data-search="{html.escape(search_blob)}">
          <div class="card-top">
            <h3>
              <a href="{html.escape(primary_url)}">{disp_name}</a>
              {badge_html}
            </h3>
            <p>{html.escape(desc)}</p>
          </div>
          <div class="links">
            {" ".join(links)}
          </div>
        </article>""")

        sections_html.append(f"""
    <section class="repo-group" data-group-section="{html.escape(gid)}">
      <div class="group-header">
        <div>
          <h3>{html.escape(g["title"])} <span class="group-count">{len(items)}</span></h3>
          <p>{html.escape(g.get("subtitle", ""))}</p>
        </div>
      </div>
      <div class="grid compact-grid">
        {"".join(cards)}
      </div>
    </section>""")

    built_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Oakwood Commons — Open-Source Developer Tools</title>
  <meta name="description" content="Cross-platform developer tools, scafctl solutions, plugins, terminal interfaces, and Go libraries for macOS, Linux, and Windows by Oakwood Commons.">
  <link rel="canonical" href="https://oakwood-commons.org/">
  <link rel="icon" type="image/png" sizes="64x64" href="/favicon.png">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0d1117;
      --surface: #161b22;
      --surface-hover: #1c232d;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --accent: #58a6ff;
      --accent-subtle: rgba(56, 139, 253, 0.14);
      --docs-badge-bg: rgba(63, 185, 80, 0.14);
      --docs-badge-fg: #3fb950;
      --code-bg: #090c10;
      --chip-bg: rgba(139, 148, 158, 0.12);
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        color-scheme: light;
        --bg: #f6f8fa;
        --surface: #ffffff;
        --surface-hover: #f3f6f9;
        --border: #d0d7de;
        --text: #1f2328;
        --muted: #59636e;
        --accent: #0969da;
        --accent-subtle: rgba(9, 105, 218, 0.1);
        --docs-badge-bg: rgba(26, 127, 55, 0.1);
        --docs-badge-fg: #1a7f37;
        --code-bg: #eff2f5;
        --chip-bg: rgba(89, 99, 110, 0.1);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }}
    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 3rem 1.5rem 4rem;
    }}
    header {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding-bottom: 2rem;
      border-bottom: 1px solid var(--border);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.9rem;
    }}
    .brand img {{
      width: 44px;
      height: 44px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }}
    .brand h1 {{
      margin: 0;
      font-size: 1.45rem;
      letter-spacing: -0.02em;
    }}
    .gh-btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.95rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 500;
      transition: border-color 0.15s ease, background 0.15s ease;
    }}
    .gh-btn:hover {{
      background: var(--surface-hover);
      border-color: var(--accent);
    }}
    .hero {{
      padding: 2.4rem 0 1.8rem;
    }}
    .hero h2 {{
      margin: 0 0 0.65rem;
      font-size: clamp(1.7rem, 3.3vw, 2.35rem);
      line-height: 1.22;
      letter-spacing: -0.025em;
    }}
    .hero p {{
      margin: 0;
      max-width: 740px;
      color: var(--muted);
      font-size: 1.08rem;
    }}
    .section-label {{
      margin: 1.5rem 0 0.9rem;
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
      gap: 1rem;
    }}
    .compact-grid {{
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    }}
    .card {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 1.25rem;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--surface);
      transition: border-color 0.15s ease, transform 0.15s ease;
    }}
    .card:hover {{
      border-color: var(--accent);
      transform: translateY(-1px);
    }}
    .card-top h3 {{
      margin: 0 0 0.45rem;
      font-size: 1.05rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }}
    .featured-card .card-top h3 {{
      font-size: 1.2rem;
    }}
    .card-top h3 a {{
      color: var(--text);
      text-decoration: none;
      word-break: break-word;
    }}
    .card-top h3 a:hover {{
      color: var(--accent);
    }}
    .prefix {{
      color: var(--muted);
      font-weight: 400;
    }}
    .badge {{
      font-size: 0.72rem;
      font-weight: 600;
      padding: 0.15rem 0.55rem;
      border-radius: 999px;
      background: var(--accent-subtle);
      color: var(--accent);
      white-space: nowrap;
    }}
    .badge-docs {{
      background: var(--docs-badge-bg);
      color: var(--docs-badge-fg);
    }}
    .os-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0.25rem 0 0.6rem;
    }}
    .os-chip {{
      font-size: 0.7rem;
      font-weight: 500;
      padding: 0.1rem 0.48rem;
      border-radius: 6px;
      background: var(--chip-bg);
      color: var(--muted);
      border: 1px solid var(--border);
    }}
    .card p {{
      margin: 0.35rem 0 0.95rem;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .install-box {{
      margin: 0 0 1.05rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--code-bg);
      overflow: hidden;
    }}
    .os-tabs {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.35rem;
      padding-right: 0.35rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .os-tab-list {{
      display: flex;
      flex-wrap: wrap;
      min-width: 0;
    }}
    .os-tab {{
      border: none;
      background: transparent;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 600;
      padding: 0.42rem 0.52rem;
      white-space: nowrap;
      cursor: pointer;
      outline: none;
      border-bottom: 2px solid transparent;
      transition: color 0.15s ease, border-color 0.15s ease;
    }}
    .os-tab:hover {{
      color: var(--text);
    }}
    .os-tab:focus-visible, .copy-btn:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: -2px;
      border-radius: 4px;
    }}
    .os-tab.active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
    }}
    .os-pane {{
      padding: 0.6rem 0.7rem;
    }}
    .install-cmd {{
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.75rem;
      line-height: 1.5;
      color: var(--text);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .install-cmd code {{
      font-family: inherit;
      font-size: inherit;
      color: inherit;
    }}
    .copy-btn {{
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 24px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted);
      border-radius: 5px;
      padding: 0;
      cursor: pointer;
      outline: none;
      transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
    }}
    .copy-btn:hover {{
      color: var(--text);
      background: var(--surface-hover);
      border-color: var(--border);
    }}
    .copy-btn.copied {{
      color: var(--docs-badge-fg);
    }}
    .subnote {{
      margin-top: 0.4rem;
      padding-top: 0.35rem;
      border-top: 1px solid var(--border);
      font-size: 0.74rem;
      color: var(--muted);
      line-height: 1.4;
    }}
    .subnote a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .subnote a:hover {{
      text-decoration: underline;
    }}
    .subnote code {{
      font-size: 0.72rem;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.9rem;
      font-size: 0.86rem;
      font-weight: 500;
    }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .links a:hover {{
      text-decoration: underline;
    }}
    .directory-bar {{
      margin-top: 3rem;
      padding-top: 2rem;
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}
    .directory-top {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }}
    .directory-top h2 {{
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: -0.015em;
    }}
    .search-input {{
      min-width: 260px;
      flex: 0 1 320px;
      padding: 0.55rem 0.85rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      font-size: 0.9rem;
      outline: none;
    }}
    .search-input:focus {{
      border-color: var(--accent);
    }}
    .pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 0.8rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--muted);
      font-size: 0.84rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .pill:hover {{
      color: var(--text);
      border-color: var(--accent);
    }}
    .pill.active {{
      background: var(--accent-subtle);
      color: var(--accent);
      border-color: var(--accent);
    }}
    .pill .count, .group-count {{
      font-size: 0.74rem;
      padding: 0.05rem 0.42rem;
      border-radius: 999px;
      background: var(--border);
      color: var(--text);
    }}
    .repo-group {{
      margin-top: 2.25rem;
    }}
    .group-header {{
      margin-bottom: 0.9rem;
    }}
    .group-header h3 {{
      margin: 0 0 0.2rem;
      font-size: 1.12rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .group-header p {{
      margin: 0;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .empty-state {{
      display: none;
      margin: 2rem 0;
      padding: 2rem;
      text-align: center;
      border-radius: 12px;
      border: 1px dashed var(--border);
      color: var(--muted);
    }}
    .hidden {{
      display: none !important;
    }}
    footer {{
      margin-top: 3.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 0.75rem;
      font-size: 0.84rem;
      color: var(--muted);
    }}
    footer a {{
      color: var(--muted);
      text-decoration: none;
    }}
    footer a:hover {{
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <img src="https://avatars.githubusercontent.com/u/248898899?s=96&v=4" alt="Oakwood Commons logo">
        <h1>Oakwood Commons</h1>
      </div>
      <a class="gh-btn" href="https://github.com/oakwood-commons">
        GitHub Organization &rarr;
      </a>
    </header>

    <section class="hero">
      <h2>Cross-platform developer tools for configuration, scaffolding, and terminal workflows.</h2>
      <p>Open-source Go CLIs, CEL-powered solutions, pluggable providers, and libraries with signed native builds for macOS, Linux, and Windows (<code>x86_64</code> &amp; <code>ARM64</code>).</p>
    </section>

    <div class="section-label">Flagship Projects &amp; Multi-OS Install</div>
    <div class="grid">
      {"".join(featured_cards_html)}
    </div>

    <div class="directory-bar">
      <div class="directory-top">
        <h2>Repository Directory</h2>
        <input id="repo-search" class="search-input" type="search" placeholder="Filter plugins, solutions, libraries..." aria-label="Filter repositories">
      </div>
      <div class="pills" role="tablist" aria-label="Repository categories">
        {"".join(pills_html)}
      </div>
    </div>

    {"".join(sections_html)}

    <div id="empty-state" class="empty-state">
      No repositories match your current filter.
    </div>

    <footer>
      <span>&copy; Oakwood Commons &middot; Licensed under Apache-2.0 &middot; Synced {built_date}</span>
      <span>
        <a href="mailto:hello@oakwood-commons.org">hello@oakwood-commons.org</a>
        &middot;
        <a href="/.well-known/security.txt">Security</a>
        &middot;
        <a href="https://github.com/oakwood-commons">GitHub</a>
      </span>
    </footer>
  </div>

  <script>
    (function () {{
      const searchInput = document.getElementById('repo-search');
      const pills = Array.from(document.querySelectorAll('.pill'));
      const cards = Array.from(document.querySelectorAll('.repo-card'));
      const sections = Array.from(document.querySelectorAll('.repo-group'));
      const emptyState = document.getElementById('empty-state');
      let activeGroup = 'all';

      function applyFilter() {{
        const q = (searchInput.value || '').trim().toLowerCase();
        let anyVisible = false;

        cards.forEach((card) => {{
          const matchGroup = activeGroup === 'all' || card.dataset.group === activeGroup;
          const matchQuery = !q || (card.dataset.search || '').includes(q);
          const show = matchGroup && matchQuery;
          card.classList.toggle('hidden', !show);
          if (show) anyVisible = true;
        }});

        sections.forEach((sec) => {{
          const visibleInGroup = sec.querySelectorAll('.repo-card:not(.hidden)').length;
          sec.classList.toggle('hidden', visibleInGroup === 0);
        }});

        emptyState.style.display = anyVisible ? 'none' : 'block';
      }}

      pills.forEach((pill) => {{
        pill.addEventListener('click', () => {{
          activeGroup = pill.dataset.filter || 'all';
          pills.forEach((p) => p.classList.toggle('active', p === pill));
          applyFilter();
        }});
      }});

      searchInput.addEventListener('input', applyFilter);

      const checkSvg = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="13.5 4.5 6.5 11.5 2.5 7.5"/></svg>';

      document.querySelectorAll('[data-install-box]').forEach((box) => {{
        const tabs = Array.from(box.querySelectorAll('.os-tab'));
        const panes = Array.from(box.querySelectorAll('.os-pane'));
        const copyBtn = box.querySelector('.copy-btn');
        const defaultIcon = copyBtn ? copyBtn.innerHTML : '';

        tabs.forEach((tab) => {{
          tab.addEventListener('click', () => {{
            const target = tab.dataset.target;
            tabs.forEach((t) => t.classList.toggle('active', t === tab));
            panes.forEach((p) => p.classList.toggle('hidden', p.id !== target));
          }});
        }});

        if (copyBtn) {{
          copyBtn.addEventListener('click', () => {{
            const activePane = box.querySelector('.os-pane:not(.hidden)');
            const text = activePane ? (activePane.dataset.cmd || '') : '';
            if (!navigator.clipboard || !text) return;
            navigator.clipboard.writeText(text).then(() => {{
              copyBtn.innerHTML = checkSvg;
              copyBtn.classList.add('copied');
              setTimeout(() => {{
                copyBtn.innerHTML = defaultIcon;
                copyBtn.classList.remove('copied');
              }}, 1400);
            }});
          }});
        }}
      }});
    }})();
  </script>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page_html, encoding="utf-8")
    print(f"Generated {OUT_PATH} ({total_count} repositories across {len(groups_cfg)} groups)")


if __name__ == "__main__":
    main()
