"""Command-line validators for autobuild documents.

    autobuild check                         self-check the core (schemas, policy, examples)
    autobuild config [PROJECT]              validate PROJECT/.autobuild/config.yaml
    autobuild brief FILE...                 validate implementation briefs
    autobuild state FILE [--project DIR]    validate a run state (config rules with --project)
    autobuild review FILE...                validate review results
    autobuild validation FILE...            validate validation results
    autobuild gate FILE [--done ID,...]     show the autonomy gate decision for a brief
    autobuild agents [PROJECT]              show which provider fills each role
    autobuild run BRIEF [--project DIR] [--base BRANCH] [--yes] [--dry-run]
                                            implement, validate and independently review one brief
    autobuild resume RUN [--project DIR] [--dry-run]
                                            explicitly continue a preserved recoverable run
    autobuild fixture create --implementer ID [--name NAME]   disposable live-test fixture
    autobuild fixture list                                    fixtures and ownership checks
    autobuild fixture clean [NAME...|--all] [--legacy PATH...] [--yes]
                                            remove verified fixtures (dry run without --yes)

Exit status is 0 when everything validates, 1 otherwise.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Optional

from autobuild.autonomy import evaluate_gate
from autobuild.config import ConfigError, load_project_config, missing_paths
from autobuild.implementations import brief_file_errors, load_brief
from autobuild.paths import CORE_ROOT, EXAMPLES_DIR
from autobuild.policy_loader import load_policy
from autobuild.provider_registry import load_registry
from autobuild.roles import ROLES
from autobuild.run_state_checks import run_state_errors
from autobuild.schemas import SCHEMA_NAMES, load_schema, schema_errors
from autobuild.states import RunState


def _report(label: str, errors: list[str]) -> bool:
    if errors:
        print(f"FAIL {label}")
        for error in errors:
            print(f"  - {error}")
        return False
    print(f"OK   {label}")
    return True


def _json_file_errors(schema: str, path: Path) -> list[str]:
    try:
        return schema_errors(schema, json.loads(path.read_text()))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]


def _check_core() -> bool:
    """Schemas compile, policy agrees with schema enums, and every example validates."""
    ok = True
    for name in SCHEMA_NAMES:
        ok &= _report(f"schema {name}", [] if load_schema(name) else ["empty schema"])

    classes = set(load_policy("autonomy")["classes"])
    schema_classes = set(load_schema("implementation")["properties"]["autonomy"]["enum"])
    ok &= _report("policy autonomy classes match schema",
                  [] if classes == schema_classes else [f"policy {sorted(classes)} vs schema {sorted(schema_classes)}"])

    safety = load_policy("safety")
    overlap = sorted(set(safety["allowed"]) & set(safety["prohibited"]))
    ok &= _report("policy safety lists are disjoint", [f"in both lists: {', '.join(overlap)}"] if overlap else [])

    states = {s.value for s in RunState}
    schema_states = set(load_schema("run-state")["properties"]["state"]["enum"])
    ok &= _report("run states match schema",
                  [] if states == schema_states else [f"code {sorted(states)} vs schema {sorted(schema_states)}"])

    bad_roles = sorted({r for p in load_registry()["providers"].values() for r in p["roles"]} - set(ROLES))
    ok &= _report("provider registry roles are known", [f"unknown roles: {', '.join(bad_roles)}"] if bad_roles else [])

    for brief in sorted((EXAMPLES_DIR / "implementations").glob("*.md")):
        ok &= _report(f"example {brief.name}", brief_file_errors(brief))
    ok &= _report("example run-state.json", run_state_errors(json.loads((EXAMPLES_DIR / "run-state.json").read_text())))
    for review in sorted(EXAMPLES_DIR.glob("review-*.json")):
        ok &= _report(f"example {review.name}", _json_file_errors("review", review))
    ok &= _report("example validation.json", _json_file_errors("validation", EXAMPLES_DIR / "validation.json"))
    return ok


def _check_config(project: Path) -> bool:
    try:
        config = load_project_config(project)
    except ConfigError as exc:
        return _report(str(exc.path), exc.errors)
    ok = _report(str(project / ".autobuild/config.yaml"), [])
    for warning in missing_paths(config):
        print(f"WARN {warning} does not exist yet")
    return ok


def _check_state(path: Path, project: Path | None) -> bool:
    config = None
    if project is not None:
        try:
            config = load_project_config(project)
        except ConfigError as exc:
            return _report(str(exc.path), exc.errors)
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return _report(str(path), [f"invalid JSON: {exc}"])
    return _report(str(path), run_state_errors(state, config))


def _check_each(paths: list[Path], errors_for: Callable[[Path], list[str]]) -> bool:
    ok = True
    for path in paths:
        ok &= _report(str(path), errors_for(path))
    return ok


def _show_agents(project: Path) -> bool:
    try:
        config = load_project_config(project)
    except ConfigError as exc:
        return _report(str(exc.path), exc.errors)
    for role, a in config.agents.items():
        model = f", model {a.model}" if a.model else ""
        print(f"{role:<12} {a.display_name} ({a.provider}; command {a.command}{model})")
    return True


def _run(brief: Path, project: Optional[Path], base: Optional[str], assume_yes: bool, dry_run: bool) -> int:
    from autobuild.git_client import GitClient
    from autobuild.preflight import PreflightError, preflight
    from autobuild.runner import Runner

    root = project or GitClient(Path.cwd(), ()).toplevel(Path.cwd()) or Path.cwd()
    try:
        plan = preflight(brief, root, base_branch=base)
    except PreflightError as exc:
        print("Autobuild did not start.")
        for issue in exc.issues:
            print(f"  - {issue}")
        print("No branch or worktree was modified.")
        return 1
    commands = ", ".join(f"{c['name']} ({c['kind']})" for c in plan.validation_commands) or "none configured"
    print(f"Implementation: {plan.meta['id']} — {plan.meta['title']}")
    print(f"Autonomy: {plan.meta['autonomy'].upper()}")
    print(f"Implementer: {plan.assignment.provider} ({plan.assignment.display_name}, {plan.health.version or 'version unknown'})")
    print(f"Reviewer: {plan.reviewer_assignment.provider} (fresh session each cycle)")
    print(f"Base branch: {plan.base_branch} @ {plan.base_commit[:12]}")
    print(f"Target branch: {plan.branch}")
    print(f"Worktree: {plan.worktree}")
    print(f"Run artifacts: {plan.run_dir}")
    print(f"Validation: {commands}")
    print(f"Checkpoint commit: {'enabled' if plan.checkpoint_commits else 'disabled'}")
    for warning in plan.warnings:
        print(f"Warning: {warning}")
    if dry_run:
        print("Dry run: preflight passed; nothing was created.")
        return 0
    if not assume_yes and sys.stdin.isatty():
        if input("Start this run? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Not started. No branch or worktree was modified.")
            return 1
    outcome = Runner(plan).run()
    print()
    print(outcome.report, end="")
    return 0 if outcome.state["state"] == "COMPLETED" else 1


def _resume(run: Path, project: Optional[Path], dry_run: bool) -> int:
    from autobuild.git_client import GitClient
    from autobuild.preflight import PreflightError
    from autobuild.resume import resume_preflight
    from autobuild.runner import Runner

    root = project or GitClient(Path.cwd(), ()).toplevel(Path.cwd()) or Path.cwd()
    try:
        plan = resume_preflight(run, root)
    except PreflightError as exc:
        print("Autobuild did not resume. No branch or worktree was modified.")
        for issue in exc.issues:
            print(f"  - {issue}")
        return 1
    if dry_run:
        print(f"Resume preflight passed for {plan.run_id}; nothing was modified.")
        return 0
    outcome = Runner(plan).run()
    print(outcome.report, end="")
    return 0 if outcome.state["state"] == "COMPLETED" else 1


def _fixture(args: argparse.Namespace) -> int:
    from autobuild import fixtures

    root = fixtures.runtime_root()
    if args.action == "create":
        try:
            path = fixtures.create_fixture(implementer=args.implementer, name=args.name)
        except fixtures.FixtureError as exc:
            print(f"FAIL {exc}")
            return 1
        print(f"Created fixture {path}")
        print(f"  cd {path} && {CORE_ROOT / 'bin' / 'autobuild'} run docs/roadmap/V-1.md --dry-run")
        return 0
    if args.action == "list":
        found = fixtures.list_fixtures()
        print(f"Runtime root: {root}" + ("" if found else " (no fixtures)"))
        for target in found:
            state = "owned" if target.safe else "UNVERIFIED: " + "; ".join(target.problems)
            print(f"  {target.path.name}: {len(target.worktrees)} worktree(s), {state}")
        return 0

    targets = [fixtures.inspect_legacy(Path(p)) for p in args.legacy]
    if args.all:
        targets += fixtures.list_fixtures()
    targets += [fixtures.inspect_fixture(name) for name in args.names]
    if not targets:
        print("Nothing selected: name fixtures, or pass --all or --legacy PATH.")
        return 1
    ok = True
    for target in targets:
        if not target.safe:
            ok = False
            print(f"SKIP {target.path}: " + "; ".join(target.problems))
            continue
        items = [target.path, *target.worktrees] + ([target.worktrees_dir] if target.worktrees_dir.exists() else [])
        if args.yes:
            fixtures.remove(target)
            print(f"REMOVED {target.path} (+{len(target.worktrees)} worktree(s))")
        else:
            print("WOULD REMOVE " + ", ".join(str(i) for i in items))
    if not args.yes:
        print("Dry run: nothing was deleted. Re-run with --yes to remove the verified fixtures above.")
    return 0 if ok else 1


def _show_gate(path: Path, done: str) -> bool:
    errors = brief_file_errors(path)
    if errors:
        return _report(str(path), errors)
    meta, _ = load_brief(path)
    decision = evaluate_gate(meta, [d for d in done.split(",") if d])
    print(f"{decision.implementation_id}: {decision.action.upper()} "
          f"(autonomy {decision.autonomy}, execution {decision.execution})")
    for reason in decision.reasons:
        print(f"  - {reason}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autobuild", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    p = sub.add_parser("config")
    p.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    p = sub.add_parser("brief")
    p.add_argument("files", nargs="+", type=Path)
    p = sub.add_parser("state")
    p.add_argument("file", type=Path)
    p.add_argument("--project", type=Path)
    for name in ("review", "validation"):
        p = sub.add_parser(name)
        p.add_argument("files", nargs="+", type=Path)
    p = sub.add_parser("gate")
    p.add_argument("file", type=Path)
    p.add_argument("--done", default="", help="comma-separated ids of completed implementations")
    p = sub.add_parser("run")
    p.add_argument("brief", type=Path)
    p.add_argument("--project", type=Path, help="project root (default: git top level of the current directory)")
    p.add_argument("--base", help="branch to start from (default: git.default_base_branch or the first protected branch)")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.add_argument("--dry-run", action="store_true", help="run preflight only")
    p = sub.add_parser("resume")
    p.add_argument("run", type=Path)
    p.add_argument("--project", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("fixture")
    fixture_sub = p.add_subparsers(dest="action", required=True)
    f = fixture_sub.add_parser("create")
    f.add_argument("--implementer", required=True, help="registry provider id to assign to every role")
    f.add_argument("--name")
    fixture_sub.add_parser("list")
    f = fixture_sub.add_parser("clean")
    f.add_argument("names", nargs="*", help="fixture names under the runtime root")
    f.add_argument("--all", action="store_true", help="every fixture under the runtime root")
    f.add_argument("--legacy", nargs="+", default=[], metavar="PATH", help="pre-runtime fixture folders (strict signature check)")
    f.add_argument("--yes", action="store_true", help="actually delete (default is a dry run)")
    p = sub.add_parser("agents")
    p.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    if args.command == "fixture":
        return _fixture(args)
    if args.command == "run":
        return _run(args.brief, args.project, args.base, args.yes, args.dry_run)
    if args.command == "resume":
        return _resume(args.run, args.project, args.dry_run)
    if args.command == "check":
        ok = _check_core()
    elif args.command == "config":
        ok = _check_config(args.project)
    elif args.command == "brief":
        ok = _check_each(args.files, brief_file_errors)
    elif args.command == "state":
        ok = _check_state(args.file, args.project)
    elif args.command in ("review", "validation"):
        ok = _check_each(args.files, lambda path: _json_file_errors(args.command, path))
    elif args.command == "agents":
        ok = _show_agents(args.project)
    else:
        ok = _show_gate(args.file, args.done)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
