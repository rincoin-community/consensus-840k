#!/usr/bin/env python3
"""Inline QMD include shortcodes and copy non-QMD include dependencies.

All include paths are resolved relative to the directory containing the main
source QMD. QMD includes are expanded recursively and enclosed in stable HTML
comments so a later run can replace the generated target from its source.

Original project software in this file is licensed under MIT.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(.+?)\s*>\}\}", re.DOTALL)
LATEX_GRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}"
)
MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))",
    re.DOTALL,
)
HTML_IMAGE_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))",
    re.IGNORECASE,
)
METADATA_FILE_KEYS = {
    "bibliography",
    "citation-abbreviations",
    "csl",
    "cover-image",
    "filters",
    "format-resources",
    "include-after-body",
    "include-before-body",
    "include-in-header",
    "logo",
    "metadata-file",
    "reference-doc",
    "template",
}


class PlanError(Exception):
    """An error found before output mutation is allowed."""


@dataclass(frozen=True)
class NonQmdCopy:
    source: Path
    destination: Path
    reference: str
    kind: str


@dataclass(frozen=True)
class QmdInline:
    source: Path
    reference: str
    containing_file: Path


@dataclass
class ExpansionPlan:
    source: Path
    target: Path
    rendered: bytes
    qmd_inlines: list[QmdInline]
    non_qmd_copies: list[NonQmdCopy]


def absolute_lexical(path: Path) -> Path:
    """Return an absolute normalized path without resolving the final symlink."""

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def decode_qmd(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError(f"QMD file is not valid UTF-8: {path}") from exc
    except OSError as exc:
        raise PlanError(f"Cannot read QMD file {path}: {exc}") from exc


def parse_include_reference(body: str, containing_file: Path) -> str:
    try:
        tokens = shlex.split(body, posix=True)
    except ValueError as exc:
        raise PlanError(
            f"Invalid include syntax in {containing_file}: {body!r}: {exc}"
        ) from exc

    if len(tokens) != 1:
        raise PlanError(
            f"Include in {containing_file} must contain exactly one path: {body!r}"
        )

    reference = tokens[0]
    if not reference:
        raise PlanError(f"Empty include path in {containing_file}")
    if Path(reference).is_absolute():
        raise PlanError(
            f"Include paths must be relative to the source QMD directory: {reference}"
        )
    if "\x00" in reference:
        raise PlanError(f"Include path contains a NUL byte in {containing_file}")
    return reference


def front_matter(text: str) -> str:
    opening = re.match(r"\A(?:\ufeff)?---[ \t]*\r?\n", text)
    if not opening:
        return ""
    remainder = text[opening.end() :]
    closing = re.search(r"(?m)^---[ \t]*\r?$", remainder)
    if not closing:
        return ""
    return remainder[: closing.start()]


def scalar_or_list(value: str) -> list[str]:
    value = value.strip()
    if not value or value in {"|", ">", "|-", ">-", "|+", ">+"}:
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        try:
            return [
                item.strip().strip("\"'")
                for item in next(csv.reader([inner], skipinitialspace=True))
                if item.strip()
            ]
        except (csv.Error, StopIteration):
            return []
    try:
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except ValueError:
        return [value.strip("\"'")]
    return tokens if len(tokens) == 1 else [value.strip("\"'")]


def metadata_file_references(text: str) -> list[tuple[str, str]]:
    metadata = front_matter(text)
    if not metadata:
        return []
    lines = metadata.splitlines()
    references: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)([A-Za-z0-9_-]+):(?:\s*(.*))?$", lines[index])
        if not match or match.group(2) not in METADATA_FILE_KEYS:
            index += 1
            continue
        indentation = len(match.group(1))
        key = match.group(2)
        value = (match.group(3) or "").strip()
        if value:
            references.extend((item, f"metadata {key}") for item in scalar_or_list(value))
            index += 1
            continue

        index += 1
        while index < len(lines):
            item = re.match(r"^(\s*)-\s+(.+?)\s*$", lines[index])
            if not item or len(item.group(1)) <= indentation:
                break
            references.extend(
                (path, f"metadata {key}")
                for path in scalar_or_list(item.group(2))
            )
            index += 1
    return references


def render_file_references(text: str) -> list[tuple[str, str]]:
    references = metadata_file_references(text)
    references.extend(
        (match.group(1), "LaTeX includegraphics")
        for match in LATEX_GRAPHICS_RE.finditer(text)
    )
    references.extend(
        (match.group(1) or match.group(2), "Markdown image")
        for match in MARKDOWN_IMAGE_RE.finditer(text)
    )
    references.extend(
        (
            match.group(1) or match.group(2) or match.group(3),
            "HTML image",
        )
        for match in HTML_IMAGE_RE.finditer(text)
    )
    return references


def local_reference(reference: str) -> str | None:
    candidate = html.unescape(reference.strip())
    if candidate.startswith("<") and candidate.endswith(">"):
        candidate = candidate[1:-1]
    if not candidate or candidate.startswith("#") or candidate.startswith("//"):
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return None
    return unquote(parsed.path)


def paths_refer_to_same_file(first: Path, second: Path) -> bool:
    try:
        if os.path.samefile(first, second):
            return True
    except (FileNotFoundError, OSError):
        pass
    try:
        return first.resolve(strict=False) == second.resolve(strict=False)
    except OSError:
        return first == second


def build_plan(source_argument: Path, target_argument: Path) -> ExpansionPlan:
    source = absolute_lexical(source_argument)
    target = absolute_lexical(target_argument)

    if source.suffix.lower() != ".qmd":
        raise PlanError(f"Source must have a .qmd extension: {source}")
    if target.suffix.lower() != ".qmd":
        raise PlanError(f"Target must have a .qmd extension: {target}")
    if not source.is_file():
        raise PlanError(f"Source QMD does not exist or is not a file: {source}")
    if paths_refer_to_same_file(source, target):
        raise PlanError(f"Source and target resolve to the same file: {source}")

    source_directory = source.parent
    target_directory = target.parent
    copy_non_qmd = not paths_refer_to_same_file(
        source_directory, target_directory
    )
    planned_copies: dict[Path, NonQmdCopy] = {}
    qmd_inlines: list[QmdInline] = []

    def plan_non_qmd(reference: str, containing_file: Path, kind: str) -> None:
        normalized = local_reference(reference)
        if normalized is None:
            if kind == "Quarto include":
                raise PlanError(
                    f"Quarto include must use a local relative path: {reference}"
                )
            return
        if not normalized:
            raise PlanError(f"Empty local {kind} path in {containing_file}")
        if Path(normalized).is_absolute():
            raise PlanError(
                f"{kind} paths must be relative to the source QMD directory: "
                f"{reference}"
            )

        include_path = absolute_lexical(source_directory / normalized)
        if not include_path.is_file():
            raise PlanError(
                f"{kind} does not exist or is not a file: {reference} "
                f"(resolved as {include_path}; referenced by {containing_file})"
            )
        if not copy_non_qmd:
            return

        destination = absolute_lexical(target_directory / normalized)
        if paths_refer_to_same_file(include_path, destination):
            return
        if paths_refer_to_same_file(destination, target):
            raise PlanError(
                "A non-QMD include would overwrite the main target: "
                f"{reference} -> {destination}"
            )
        copy = NonQmdCopy(
            source=include_path,
            destination=destination,
            reference=reference,
            kind=kind,
        )
        previous = planned_copies.get(destination)
        if previous and not paths_refer_to_same_file(previous.source, copy.source):
            raise PlanError(
                "Different non-QMD includes map to the same target: "
                f"{previous.reference} and {reference} -> {destination}"
            )
        planned_copies[destination] = copy

    def expand(text: str, containing_file: Path, stack: tuple[Path, ...]) -> str:
        def replace(match: re.Match[str]) -> str:
            reference = parse_include_reference(match.group(1), containing_file)
            include_path = absolute_lexical(source_directory / reference)
            if not include_path.is_file():
                raise PlanError(
                    f"Include does not exist or is not a file: {reference} "
                    f"(resolved as {include_path}; referenced by {containing_file})"
                )

            if include_path.suffix.lower() == ".qmd":
                include_identity = include_path.resolve(strict=True)
                if include_identity in stack:
                    cycle = " -> ".join(
                        os.fspath(path) for path in (*stack, include_identity)
                    )
                    raise PlanError(f"Recursive QMD include cycle: {cycle}")
                qmd_inlines.append(
                    QmdInline(
                        source=include_path,
                        reference=reference,
                        containing_file=containing_file,
                    )
                )
                included_text = decode_qmd(include_path)
                expanded = expand(
                    included_text,
                    include_path,
                    (*stack, include_identity),
                )
                if expanded and not expanded.endswith(("\n", "\r")):
                    expanded += "\n"
                return (
                    f"<!-- include: {reference} -->\n"
                    f"{expanded}"
                    f"<!-- /include: {reference} -->"
                )

            plan_non_qmd(reference, containing_file, "Quarto include")

            return match.group(0)

        return INCLUDE_RE.sub(replace, text)

    source_identity = source.resolve(strict=True)
    rendered_text = expand(
        decode_qmd(source),
        source,
        (source_identity,),
    )
    for reference, kind in render_file_references(rendered_text):
        plan_non_qmd(reference, source, kind)
    return ExpansionPlan(
        source=source,
        target=target,
        rendered=rendered_text.encode("utf-8"),
        qmd_inlines=qmd_inlines,
        non_qmd_copies=sorted(
            planned_copies.values(),
            key=lambda item: os.fspath(item.destination),
        ),
    )


def lexists(path: Path) -> bool:
    return os.path.lexists(path)


def parent_blocker(path: Path) -> Path | None:
    current = path.parent
    while True:
        if lexists(current):
            return None if current.is_dir() else current
        if current == current.parent:
            return None
        current = current.parent


def preflight_outputs(plan: ExpansionPlan, force: bool) -> None:
    outputs: list[tuple[Path, str]] = [(plan.target, "main target")]
    outputs.extend(
        (
            copy.destination,
            f"non-QMD include {copy.reference} [{copy.kind}]",
        )
        for copy in plan.non_qmd_copies
    )

    invalid: list[tuple[Path, str]] = []
    conflicts: list[tuple[Path, str]] = []
    for path, description in outputs:
        blocker = parent_blocker(path)
        if blocker is not None:
            invalid.append(
                (path, f"{description}; parent path is not a directory: {blocker}")
            )
            continue
        if not lexists(path):
            continue
        if path.is_dir():
            invalid.append((path, f"{description}; output path is a directory"))
        else:
            conflicts.append((path, description))

    if invalid:
        lines = ["Invalid output paths:"]
        lines.extend(
            f"  {path} ({description})"
            for path, description in sorted(invalid, key=lambda item: str(item[0]))
        )
        lines.append("Error: no files were written.")
        raise PlanError("\n".join(lines))

    if conflicts and not force:
        lines = ["Conflicting output files:"]
        lines.extend(
            f"  {path} ({description})"
            for path, description in sorted(
                conflicts, key=lambda item: str(item[0])
            )
        )
        lines.extend(
            [
                "Error: refusing to overwrite existing output files; no files "
                "were written.",
                "Re-run with --force to overwrite the listed outputs.",
            ]
        )
        raise PlanError("\n".join(lines))


def stage_bytes(destination: Path, content: bytes, mode: int) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        return temporary
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def stage_copy(copy: NonQmdCopy) -> Path:
    copy.destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{copy.destination.name}.",
        suffix=".tmp",
        dir=copy.destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(copy.source, temporary)
        return temporary
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def write_plan(plan: ExpansionPlan) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        source_mode = stat.S_IMODE(plan.source.stat().st_mode)
        staged.append(
            (plan.target, stage_bytes(plan.target, plan.rendered, source_mode))
        )
        for copy in plan.non_qmd_copies:
            staged.append((copy.destination, stage_copy(copy)))

        for destination, temporary in staged:
            os.replace(temporary, destination)
    finally:
        for _, temporary in staged:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Copy a source QMD to a target, recursively inline QMD include "
            "shortcodes, and copy non-QMD includes when the directories differ."
        ),
        epilog=(
            "Example: inline_qmd_includes.py source.qmd public/source.qmd\n"
            "Use --force to replace an existing target or copied include."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="source .qmd file")
    parser.add_argument("target", type=Path, help="target .qmd file")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the target and copied non-QMD include outputs",
    )
    return parser


def main() -> int:
    parser = argument_parser()
    arguments = parser.parse_args()
    try:
        plan = build_plan(arguments.source, arguments.target)
        preflight_outputs(plan, arguments.force)
        write_plan(plan)
    except PlanError as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error while writing outputs: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote target: {plan.target}")
    print(f"Inlined QMD include files ({len(plan.qmd_inlines)} occurrences):")
    if plan.qmd_inlines:
        for inline in plan.qmd_inlines:
            print(
                f"  {inline.source} "
                f"(marker: {inline.reference}; included by: {inline.containing_file})"
            )
    else:
        print("  (none)")
    print(f"Copied non-QMD include files ({len(plan.non_qmd_copies)}):")
    if plan.non_qmd_copies:
        for copy in plan.non_qmd_copies:
            print(
                f"  {copy.source} -> {copy.destination} "
                f"[{copy.kind}; reference: {copy.reference}]"
            )
    else:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
