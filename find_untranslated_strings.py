#!/usr/bin/env python
"""
Find translatable strings that are not wrapped by translator wrappers.
Checks both Python files and Django templates.
"""

import os
import re
import ast
from pathlib import Path
from typing import Set, Tuple, List


class TranslationChecker:
    """Check for untranslated strings in Python and template files."""

    TRANSLATION_FUNCTIONS = {
        '_', 'gettext', 'gettext_lazy', '_lazy',
        'ngettext', 'ngettext_lazy', 'pgettext', 'pgettext_lazy',
        'npgettext', 'npgettext_lazy', 'ugettext', 'ugettext_lazy'
    }

    # Patterns for template translation tags
    TEMPLATE_TRANSLATION_PATTERNS = [
        r'{%\s*trans\b.*?%}',          # {% trans ... %}
        r'{%\s*blocktrans\b.*?%}',     # {% blocktrans ... %}
        r'{{\s*.*?\|\s*i18n\s*}}',     # {{ ... | i18n }}
        r'gettext\s*\(',               # gettext(
        r'_\s*\(',                     # _(
    ]

    def __init__(self, root_path: str, exclude_dirs: Set[str] = None):
        self.root_path = Path(root_path).resolve()  # Convert to absolute path
        self.exclude_dirs = exclude_dirs or {
            '.venv', 'venv', '__pycache__', '.git', 'node_modules',
            'migrations', '.pytest_cache', 'static', 'media'
        }
        self.results = []

    def should_skip_dir(self, path: Path) -> bool:
        """Check if directory should be skipped."""
        # Only check parts relative to root, not absolute path parts
        try:
            rel_path = path.relative_to(self.root_path)
            return any(part in self.exclude_dirs for part in rel_path.parts)
        except ValueError:
            return False

    def check_python_files(self):
        """Scan Python files for untranslated strings."""
        print("Scanning Python files...")

        for py_file in self.root_path.rglob('*.py'):
            if self.should_skip_dir(py_file):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                self._check_python_content(py_file, content)
            except Exception as e:
                print(f"  ⚠ Skipped {py_file}: {type(e).__name__}: {e}")

    def _check_python_content(self, file_path: Path, content: str):
        """Check Python file for untranslated strings."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        # Get all string nodes and their translation function context
        visitor = StringVisitor()
        visitor.visit(tree)

        file_path = file_path.resolve()
        for node, is_wrapped in visitor.strings:
            if not is_wrapped:
                text = node.value if hasattr(node, 'value') else node.s
                text = text.strip()

                if self._is_translatable_python_string(text):
                    self.results.append((
                        str(file_path.relative_to(self.root_path)),
                        node.lineno,
                        text[:80],
                        'python'
                    ))

    def check_template_files(self):
        """Scan template files for untranslated strings."""
        print("Scanning template files...")

        template_extensions = ('.html', '.txt', '.email')

        for template_file in self.root_path.rglob('*'):
            if template_file.suffix not in template_extensions:
                continue
            if self.should_skip_dir(template_file):
                continue

            try:
                with open(template_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                self._check_template_content(template_file, content)
            except UnicodeDecodeError:
                pass

    def _check_template_content(self, file_path: Path, content: str):
        """Check template file for untranslated strings."""
        file_path = file_path.resolve()
        lines = content.split('\n')

        # Remove all translated content first
        protected_content = content
        for pattern in self.TEMPLATE_TRANSLATION_PATTERNS:
            protected_content = re.sub(pattern, '', protected_content, flags=re.DOTALL)

        # Also remove template tags and Django/Jinja expressions
        protected_content = re.sub(r'{%.*?%}', '', protected_content, flags=re.DOTALL)
        protected_content = re.sub(r'{{.*?}}', '', protected_content, flags=re.DOTALL)
        protected_content = re.sub(r'{#.*?#}', '', protected_content, flags=re.DOTALL)

        # Find potential translatable strings
        # Look for text that's not HTML tags, comments, or code
        suspicious_pattern = r'[A-Z][A-Za-z0-9\s\-,.:;!?\'\"]+[A-Za-z0-9.?!]'

        for line_num, line in enumerate(lines, 1):
            # Skip empty lines and HTML-only lines
            if not line.strip() or line.strip().startswith('<') or line.strip().startswith('|'):
                continue

            # Skip if line is in a translation block
            if re.search(self.TEMPLATE_TRANSLATION_PATTERNS[0], line):
                continue

            matches = re.findall(suspicious_pattern, line)
            if matches and len(matches[0]) > 3:  # Only care about substantial text
                # Filter out common non-translatable patterns
                text = matches[0].strip()
                if not self._is_non_translatable(text):
                    self.results.append((
                        str(file_path.relative_to(self.root_path)),
                        line_num,
                        text[:60],
                        'template'
                    ))

    def _is_non_translatable(self, text: str) -> bool:
        """Check if text should NOT be translated."""
        non_translatable = {
            'name', 'class', 'id', 'value', 'type', 'href', 'src', 'alt',
            'placeholder', 'action', 'method', 'onclick', 'onchange',
            'data', 'colspan', 'rowspan', 'width', 'height', 'style',
            'rows', 'cols', 'for', 'form', 'required', 'disabled',
        }
        return text.lower() in non_translatable

    @staticmethod
    def _is_translatable_python_string(text: str) -> bool:
        """Check if a Python string should be translated."""
        if not text:
            return False

        # Likely user-facing if it has spaces, uppercase, or looks like a title
        has_space = ' ' in text
        has_upper = any(c.isupper() for c in text)
        is_multiword = len(text.split()) > 1

        # Skip obvious code patterns
        if text.startswith('"') or text.startswith("'"):
            return False
        if text.isidentifier():  # Python identifier
            return False
        if text.isupper() and '_' in text:  # CONSTANT_NAME
            return False
        if all(not c.isalpha() for c in text):  # Only punctuation/numbers
            return False

        # Likely translatable: has spaces, mixed case, or multiple words
        return (has_space and (has_upper or is_multiword)) or is_multiword

    def print_results(self):
        """Print results organized by file."""
        if not self.results:
            print("\n✅ No untranslated strings found!")
            return

        print(f"\n⚠️  Found {len(self.results)} potential untranslated strings:\n")

        # Group by file
        by_file = {}
        for file_path, line_num, text, file_type in self.results:
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append((line_num, text, file_type))

        # Print grouped results
        for file_path in sorted(by_file.keys()):
            print(f"\n📄 {file_path}")
            for line_num, text, file_type in sorted(by_file[file_path]):
                print(f"   Line {line_num}: {text[:70]}")

    def save_results(self, output_file: str = 'untranslated_strings.txt'):
        """Save results to a file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Untranslated Strings Report\n")
            f.write("=" * 80 + "\n\n")

            by_file = {}
            for file_path, line_num, text, file_type in self.results:
                if file_path not in by_file:
                    by_file[file_path] = []
                by_file[file_path].append((line_num, text, file_type))

            for file_path in sorted(by_file.keys()):
                f.write(f"\n{file_path}\n")
                f.write("-" * 80 + "\n")
                for line_num, text, file_type in sorted(by_file[file_path]):
                    f.write(f"  Line {line_num}: {text}\n")

        print(f"\n💾 Results saved to {output_file}")


class StringVisitor(ast.NodeVisitor):
    """AST visitor to find strings and track if they're in translation function calls."""

    TRANSLATION_FUNCTIONS = {
        '_', 'gettext', 'gettext_lazy', '_lazy',
        'ngettext', 'ngettext_lazy', 'pgettext', 'pgettext_lazy',
        'npgettext', 'npgettext_lazy', 'ugettext', 'ugettext_lazy',
    }

    def __init__(self):
        self.strings = []  # List of (node, is_wrapped)
        self.in_translation_call = False

    def visit_Call(self, node: ast.Call):
        """Visit function calls."""
        func_name = self._get_func_name(node.func)

        old_state = self.in_translation_call

        if func_name in self.TRANSLATION_FUNCTIONS:
            self.in_translation_call = True

        self.generic_visit(node)

        self.in_translation_call = old_state

    def visit_Constant(self, node: ast.Constant):
        """Visit string constants (Python 3.8+)."""
        if isinstance(node.value, str):
            self.strings.append((node, self.in_translation_call))
        self.generic_visit(node)

    def visit_Str(self, node: ast.Str):
        """Visit string nodes (Python 3.7 compatibility)."""
        self.strings.append((node, self.in_translation_call))
        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node) -> str:
        """Extract function name from Call node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return ''


def main():
    """Run the translation checker."""
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else '.'

    checker = TranslationChecker(root)
    checker.check_python_files()
    checker.check_template_files()
    checker.print_results()
    checker.save_results()


if __name__ == '__main__':
    main()
