"""Build and serve the farm documentation site from a single pipeline file.

One file replaces the former pair ``build_pydoc_api.py`` + ``serve_docs.py``:

* ``build`` — bootstrap Django, walk ``apps/`` + ``farm/`` and write one
  standalone pydoc HTML page per source module under ``docs/api-docs/``,
  finishing with an ``index.html`` that groups the pages by app.
* ``serve`` — serve ``docs/`` as a styled site: every ``*.md`` is rendered to
  HTML on the fly (shared styling, breadcrumbs, an auto-generated list of the
  pages in the same folder, and a top navigation bar). ``api-docs/`` and any
  other static file are served unchanged, so the raw Markdown and the API
  reference share one origin.
* no subcommand — run the full pipeline: build first, then serve.

Usage (from the repo root):
    .venv/bin/python debug_tools/docs.py                  # build + serve on 8766
    .venv/bin/python debug_tools/docs.py build            # just (re)generate the API pages
    .venv/bin/python debug_tools/docs.py build apps.app_entity.models  # one module
    .venv/bin/python debug_tools/docs.py serve            # serve only (port 8766)
    .venv/bin/python debug_tools/docs.py serve 9000       # serve on another port

Then open http://localhost:8766/ (docs home) or http://localhost:8766/api-docs/
(pydoc API reference). Rendering the Markdown pages needs the pure-Python
``markdown`` package (``.venv/bin/pip install markdown``); if it is missing the
server falls back to serving the raw files.
"""

import argparse
import html
import importlib
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pydoc import HTMLDoc
from urllib.parse import unquote, urlparse

try:
    import markdown as _md
except Exception:  # pragma: no cover - optional dependency
    _md = None

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_ROOT)

DOCS_DIR = os.path.join(REPO_ROOT, "docs")
OUT_DIR = os.path.join(DOCS_DIR, "api-docs")

# Directories / files never rendered (generated, env-specific or non-API).
EXCLUDED_DIRS = {"migrations", "tests", "ui_tests", "__pycache__", "debug_tools"}
EXCLUDED_FILES = {"wsgi.py", "asgi.py", "settings.py", "manage.py"}

# Markdown entry points around the generated pages. Pages live in
# docs/api-docs/, so "../" reaches the docs/ root (served as DOCS_DIR). Kept
# commented out to keep the API index focused on the generated pages only.
DOCS_LINKS = [
    ("Home", "/"),
]

# Top-level destinations shown in the header navigation bar.
NAV_SECTIONS = [
    ("Home", "/"),
    ("Guides", "/guides/"),
    ("Features", "/features/"),
    
    ("Operations", "/operations/"),
    
    ("Logging", "/logging/"),
    ("Testing", "/testing/"),
    ("API reference", "/api-docs/"),
]

CSS = """
:root { --accent:#0a7; --fg:#222; --muted:#666; --line:#e4e4e4; }
* { box-sizing: border-box; }
body { margin:0; font: 15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: var(--fg); background:#fff; }
header.nav { background:#0b6f4f; color:#fff; }
header.nav .inner { max-width:1100px; margin:0 auto; padding:.4rem 1rem;
       display:flex; flex-wrap:wrap; gap:.25rem .9rem; align-items:baseline; }
header.nav a { color:#fff; text-decoration:none; font-weight:600; }
header.nav a.brand { font-size:1.05rem; margin-right:.4rem; }
header.nav a:hover { text-decoration:underline; }
main { max-width:1100px; margin:0 auto; padding:1rem; }
ul.breadcrumb { list-style:none; margin:.4rem 0 1rem; padding:0; font-size:.9rem; color:var(--muted); }
ul.breadcrumb li { display:inline; }
ul.breadcrumb li+li::before { content:"/\\00a0"; color:#aaa; }
.wrap { display:flex; gap:1.5rem; }
article.content { flex:1 1 auto; min-width:0; }
article.content h1 { border-bottom:2px solid var(--accent); padding-bottom:.3rem; }
article.content h2 { border-bottom:1px solid var(--line); padding-bottom:.2rem; margin-top:1.6rem; }
article.content pre { background:#f6f8fa; padding:.7rem .9rem; overflow:auto; border-radius:4px; }
article.content code { background:#f2f2f2; padding:.1rem .3rem; border-radius:3px; }
article.content pre code { background:none; padding:0; }
article.content table { border-collapse:collapse; width:100%; margin:1rem 0; }
article.content th, article.content td { border:1px solid var(--line); padding:.4rem .6rem; text-align:left; }
article.content blockquote { border-left:4px solid var(--line); margin-left:0; padding-left:1rem; color:var(--muted); }
aside.sidebar { flex:0 0 15rem; font-size:.88rem; }
aside.sidebar h3 { color:var(--accent); border-bottom:1px solid var(--line); padding-bottom:.2rem; }
aside.sidebar ul { list-style:none; margin:.3rem 0; padding-left:.2rem; }
aside.sidebar li { margin:.15rem 0; }
aside.sidebar a { color:#136; text-decoration:none; }
aside.sidebar a:hover { text-decoration:underline; }
aside.sidebar li.here a { font-weight:700; }
footer { max-width:1100px; margin:2rem auto 1rem; padding:0 1rem; color:var(--muted);
         border-top:1px solid var(--line); font-size:.85rem; }
@media (max-width: 800px) { .wrap { flex-direction:column; } aside.sidebar { flex:1 1 auto; } }
"""


# ---------------------------------------------------------------------------
# build — pydoc API pages
# ---------------------------------------------------------------------------

def _setup_django():
    """Point at the project settings and initialise the app registry."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farm.settings")
    import django  # noqa: E402

    django.setup()


def discover_modules():
    """Collect dotted module names under ``apps/`` and ``farm/``.

    An ``__init__.py`` maps to its package (``apps/app_entity/models/__init__.py``
    → ``apps.app_entity.models``) so Django never sees the package imported twice
    under a conflicting ``.__init__`` alias.
    """
    modules = []

    for root in ("apps", "farm"):
        base = os.path.join(REPO_ROOT, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for fname in sorted(filenames):
                if not fname.endswith(".py") or fname in EXCLUDED_FILES:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), REPO_ROOT)
                if fname == "__init__.py":
                    parts = rel[:-len("__init__.py") - 1].split(os.sep)
                else:
                    parts = rel[:-3].split(os.sep)
                modules.append(".".join(parts))
    return sorted(set(modules))


def module_out_path(module_name):
    """``docs/api-docs/apps.app_entity.models.html`` for ``apps.app_entity.models``.

    pydoc pages cross-link other modules using *dotted* filenames, so pages are
    written flat (``<module>.html``) rather than as nested directories — that
    keeps the intra-documentation navigation working.
    """
    return os.path.join(OUT_DIR, module_name + ".html")


def render_module(module_name):
    """Return the pydoc HTML page for *module_name*."""
    module = importlib.import_module(module_name)
    htmldoc = HTMLDoc()
    return htmldoc.docmodule(module)


def short_doc(module):
    """First sentence of the module docstring (fallback: module name)."""
    doc = (getattr(module, "__doc__", "") or "").strip()
    first = doc.split("\n\n")[0].strip().splitlines()
    return first[0] if first else module.__name__


def build_index(pages):
    """Write a grouped index.html listing every generated page."""
    groups = {}
    for module_name, doc in sorted(pages.items()):
        group = module_name.split(".")[1] if module_name.startswith("apps.") else "farm"
        groups.setdefault(group, []).append((module_name, doc))

    docs_links = "\n".join(
        f'      <li><a href="{href}">{html.escape(label)}</a></li>'
        for label, href in DOCS_LINKS
    )
    docs_block = (
        "    <h2>Project docs <span class=\"hint\">(raw Markdown)</span></h2>\n"
        f"    <ul>\n{docs_links}\n    </ul>\n"
        "    <p class=\"hint\">Pages below are rendered from the modules' live "
        "docstrings. Rebuild and serve the whole site with "
        "<code>.venv/bin/python debug_tools/docs.py</code> (or "
        "<code>debug_tools/docs.py build</code> then "
        "<code>debug_tools/docs.py serve</code>).</p>\n"
    )

    links = []
    for group in sorted(groups):
        rows = "\n".join(
            f'      <li><a href="{module_name}.html">'
            f"<code>{html.escape(module_name)}</code></a>"
            f"<div class=\"doc\">{html.escape(doc)}</div></li>"
            for module_name, doc in groups[group]
        )
        links.append(f"    <h2>{html.escape(group)}</h2>\n    <ul>\n{rows}\n    </ul>")

    index = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>farm — API reference (pydoc)</title>
    <style>
      body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
             max-width: 60rem; margin: 2rem auto; padding: 0 1rem; color: #222; }}
      h1 {{ border-bottom: 2px solid #0a7; padding-bottom: .25rem; }}
      h2 {{ color: #0a7; margin-top: 2rem; }}
      h2 .hint, p.hint {{ color: #888; font-size: .85rem; font-weight: normal; }}
      ul {{ list-style: none; padding-left: 0; }}
      li {{ margin: .4rem 0; }}
      code {{ background: #f2f2f2; padding: .1rem .3rem; border-radius: 3px; }}
      .doc {{ color: #666; font-size: .9rem; margin-left: 1rem; }}
    </style>
    </head>
    <body>
    <h1>farm — API reference (generated with pydoc)</h1>
    {docs_block}
    {chr(10).join(links)}
    </body>
    </html>
    """
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(index)


def cmd_build(requested):
    """Render pydoc pages for *requested* modules (all if empty). Returns exit code."""
    _setup_django()
    modules = requested or discover_modules()

    pages = {}
    failed = []
    for module_name in modules:
        try:
            doc = render_module(module_name)
        except Exception as exc:  # keep going on any single import/render failure
            failed.append((module_name, repr(exc)))
            continue
        path = module_out_path(module_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc)
        try:
            module = importlib.import_module(module_name)
            pages[module_name] = short_doc(module)
        except Exception:
            pages[module_name] = module_name
        print(f"OK   {module_name}")

    build_index(pages)
    print(f"\nWrote {len(pages)} module pages to {OUT_DIR}")
    print(f"Index: {os.path.join(OUT_DIR, 'index.html')}")
    if failed:
        print(f"\n{len(failed)} module(s) FAILED to render:")
        for name, err in failed:
            print(f"  - {name}: {err}")
        return 1
    return 0


# ---------------------------------------------------------------------------
# serve — styled Markdown + static docs over HTTP
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    md = _md
    assert md is not None, "the 'markdown' package is required"
    return md.markdown(
        text,
        extensions=["extra", "toc", "sane_lists", "smarty"],
        output_format="html",
    )


def title_from_md(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else fallback


def sibling_links(rel_dir: str, current_file: str) -> str:
    """``<li>`` links to the markdown pages in the same folder as *current_file*."""
    folder = os.path.join(DOCS_DIR, rel_dir)
    items = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".md"):
                continue
            rel = os.path.join(rel_dir, name) if rel_dir else name
            here = rel == current_file
            label = name[:-3].replace("_", " ").replace("-", " ")
            items.append(
                f'<li class="{"here" if here else ""}"><a href="/{rel}">{html.escape(label)}</a></li>'
            )
    if not items:
        return ""
    return "<ul>" + "".join(items) + "</ul>"


def breadcrumb_html(parts) -> str:
    crumbs = ['<li><a href="/">Home</a></li>']
    acc = ""
    for part in parts[:-1]:
        acc += "/" + part
        label = part.replace("-", " ").title()
        crumbs.append(f'<li><a href="{acc}/">{html.escape(label)}</a></li>')
    if parts:
        label = parts[-1][:-3].replace("_", " ").replace("-", " ").title()
        crumbs.append(f"<li>{html.escape(label)}</li>")
    return '<ul class="breadcrumb">' + "".join(crumbs) + "</ul>"


def nav_html() -> str:
    links = "".join(
        f'<a href="{path}">{html.escape(label)}</a>' for label, path in NAV_SECTIONS
    )
    return f'<header class="nav"><div class="inner"><a class="brand" href="/">farm docs</a>{links}</div></header>'


def page_html(title: str, body: str, sidebar: str, breadcrumbs: str) -> bytes:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — farm docs</title>
<style>{CSS}</style>
</head>
<body>
{nav_html()}
<main>
{breadcrumbs}
<div class="wrap">
  <article class="content">{body}</article>
  {sidebar}
</div>
</main>
<footer>farm — documentation. Markdown pages are rendered on the fly;
rebuild and serve the whole site with
<code>.venv/bin/python debug_tools/docs.py</code>.</footer>
</body>
</html>
""".encode("utf-8")


class DocsHandler(SimpleHTTPRequestHandler):
    """Render ``*.md`` (and directory READMEs) as styled HTML; static otherwise."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DOCS_DIR, **kwargs)

    def log_message(self, fmt, *args):  # keep the standard access log
        super().log_message(fmt, *args)

    def _md_page(self, rel_md: str):
        """Serve a rendered markdown page for a path that ends in .md."""
        text = open(os.path.join(DOCS_DIR, rel_md), encoding="utf-8").read()
        title = title_from_md(text, os.path.basename(rel_md)[:-3].replace("_", " ").title())
        body = render_markdown(text) if _md else (
            f"<p><code>markdown</code> is not installed — "
            f"raw content: <a href=\"/{rel_md}\">view source</a></p>"
        )
        rel_dir, _ = os.path.split(rel_md)
        parts = rel_md.split("/")
        sidebar = (
            '<aside class="sidebar"><h3>Related pages</h3>'
            + sibling_links(rel_dir, rel_md)
            + "</aside>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page := page_html(title, body, sidebar, breadcrumb_html(parts)))))
        self.end_headers()
        self.wfile.write(page)

    def _directory_page(self, rel_dir: str):
        """Serve a folder: its README.md (rendered) or a styled index."""
        folder = os.path.join(DOCS_DIR, rel_dir)
        readme = os.path.join(folder, "README.md")
        index_html = os.path.join(folder, "index.html")
        if os.path.isfile(index_html):
            # Static index (e.g. the pydoc api-docs index).
            self.path = "/" + os.path.join(rel_dir, "index.html")
            return super().do_GET()
        if os.path.isfile(readme):
            return self._md_page((rel_dir + "/README.md") if rel_dir else "README.md")
        # Auto index of the folder.
        listing = []
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            href = "/" + os.path.join(rel_dir, name) + ("/" if os.path.isdir(full) else "")
            label = name[:-3].replace("_", " ").replace("-", " ").title() if name.endswith(".md") else name
            listing.append(f'<li><a href="{href}">{html.escape(label)}</a></li>')
        body = f"<h1>/{rel_dir}</h1><ul>{''.join(listing)}</ul>"
        parts = (rel_dir.split("/") if rel_dir else [])
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        payload = page_html(rel_dir or "docs", body, "", breadcrumb_html(parts))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        rel = unquote(parsed.path).lstrip("/")
        if rel.endswith(".md") and _md is not None:
            # A .md page that no longer exists (e.g. removed during a docs
            # reorganization): reply 404 instead of crashing this thread.
            if not os.path.isfile(os.path.join(DOCS_DIR, rel)):
                self.send_error(404, "Not Found")
                return
            return self._md_page(rel)
        folder = os.path.join(DOCS_DIR, rel)
        if os.path.isdir(folder):
            return self._directory_page(rel)
        return super().do_GET()


def cmd_serve(port):
    """Serve ``docs/`` (rendering Markdown on the fly) until interrupted."""
    if _md is None:
        print("warning: 'markdown' not installed; .md files will be served raw.", file=sys.stderr)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), DocsHandler)
    print(f"Serving docs from {DOCS_DIR}")
    print(f"  docs home   -> http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.shutdown()
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docs.py",
        description="Build and serve the farm documentation site.",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_build = sub.add_parser("build", help="generate the pydoc API pages under docs/api-docs/")
    p_build.add_argument(
        "modules", nargs="*",
        help="optional dotted module names to render (default: all discovered modules)",
    )

    p_serve = sub.add_parser("serve", help="serve docs/ as a styled site")
    p_serve.add_argument("port", nargs="?", type=int, default=8766,
                         help="port to listen on (default: 8766)")

    args = parser.parse_args(argv)

    if args.command == "build":
        return cmd_build(args.modules)
    if args.command == "serve":
        return cmd_serve(args.port)
    # No subcommand → full pipeline: build the API pages, then serve them.
    code = cmd_build([])
    if code != 0:
        return code
    return cmd_serve(8766)


if __name__ == "__main__":
    sys.exit(main())
