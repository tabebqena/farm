#!/usr/bin/env python
"""
Split large test files into smaller files by test class.
Run from the project root: python split_tests.py
"""
import os
import re
from pathlib import Path


def extract_imports_and_helpers(content):
    """Extract imports and shared helper functions from test file."""
    lines = content.split('\n')
    imports = []
    helpers = []
    i = 0

    # Collect imports
    while i < len(lines):
        line = lines[i]
        if line.startswith(('import ', 'from ')):
            imports.append(line)
            i += 1
        elif line.strip() == '' and i < len(lines) - 1 and lines[i + 1].startswith(('import ', 'from ')):
            i += 1
        elif line.startswith('#') or line.strip() == '':
            i += 1
        else:
            break

    # Collect shared helpers (functions before first test class)
    while i < len(lines):
        line = lines[i]
        if line.startswith('class '):
            break
        helpers.append(line)
        i += 1

    return '\n'.join(imports), '\n'.join(helpers), i


def extract_test_classes(content):
    """Extract test classes from content."""
    # Find all test class definitions
    pattern = r'^class\s+(\w+)\s*\([^)]*\)\s*:'
    classes = []

    lines = content.split('\n')
    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            class_name = match.group(1)
            classes.append((i, class_name))

    return classes


def extract_class_content(lines, start_idx, end_idx):
    """Extract class content from start_idx to end_idx."""
    return '\n'.join(lines[start_idx:end_idx])


def split_test_file(filepath):
    """Split a test file into separate files by test class."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Get imports and helpers
    imports, helpers, _ = extract_imports_and_helpers(content)
    lines = content.split('\n')

    # Find test classes
    class_indices = extract_test_classes(content)

    if len(class_indices) <= 1:
        print(f"⏭️  Skipping {filepath.name}: only 1 or 0 test classes")
        return

    print(f"📝 Splitting {filepath.name} ({len(class_indices)} test classes)...")

    # Create new files for each class
    for idx, (start_line, class_name) in enumerate(class_indices):
        # Determine end line (start of next class or end of file)
        if idx + 1 < len(class_indices):
            end_line = class_indices[idx + 1][0]
        else:
            end_line = len(lines)

        # Extract class content
        class_content = '\n'.join(lines[start_line:end_line]).rstrip()

        # Build new file content
        new_content = f"""{imports}

{helpers}

{class_content}
"""

        # Create new filename based on class name
        # Convert CamelCase to snake_case
        snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        new_filename = filepath.parent / f"test_{snake_case}.py"

        # Skip if file already exists
        if new_filename.exists():
            print(f"   ⏭️  {new_filename.name} already exists, skipping")
            continue

        # Write new file
        with open(new_filename, 'w') as f:
            f.write(new_content)

        print(f"   ✅ Created {new_filename.name}")


def main():
    """Split test files in the app_operation tests directory."""
    tests_dir = Path('/media/dr/Main/Others/Programming/django_apps/farm/apps/app_operation/tests')

    # Get all test files
    test_files = sorted(tests_dir.glob('test_*.py'))

    # Files to split (all files with multiple test classes)
    files_to_split = None  # None means split all with 2+ classes

    print(f"🔍 Found {len(test_files)} test files in {tests_dir.name}\n")

    for test_file in test_files:
        num_classes = len(extract_test_classes(test_file.read_text()))

        # Split if either files_to_split is None (split all) or file is in the list
        should_split = (files_to_split is None and num_classes > 1) or (
            files_to_split is not None and test_file.name in files_to_split
        )

        if should_split:
            split_test_file(test_file)

    print("\n✨ Done!")


if __name__ == '__main__':
    main()
