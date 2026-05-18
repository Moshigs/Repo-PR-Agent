from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .models import Finding, ScanReport

LINE_TODO_RE = re.compile(
    r"^[ \t]*(?:#|//|--)\s*(TODO|FIXME|HACK|XXX)\b\s*[:\.]?\s*(.*?)\s*$",
    re.IGNORECASE,
)

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
}

CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".vue",
    ".sql",
    ".yaml",
    ".yml",
    ".swift",
}


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            if p.name in IGNORE_DIRS:
                continue
        if not p.is_file():
            continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        suf = p.suffix.lower()
        if suf not in CODE_SUFFIXES:
            continue
        try:
            if p.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        out.append(p)
    return sorted(out)


def _scan_todo_comments(rel: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = LINE_TODO_RE.match(line)
        if not m:
            continue
        tag = m.group(1).upper()
        tail = (m.group(2) or "").strip()[:280]
        findings.append(
            Finding(
                path=rel.as_posix(),
                line=line_no,
                rule=tag,
                message=tail or "(无说明)",
                source="todo_tag",
            )
        )
    return findings


def _repo_rel(repo: Path, raw: str) -> str:
    p = Path(raw)
    try:
        if p.is_absolute():
            return p.relative_to(repo).as_posix()
    except ValueError:
        pass
    return p.as_posix()


def _run_ruff_json(root: Path) -> list[Finding]:
    if not shutil.which("ruff"):
        return []
    try:
        proc = subprocess.run(
            ["ruff", "check", str(root), "--output-format=json", "--exit-zero"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[Finding] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        code = str(it.get("code") or "RUFF")
        msg = str(it.get("message") or "")
        fname = str(it.get("filename") or "")
        loc = it.get("location") or {}
        line = int(loc.get("row") or 0)
        out.append(
            Finding(path=_repo_rel(root, fname), line=line, rule=code, message=msg, source="ruff")
        )
    return out


def scan_repository(root: str | Path) -> ScanReport:
    root_path = Path(root).resolve()
    report = ScanReport(root=str(root_path))
    findings: list[Finding] = []

    for fp in _iter_files(root_path):
        try:
            txt = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = fp.relative_to(root_path)
        findings.extend(_scan_todo_comments(rel, txt))

    findings.extend(_run_ruff_json(root_path))
    findings.sort(key=lambda f: (f.path, f.line, f.rule))
    report.findings = findings
    return report
