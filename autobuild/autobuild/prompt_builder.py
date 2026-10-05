"""Assemble the implementer prompt from the approved brief and run context.

The prompt carries the brief, the worktree rules, pointers to policies and
project docs, the validation the controller will run, and the required
completion output. It deliberately carries no prior agent conversation.
"""

import re
from pathlib import Path
from string import Template
from typing import Any, Sequence

from autobuild.paths import TEMPLATE_DIR

_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
GLOBAL_POLICY_DIR = Path("~/.agents")


def _validation_lines(commands: Sequence[dict[str, Any]]) -> str:
    if not commands:
        return "- (none configured — the run will rely on review)"
    lines = []
    for spec in commands:
        where = f" (in `{spec['cwd']}`)" if spec.get("cwd") else ""
        scope = f"; only when files matching {', '.join(spec['paths'])} change" if spec.get("paths") else ""
        display = spec.get("display") or spec.get("command") or spec.get("run")
        rendered = " ".join(display) if isinstance(display, list) else display
        lines.append(f"- {spec['name']} [{spec['kind']}]: `{rendered}`{where}{scope}")
    return "\n".join(lines)


def build_prompt(
    *,
    brief_text: str,
    worktree: Path,
    branch: str,
    base_branch: str,
    base_commit: str,
    project_docs: Sequence[str],
    validation_commands: Sequence[dict[str, Any]],
) -> str:
    """Render templates/implementer-prompt.md. Validation commands are shown already substituted."""
    template = _LEADING_COMMENT.sub("", (TEMPLATE_DIR / "implementer-prompt.md").read_text())
    return Template(template).substitute(
        worktree=worktree,
        branch=branch,
        base_branch=base_branch,
        base_commit=base_commit[:12],
        policies=f"`{GLOBAL_POLICY_DIR}/*.md` (CODING, DOCUMENTATION, EXECUTION, GIT, SECURITY, VERIFICATION)",
        project_docs=", ".join(f"`{d}`" for d in project_docs) or "the repository docs",
        validation_commands=_validation_lines(validation_commands),
        brief=brief_text.strip(),
    )
