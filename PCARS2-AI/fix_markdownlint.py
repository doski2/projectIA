#!/usr/bin/env python3
"""
Corrige avisos auto-reparables de markdownlint en archivos .md.

Reglas auto-fix: MD001, MD009, MD012, MD013, MD022, MD026, MD031, MD032, MD036, MD040, MD047, MD058, MD060.
Índice completo: docs/MARKDOWNLINT.md · oficial: github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md

Uso:
  python fix_markdownlint.py              # todos los .md (por defecto)
  python fix_markdownlint.py docs/PENDIENTES.md
  python fix_markdownlint.py --all
  python fix_markdownlint.py --check
  python fix_markdownlint.py --lint

Config: `.markdownlint.json` (raíz) + `.vscode/settings.json` (Cursor/VS Code).
Ver reglas: https://github.com/DavidAnson/markdownlint/tree/v0.40.0/doc
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BQ_PREFIX = re.compile(r"^(\s*>\s)")
MD013_WIDTH = 100
MD036_BOLD = re.compile(r"^\*\*(.+)\*\*$")
MD036_STRONG = re.compile(r"^__(.+)__$")
MD036_ITALIC_STAR = re.compile(r"^\*([^*]+)\*$")
MD036_ITALIC_UNDER = re.compile(r"^_([^_]+)_$")
MD036_PUNCT_END = re.compile(r"[.,;:!?。，；：！？]$")
HEADING = re.compile(r"^(#{1,6})\s+")
FENCE = re.compile(r"^```(\w*)$")
DELIMITER_CELL = re.compile(r"^:?-{1,}:?$")
TRAILING_PUNCT = re.compile(r"[:.,;!?]+$")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)\s")
TABLE_ROW = re.compile(r"^\s*\|")


def parse_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    parts = stripped.split("|")
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return [part.strip() for part in parts] if parts else None


def is_delimiter_row(cells: list[str]) -> bool:
    return bool(cells) and all(
        not cell or DELIMITER_CELL.fullmatch(cell.replace(" ", "")) for cell in cells
    )


def format_aligned_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    col_count = max(len(row) for row in rows)
    normalized = [row + [""] * (col_count - len(row)) for row in rows]
    widths = [
        max(max(len(row[col]) for row in normalized), 3) for col in range(col_count)
    ]
    lines: list[str] = []
    for row in normalized:
        cells = (
            ["-" * widths[col] for col in range(col_count)]
            if is_delimiter_row(row)
            else [row[col] for col in range(col_count)]
        )
        padded = [f" {cell.ljust(widths[i])} " for i, cell in enumerate(cells)]
        lines.append("|" + "|".join(padded) + "|")
    return lines


def fix_tables(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    fixes = 0
    in_fence = False
    while i < len(lines):
        if FENCE.match(lines[i].strip()):
            in_fence = not in_fence
            out.append(lines[i])
            i += 1
            continue
        if in_fence:
            out.append(lines[i])
            i += 1
            continue
        cells = parse_table_cells(lines[i])
        if cells is None:
            out.append(lines[i])
            i += 1
            continue
        start = i
        block: list[list[str]] = [cells]
        i += 1
        while i < len(lines):
            if FENCE.match(lines[i].strip()):
                break
            next_cells = parse_table_cells(lines[i])
            if next_cells is None:
                break
            block.append(next_cells)
            i += 1
        formatted = format_aligned_table(block)
        if formatted != lines[start:i]:
            fixes += 1
        out.extend(formatted)
    return "\n".join(out), fixes


def fix_heading_increment(text: str) -> tuple[str, int]:
    """MD001 — los niveles de encabezado solo suben de uno en uno."""
    lines = text.splitlines()
    out: list[str] = []
    fixes = 0
    in_fence = False
    last_level = 0

    for line in lines:
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        match = HEADING.match(line)
        if not match:
            out.append(line)
            continue

        level = len(match.group(1))
        if last_level > 0 and level > last_level + 1:
            level = last_level + 1
            title = line[match.end():]
            out.append("#" * level + title)
            fixes += 1
        else:
            out.append(line)
        last_level = level

    return "\n".join(out), fixes


def infer_fence_language(block_lines: list[str]) -> str:
    sample = "\n".join(block_lines[:12]).lower()
    if "python -m " in sample or "python apply_mod" in sample:
        return "powershell"
    if re.search(r"^\s*\$\s", sample, re.M) or ".\\" in sample:
        return "powershell"
    if re.search(r"^\s*(import |from |def |class )", sample, re.M):
        return "python"
    if re.search(r"^\s*(npm |npx |git )", sample, re.M):
        return "bash"
    return "text"


def fix_fenced_code_language_v2(text: str) -> tuple[str, int]:
    """Abre bloques sin idioma; no toca cierres ```."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    fixes = 0
    while i < len(lines):
        stripped = lines[i].strip()
        match = FENCE.match(stripped)
        if not match:
            out.append(lines[i])
            i += 1
            continue
        lang = match.group(1)
        if lang:
            out.append(lines[i])
            i += 1
            block: list[str] = []
            while i < len(lines):
                close = FENCE.match(lines[i].strip())
                if close:
                    out.append(lines[i])
                    i += 1
                    break
                block.append(lines[i])
                i += 1
            continue
        block = []
        i += 1
        while i < len(lines):
            close = FENCE.match(lines[i].strip())
            if close:
                break
            block.append(lines[i])
            i += 1
        out.append(f"```{infer_fence_language(block)}")
        out.extend(block)
        fixes += 1
        if i < len(lines):
            out.append(lines[i])
            i += 1
    return "\n".join(out), fixes


def last_heading_level(lines: list[str], before: int) -> int:
    level = 0
    for line in lines[:before]:
        match = HEADING.match(line)
        if match:
            level = len(match.group(1))
    return level or 1


def parse_emphasis_heading(line: str) -> str | None:
    """
    MD036: párrafo de una línea que es solo énfasis (sin puntuación final).
    https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md#md036---emphasis-used-instead-of-a-heading
    """
    stripped = line.strip()
    for pattern in (MD036_BOLD, MD036_STRONG, MD036_ITALIC_STAR, MD036_ITALIC_UNDER):
        match = pattern.match(stripped)
        if not match:
            continue
        text = match.group(1).strip()
        if MD036_PUNCT_END.search(text):
            return None
        return text
    return None


def fix_emphasis_headings(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    fixes = 0
    for idx, line in enumerate(lines):
        title = parse_emphasis_heading(line)
        if title is None:
            out.append(line)
            continue
        clean = TRAILING_PUNCT.sub("", title)
        parent = last_heading_level(lines, idx)
        level = min(parent + 2, 6) if parent >= 2 else min(parent + 1, 6)
        out.append(f"{'#' * level} {clean}")
        fixes += 1
    return "\n".join(out), fixes


def fix_trailing_spaces(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    fixes = 0
    for line in lines:
        trimmed = line.rstrip()
        if trimmed != line:
            fixes += 1
        out.append(trimmed)
    return "\n".join(out), fixes


def is_blank(line: str) -> bool:
    return not line.strip()


def is_list_line(line: str) -> bool:
    return bool(LIST_ITEM.match(line))


def is_fence_line(line: str) -> bool:
    return bool(FENCE.match(line.strip()))


def is_heading_line(line: str) -> bool:
    return bool(HEADING.match(line))


def ensure_blank_before(lines: list[str], idx: int) -> None:
    if idx <= 0 or is_blank(lines[idx - 1]):
        return
    lines.insert(idx, "")


def ensure_blank_after(lines: list[str], idx: int) -> None:
    if idx >= len(lines) - 1 or is_blank(lines[idx + 1]):
        return
    lines.insert(idx + 1, "")


def fix_blanks_around_blocks(text: str) -> tuple[str, int]:
    """MD022, MD031, MD032 — líneas en blanco alrededor de bloques."""
    lines = text.splitlines()
    fixes = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        if is_heading_line(line):
            before = len(lines)
            ensure_blank_before(lines, i)
            i += len(lines) - before + 1
            if len(lines) != before:
                fixes += 1
            if i < len(lines):
                after_before = len(lines)
                ensure_blank_after(lines, i)
                if len(lines) != after_before:
                    fixes += 1
                i += len(lines) - after_before
            continue

        if is_fence_line(line):
            before = len(lines)
            ensure_blank_before(lines, i)
            i += len(lines) - before + 1
            if len(lines) != before:
                fixes += 1
            while i < len(lines) and not is_fence_line(lines[i]):
                i += 1
            if i < len(lines):
                after_before = len(lines)
                ensure_blank_after(lines, i)
                i += len(lines) - after_before + 1
                if len(lines) != after_before:
                    fixes += 1
            continue

        if is_list_line(line):
            before = len(lines)
            ensure_blank_before(lines, i)
            if len(lines) != before:
                fixes += 1
            j = i + 1
            while j < len(lines) and (is_list_line(lines[j]) or is_blank(lines[j])):
                if is_list_line(lines[j]):
                    j += 1
                elif j + 1 < len(lines) and is_list_line(lines[j + 1]):
                    j += 1
                else:
                    break
            after_before = len(lines)
            ensure_blank_after(lines, j - 1)
            if len(lines) != after_before:
                fixes += 1
            i = j + (len(lines) - after_before)
            continue

        if parse_table_cells(line) is not None:
            before = len(lines)
            ensure_blank_before(lines, i)
            if len(lines) != before:
                fixes += 1
                i += len(lines) - before
            j = i + 1
            while j < len(lines) and parse_table_cells(lines[j]) is not None:
                j += 1
            after_before = len(lines)
            ensure_blank_after(lines, j - 1)
            if len(lines) != after_before:
                fixes += 1
            i = j + (len(lines) - after_before)
            continue

        i += 1

    return "\n".join(lines), fixes


def fix_multiple_blanks(text: str) -> tuple[str, int]:
    fixed, count = re.subn(r"\n{3,}", "\n\n", text)
    return fixed, count


def fix_trailing_newline(text: str) -> tuple[str, int]:
    if text and not text.endswith("\n"):
        return text + "\n", 1
    return text, 0


def should_wrap_md013(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if (
        HEADING.match(line)
        or is_fence_line(line)
        or parse_table_cells(line) is not None
        or re.fullmatch(r"[-*_]{3,}", stripped)
    ):
        return False
    return len(line) > MD013_WIDTH


def wrap_prose_line(line: str, width: int = MD013_WIDTH) -> list[str]:
    if len(line) <= width:
        return [line]
    if " " not in line:
        return [line]
    words = line.split()
    out: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > width:
            out.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        out.append(" ".join(current))
    return out if out else [line]


def wrap_line_md013(line: str, width: int = MD013_WIDTH) -> list[str]:
    bq = BQ_PREFIX.match(line)
    if bq:
        prefix = bq.group(1)
        body = line[bq.end() :].strip()
        if len(line) <= width:
            return [line]
        first_width = max(width - len(prefix), 40)
        body_lines = wrap_prose_line(body, first_width)
        result = [prefix + body_lines[0]]
        for extra in body_lines[1:]:
            result.append(prefix + extra)
        return result

    match = LIST_ITEM.match(line)
    if not match:
        return wrap_prose_line(line, width)
    indent = match.group(1)
    marker = match.group(2)
    prefix = f"{indent}{marker} "
    body = line[match.end() :].strip()
    if len(line) <= width:
        return [line]
    first_width = max(width - len(prefix), 40)
    body_lines = wrap_prose_line(body, first_width)
    cont_indent = indent + " " * len(prefix)
    result = [prefix + body_lines[0]]
    for extra in body_lines[1:]:
        result.append(cont_indent + extra)
    return result


def fix_line_length(text: str, width: int = MD013_WIDTH) -> tuple[str, int]:
    """MD013 — partir prosa en líneas <= width (como .markdownlint.json)."""
    lines = text.splitlines()
    out: list[str] = []
    fixes = 0
    in_fence = False
    for line in lines:
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or not should_wrap_md013(line):
            out.append(line)
            continue
        wrapped = wrap_line_md013(line, width)
        if len(wrapped) > 1:
            fixes += 1
        out.extend(wrapped)
    return "\n".join(out), fixes


def fix_markdown(text: str) -> tuple[str, dict[str, int]]:
    stats: dict[str, int] = {}
    text, n = fix_trailing_spaces(text)
    stats["MD009"] = n
    text, n = fix_line_length(text)
    stats["MD013"] = n
    text, n = fix_emphasis_headings(text)
    stats["MD036"] = n
    text, n = fix_heading_increment(text)
    stats["MD001"] = n
    text, n = fix_fenced_code_language_v2(text)
    stats["MD040"] = n
    text, n = fix_tables(text)
    stats["MD060"] = n
    text, n = fix_blanks_around_blocks(text)
    stats["MD022/031/032/058"] = n
    text, n = fix_multiple_blanks(text)
    stats["MD012"] = n
    text, n = fix_trailing_newline(text)
    stats["MD047"] = n
    return text, stats


def collect_markdown_files(paths: list[Path], all_docs: bool) -> list[Path]:
    if all_docs:
        found: list[Path] = []
        for pattern in ("docs/**/*.md", "camiones/**/*.md", "datos/**/*.md", "*.md"):
            found.extend(ROOT.glob(pattern))
        return sorted({p.resolve() for p in found if p.is_file()})
    return [p.resolve() for p in paths]


def run_markdownlint(files: list[Path]) -> int:
    if not files:
        return 0
    rel = [str(f.relative_to(ROOT)) for f in files]
    config = ROOT / ".markdownlint.json"
    cmd = (
        f'npx --yes markdownlint-cli2 --config="{config}" '
        + " ".join(f'"{p}"' for p in rel)
    )
    return subprocess.run(cmd, cwd=ROOT, check=False, shell=True).returncode


def process_file(path: Path, check_only: bool) -> dict[str, int]:
    original = path.read_text(encoding="utf-8")
    fixed, stats = fix_markdown(original)
    changed = fixed != original
    if changed and not check_only:
        path.write_text(fixed, encoding="utf-8", newline="\n")
    stats["changed"] = int(changed)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-fix markdownlint en .md")
    parser.add_argument("paths", nargs="*", type=Path, help="Archivos .md")
    parser.add_argument("--all", action="store_true", help="Todos los .md del repo")
    parser.add_argument("--check", action="store_true", help="No escribir; solo informar")
    parser.add_argument("--lint", action="store_true", help="Ejecutar markdownlint-cli2")
    args = parser.parse_args(argv)

    use_all = args.all or not args.paths
    files = collect_markdown_files(args.paths, use_all)
    if not files:
        parser.error("No se encontraron archivos .md")

    any_changed = False
    for path in files:
        stats = process_file(path, args.check)
        if stats.get("changed"):
            any_changed = True
            rel = path.relative_to(ROOT)
            parts = [f"{k}={v}" for k, v in sorted(stats.items()) if k != "changed" and v]
            mode = "would fix" if args.check else "fixed"
            print(f"{rel}: {mode} ({', '.join(parts)})")

    if not any_changed:
        print("Sin cambios necesarios.")

    if args.lint:
        code = run_markdownlint(files)
        if code != 0:
            print(f"markdownlint: quedan avisos (exit {code})", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
