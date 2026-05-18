from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    message: str
    source: str  # classifier: inline_comment | ruff


@dataclass
class ScanReport:
    root: str
    findings: list[Finding] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "findings": [
                {
                    "path": f.path,
                    "line": f.line,
                    "rule": f.rule,
                    "message": f.message,
                    "source": f.source,
                }
                for f in self.findings
            ],
        }


@dataclass
class TaskBrief:
    id: str
    title: str
    description: str
    related_files: list[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class OrchestrationOutcome:
    tasks: list[TaskBrief]
    coder_outputs: dict[str, str]
    reviewer_outputs: dict[str, str]

