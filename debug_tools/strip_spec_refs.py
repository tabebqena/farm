#!/usr/bin/env python3
"""Strip code & test file references from specs/operations/*.md (light cleanup).

Rules applied (per the chosen "light cleanup"):
  - Markdown links pointing at code/template files under ../../apps/ keep their
    label as plain text IF the label is a code symbol (e.g. `Operation.clean()`);
    file names / paths / line-only refs (e.g. `operation.py`, `:550`) are dropped.
    A standalone "in " immediately before a dropped link is dropped with it.
  - Markdown links whose target path contains /tests/ (test methods, test files,
    coverage manifest) are dropped entirely.
  - Spec-internal links (.md files, anchors, ../ai-plans/...) are kept.
  - Bare backtick test names (`test_...`) and bare backtick app code paths
    (`apps/...`) in prose are stripped.
  - Line numbers (:NN) are stripped from kept spec links.
  - Leftover fragments ("(see )", trailing " in", "+ map", leading "→", dangling
    "—") and reference-only cells are cleaned. Standalone "—" markers are kept.
"""
import os
import re

SPECS_DIR = "specs/operations"

# Files already processed manually with the same rules — skip to avoid churn.
EXCLUDE = {
    "_OPERATION_SPEC_TEMPLATE.md",
    "op_1_cash_injection.md",
    "op_2_cash_withdrawal.md",
}


def classify(label, target):
    if "../../apps/" not in target and "../apps/" not in target:
        return "keep"
    if "/tests/" in target:
        return "drop"
    inner = label.strip()
    inner_un = re.sub(r"^`+|`+$", "", inner).strip()
    if re.search(r"\.(py|html)", inner_un):
        return "drop"
    if re.match(r"^:?\d+$", inner_un):
        return "drop"
    if "/" in inner_un:
        return "drop"
    return "symbol"


def transform_links(text):
    def repl(m):
        prefix = m.group(1) or ""
        label, target = m.group(2), m.group(3)
        c = classify(label, target)
        if c == "keep":
            return m.group(0)
        if c == "drop":
            return ""
        return prefix + label

    return re.sub(r"(\bin\s+)?\[([^\]]*)\]\(([^)]*)\)", repl, text)


def clean_cell(p):
    p = p.strip()
    p = re.sub(r"^\s*(?:,\s*)+", "", p)
    p = re.sub(r"\s*(?:,\s*)+$", "", p)
    p = re.sub(r"\s*,\s*", ", ", p)
    p = re.sub(r"\(\s*see\s*\)", "", p)
    # remove a leading arrow left by a dropped first link
    p = re.sub(r"^\s*→\s*", "", p)
    # remove a trailing —/→ only when it follows content (keep standalone "—" markers)
    p = re.sub(r"(\S)\s*[—→]\s*$", r"\1", p)
    # trailing "map"/"set" reference fragments (with , or + separator)
    p = re.sub(
        r"\s*(?:,|\+)\s*(?:entity map|op map|payment set|issuance set|repayment set|funds set|map|set)\s*$",
        "",
        p,
    )
    p = re.sub(r"\s*\+\s*$", "", p)
    p = re.sub(r"\s+", " ", p)
    p = p.strip()
    # Reference-only leftovers -> empty
    if re.fullmatch(
        r"(?:entry link|link|map|set|registry|entity map|op map|payment set|issuance set|repayment set|funds set)?"
        r"(?:,?\s*\((?:excluded|included)\))?[, ]*",
        p,
        re.I,
    ):
        return ""
    return p


def postprocess(text):
    # bare backtick test names / test file names in prose
    text = re.sub(r"`test_[a-zA-Z0-9_]+\.py`", "", text)
    text = re.sub(r"`test_[a-zA-Z0-9_]+`", "", text)
    text = re.sub(r"`tests/[a-zA-Z0-9_./]+`", "", text)
    # bare backtick app code paths in prose
    text = re.sub(r"`apps/[a-zA-Z0-9_./*<>-]+`", "", text)
    # transaction-type reference fragments left dangling after link removal
    text = re.sub(
        r"(?:entity map|op map|payment set|issuance set|repayment set|funds set)",
        "",
        text,
    )
    # "Configuration flags (all on <file>):" -> "Configuration flags:"
    text = re.sub(r"\s*\(all on\s*\)\s*:", ":", text)
    text = re.sub(r"\s*\(all on\s*\)", "", text)
    # empty parentheses (incl. those holding only commas/spaces), not attached to identifiers
    text = re.sub(r"(?<!\w)\(\s*(?:,\s*)*\s*\)", "", text)
    text = re.sub(r"(?<!\w)\(\s*\)", "", text)
    text = re.sub(r"\(\s*see\s*\)", "", text)
    text = re.sub(r"\(\s*URLs\s*[, ]*\s*\)", "", text)
    # normalize semicolon spacing (e.g. after dropping a parenthesized reference)
    text = re.sub(r"\s*;\s*", "; ", text)
    # strip line numbers from kept spec links
    text = re.sub(r"(\]\([^()#:]+):\d+\)", r"\1)", text)
    # line-end junk
    text = re.sub(r"\s*—\s*$", "", text, flags=re.M)
    text = re.sub(r"\s*→\s*$", "", text, flags=re.M)
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    # clean table cells (preserving single-space padding)
    lines = text.split("\n")
    out = []
    for line in lines:
        if line.count("|") >= 2 and not re.match(r"^\s*\|?\s*:?-+:?", line):
            parts = line.split("|")
            parts = [clean_cell(p) for p in parts]
            new_parts = []
            for i, p in enumerate(parts):
                if i == 0 or i == len(parts) - 1:
                    new_parts.append(p)
                else:
                    new_parts.append(" " + p + " ")
            line = "|".join(new_parts)
        out.append(line)
    text = "\n".join(out)
    # collapse multiple spaces outside fenced code blocks
    out = []
    in_fence = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            line = re.sub(r"[ \t]{2,}", " ", line)
        out.append(line)
    text = "\n".join(out)
    # stray space before a period or colon (e.g. after removing a parenthetical)
    text = re.sub(r"[ \t]+\.", ".", text)
    text = re.sub(r"(\S)\s+:", r"\1:", text)
    return text


def main():
    files = sorted(f for f in os.listdir(SPECS_DIR) if f.endswith(".md") and f not in EXCLUDE)
    for name in files:
        path = os.path.join(SPECS_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            original = fh.read()
        text = transform_links(original)
        text = postprocess(text)
        if text != original:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"updated: {path}")
        else:
            print(f"unchanged: {path}")


if __name__ == "__main__":
    main()
