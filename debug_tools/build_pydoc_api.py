"""Generate static HTML API documentation from the project's docstrings using pydoc.

Bootstraps Django first (importing ``apps.app_*`` modules requires the app
registry), then walks ``apps/`` (plus the ``farm`` package) and writes one
standalone pydoc HTML page per source module under ``api-docs/``, finishing
with an ``index.html`` that groups the pages by app.

Usage (from the repo root):
    .venv/bin/python debug_tools/build_pydoc_api.py
    .venv/bin/python debug_tools/build_pydoc_api.py apps.app_entity.models

Serve the result:
    python -m http.server 8766 --directory api-docs
    # open http://localhost:8766/
"""

import importlib
import os
import sys
from html import escape
from pydoc import HTMLDoc

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farm.settings")
import django  # noqa: E402

django.setup()

OUT_DIR = os.path.join(REPO_ROOT, "api-docs")

# Directories / files never rendered (generated, env-specific or non-API).
EXCLUDED_DIRS = {"migrations", "tests", "ui_tests", "__pycache__", "debug_tools"}
EXCLUDED_FILES = {"wsgi.py", "asgi.py", "settings.py", "manage.py"}


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
    """``api-docs/apps.app_entity.models.html`` for ``apps.app_entity.models``.

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

    links = []
    for group in sorted(groups):
        rows = "\n".join(
            f'      <li><a href="{module_name}.html">'
            f"<code>{escape(module_name)}</code></a>"
            f"<div class=\"doc\">{escape(doc)}</div></li>"
            for module_name, doc in groups[group]
        )
        links.append(f"    <h2>{escape(group)}</h2>\n    <ul>\n{rows}\n    </ul>")

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
  ul {{ list-style: none; padding-left: 0; }}
  li {{ margin: .4rem 0; }}
  code {{ background: #f2f2f2; padding: .1rem .3rem; border-radius: 3px; }}
  .doc {{ color: #666; font-size: .9rem; margin-left: 1rem; }}
</style>
</head>
<body>
<h1>farm — API reference (generated with pydoc)</h1>
<p>Pages below are rendered from the modules' live docstrings. Regenerate with
<code>.venv/bin/python debug_tools/build_pydoc_api.py</code>.</p>
{chr(10).join(links)}
</body>
</html>
"""
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(index)


def main():
    requested = [a for a in sys.argv[1:] if not a.startswith("-")]
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


if __name__ == "__main__":
    sys.exit(main())
