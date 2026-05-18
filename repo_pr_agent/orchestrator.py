from __future__ import annotations

import json
import textwrap
from pathlib import Path
from .llm import ChatBackend
from .models import Finding, TaskBrief


MAX_FINDINGS_SENT = 200
SNIPPET_BUDGET = 3200

def load_scan(path: Path) -> tuple[list[Finding], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    root = str(data.get("root") or ".")
    raw = data.get("findings") or []
    findings: list[Finding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        findings.append(
            Finding(
                path=str(item.get("path") or ""),
                line=int(item.get("line") or 0),
                rule=str(item.get("rule") or ""),
                message=str(item.get("message") or ""),
                source=str(item.get("source") or "unknown"),
            )
        )
    return findings, root


def _finding_block(findings: list[Finding]) -> str:
    lines: list[str] = []
    for f in findings[:MAX_FINDINGS_SENT]:
        lines.append(f"- `{f.path}`:{f.line} [{f.rule}] ({f.source}) {f.message}")
    if len(findings) > MAX_FINDINGS_SENT:
        lines.append(f"\n...(其余 {len(findings) - MAX_FINDINGS_SENT} 条省略)")
    return "\n".join(lines) if lines else "(无发现)"


def _read_file_snippets(repo: Path, rel_paths: list[str], budget: int = 3200) -> dict[str, str]:
    chunks: dict[str, str] = {}
    seen: set[str] = set()
    for raw in rel_paths:
        rp = Path(raw.strip())
        if not str(rp):
            continue
        key = rp.as_posix()
        if key in seen:
            continue
        seen.add(key)
        fp = repo / rp
        if not fp.is_file():
            chunks[key] = f"(文件不存在: {key})\n"
            continue
        try:
            txt = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            chunks[key] = f"(读取失败: {key})\n"
            continue
        total = len(txt)
        if len(txt) > budget:
            txt = txt[:budget] + f"\n... [truncated, 原始长度 {total} 字符]\n"
        chunks[key] = txt
    return chunks


SYSTEM_PLANNER = """你是资深交付负责人，任务是把代码仓库体检结果转成可执行任务图。
你只输出严格的 JSON（不要 Markdown 围栏）。顶层键：summary（中文一段）、tasks（数组）。
每个 task 必须有：id, title, description, related_files（字符串数组，仓库相对 POSIX 路径）, priority(high|medium|low)。
任务要少而精（建议 5 个以内），优先处理安全、正确性、可维护性。"""
SYSTEM_CODER = """你是高级工程师。根据给定任务体检上下文与源码片段，提出可应用的修改方案。
必须用中文简述思路，再给 unified diff（git patch 语法）。如果只改一两个文件就只包含这些文件的 diff。
不要编造不存在的文件名。若上下文不足则说明无法给出安全补丁并列出需要的信息。"""

SYSTEM_REVIEWER = """你是代码评审。检查 proposed_patch 是否合理、是否与任务一致、是否存在明显风险。
用中文分段输出：1) verdict: approve/request_changes/block 选一 ；2) 具体意见列表；3) 若 request_changes，给出最关键的修改方向。"""


def planner_parse(raw: str) -> tuple[str, list[TaskBrief]]:
    payload = json.loads(raw)
    summary = str(payload.get("summary") or "")
    tasks_out: list[TaskBrief] = []
    tasks = payload.get("tasks") or []
    if not isinstance(tasks, list):
        return summary, tasks_out
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip() or "T?"
        titles = str(t.get("title") or "").strip()
        desc = str(t.get("description") or "").strip()
        rel = t.get("related_files") or []
        rf: list[str] = []
        if isinstance(rel, list):
            rf = [str(x) for x in rel if str(x)]
        pr = str(t.get("priority") or "medium")
        tasks_out.append(
            TaskBrief(id=tid, title=titles or tid, description=desc, related_files=rf, priority=pr)
        )
    return summary, tasks_out


def orchestrate(
    *,
    repo_root: Path,
    findings: list[Finding],
    max_tasks: int,
    backend: ChatBackend | None,
    dry_run: bool = False,
) -> tuple[str, dict[str, str]]:
    if dry_run:
        lines = ["## [dry-run] 未调用大模型。", _finding_block(findings[:20])]
        return "\n".join(lines), {"planner_raw": "{}"}

    assert backend is not None
    planner_user = (
        "以下是仓库体检条目，请产出任务分解 JSON。\n\n" + _finding_block(findings)
    )
    plan_raw = backend.complete(SYSTEM_PLANNER, planner_user, json_mode=True, max_completion_tokens=4096)

    try:
        summary, tasks = planner_parse(plan_raw)
    except json.JSONDecodeError:
        fallback = "```text\n" + plan_raw.strip()[:12000] + "\n```\n"
        return (
            "# Repo-PR-Agent / Planner JSON 无效\n输出不是合法 JSON，请调整模型名称或调高输出上限。\n\n"
            + fallback,
            {"planner_raw": plan_raw},
        )

    tasks_sel = sorted(
        tasks,
        key=lambda t: {"high": 0, "medium": 1, "low": 2}.get(t.priority.lower(), 1),
    )[: max(1, max_tasks)]

    if not tasks_sel and findings:
        top_files: list[str] = []
        for fid in findings:
            if fid.path and fid.path not in top_files:
                top_files.append(fid.path)
            if len(top_files) >= 5:
                break
        tasks_sel = [
            TaskBrief(
                id="T_fallback",
                title="基于体检条目生成首轮补丁草案",
                description="Planner 未返回任务；使用扫描中出现的文件上下文继续 Coder→Reviewer。",
                related_files=top_files,
                priority="high",
            )
        ]

    if not tasks_sel:
        return (
            "# Repo-PR-Agent\n\n未发现可执行任务（体检条目为空）。\n\n"
            "```json\n" + plan_raw.strip() + "\n```\n",
            {"planner_raw": plan_raw},
        )

    coder_out: dict[str, str] = {}
    reviewer_out: dict[str, str] = {}

    for task in tasks_sel:
        paths: list[str] = []
        for rp in task.related_files:
            if rp and rp not in paths:
                paths.append(rp)
        if not paths:
            for fid in findings:
                if fid.path and fid.path not in paths:
                    paths.append(fid.path)
                if len(paths) >= 10:
                    break
        snippets = _read_file_snippets(repo_root, paths, budget=SNIPPET_BUDGET)
        snippets_fmt = ""
        for p, txt in snippets.items():
            snippets_fmt += f"\n----- FILE {p}\n{txt}"

        coder_user = textwrap.dedent(
            f"""
            任务 {task.id}：{task.title}
            说明：{task.description}
            priority：{task.priority}

            相关源码片段：
            {snippets_fmt}
            """
        ).strip()

        coder_text = backend.complete(SYSTEM_CODER, coder_user, json_mode=False, max_completion_tokens=8192)
        coder_out[task.id] = coder_text

        rev_user = textwrap.dedent(
            f"""
            对应任务：
            id={task.id}
            title={task.title}
            description={task.description}

            Agent 补丁提案：
            {coder_text}
            """
        ).strip()
        reviewer_text = backend.complete(SYSTEM_REVIEWER, rev_user, json_mode=False, max_completion_tokens=4096)
        reviewer_out[task.id] = reviewer_text

    md = _render_md(summary, plan_raw, tasks_sel, coder_out, reviewer_out)
    return md, {"planner_raw": plan_raw}


def _render_md(
    summary: str,
    planner_raw: str,
    tasks: list[TaskBrief],
    coder: dict[str, str],
    reviewer: dict[str, str],
) -> str:
    parts: list[str] = []
    parts.append("# Repo-PR-Agent · 流水线报告")
    parts.append("")
    parts.append("## Planner 概要")
    parts.append(summary.strip() or "（未返回 summary）")
    parts.append("")
    parts.append("## 执行任务（截取）")
    for t in tasks:
        parts.append(f"- **{t.id}** [{t.priority}] {t.title} — 关联文件：`{','.join(t.related_files) or '—'}`")
    parts.append("")
    parts.append("## Planner JSON（原文）")
    parts.append("\n```json\n" + planner_raw.strip() + "\n```\n")

    for t in tasks:
        parts.append(f"## 任务 `{t.id}`")
        parts.append(f"### 描述\n{t.description}\n")
        parts.append("### Coder 输出\n```text\n" + (coder.get(t.id) or "(无)") + "\n```\n")
        parts.append("### Reviewer 输出\n```text\n" + (reviewer.get(t.id) or "(无)") + "\n```\n")

    return "\n".join(parts).strip() + "\n"
