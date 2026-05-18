from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv


def cmd_scan(ns: argparse.Namespace) -> int:
    from .scanner import scan_repository

    root = Path(ns.root).resolve()
    repo = scan_repository(root)
    out_payload = repo.to_json_dict()
    js = json.dumps(out_payload, ensure_ascii=False, indent=2)
    if ns.stdout:
        print(js)
    else:
        outp = Path(ns.out).resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(js + "\n", encoding="utf-8")
        print(f"[scan] 写入 {outp}，共 {len(repo.findings)} 条条目。")
    return 0


def cmd_run(ns: argparse.Namespace) -> int:
    from .llm import ChatBackend
    from .orchestrator import load_scan, orchestrate

    repo_root = Path(ns.root).resolve()
    scan_path = Path(ns.scan).resolve()

    findings, _scan_recorded_root = load_scan(scan_path)

    backend = None
    if not ns.dry_run:
        backend = ChatBackend(model=ns.model)

    md, meta = orchestrate(
        repo_root=repo_root,
        findings=findings,
        max_tasks=ns.max_tasks,
        backend=backend,
        dry_run=bool(ns.dry_run),
    )
    outp = Path(ns.report).resolve()
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(md, encoding="utf-8")
    print(f"[run] 报告写入 {outp}")
    meta_path = outp.with_suffix(".planner_meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="repo_pr_agent",
        description="Repository scan plus Planner/Coder/Reviewer draft patch pipeline.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="递归扫描源码，输出体检 JSON（TODO/FIXME 注释 + 可选 Ruff）")
    ps.add_argument("--root", default=".", help="仓库根路径")
    ps.add_argument(
        "--out",
        "-o",
        default="reports/scan.json",
        help="输出路径（默认 reports/scan.json）",
    )
    ps.add_argument("--stdout", action="store_true", help="写到 stdout")
    ps.set_defaults(_fn=cmd_scan)

    pr = sub.add_parser("run", help="读取 scan JSON，Planner→Coder→Reviewer，写 Markdown")
    pr.add_argument("--root", default=".", help="用于解析相对路径的文件根目录")
    pr.add_argument("--scan", required=True, help="scan JSON 路径")
    pr.add_argument("--report", default="reports/orchestration.md", help="输出 Markdown")
    pr.add_argument("--max-tasks", type=int, default=3, dest="max_tasks")
    pr.add_argument(
        "--model",
        default=None,
        help="覆盖 OPENAI_MODEL，例如 gpt-4o-mini / gpt-4o（默认读取环境变量）",
    )
    pr.add_argument(
        "--dry-run",
        action="store_true",
        help="离线运行：跳过 Chat API，输出最小报告用于自检",
    )
    pr.set_defaults(_fn=cmd_run)

    ns = parser.parse_args(argv)
    return int(ns._fn(ns))


if __name__ == "__main__":
    raise SystemExit(main())
