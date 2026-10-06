#!/usr/bin/env python3
"""Lightweight manual completion evidence; never stages, commits or repairs.

Reuse Autobuild validation and filename safety checks without entering its controller.
Evidence is task-local; documentation applicability remains an agent assertion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'autobuild'))
from autobuild.policy.secret_files import secret_like

AREAS = ('changelog', 'project_state', 'evaluation_results', 'known_limitations',
         'architectural_decisions', 'implementation_documentation')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)


def snapshot(root):
    """Capture porcelain records, including rename sources, without printing content."""
    raw = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    tokens = raw.decode(errors='surrogateescape').split('\0')
    rows = []
    i = 0
    while i < len(tokens) and tokens[i]:
        token = tokens[i]
        row = {'status': token[:2], 'path': token[3:]}
        i += 1
        if 'R' in row['status'] or 'C' in row['status']:
            row['source'] = tokens[i]
            i += 1
        rows.append(row)
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'], capture_output=True)
    digest = hashlib.sha256(head.stdout + raw)
    for row in rows:
        path = root / row['path']
        digest.update(row['path'].encode(errors='surrogateescape'))
        if path.is_symlink():
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
    digest.update(git(root, 'diff', '--cached', '--binary'))
    return {'files': rows, 'fingerprint': digest.hexdigest()}


def evaluate(root, evidence, reconciliation, commands, run=False):
    if commands:
        # Reuse the existing command schema, including safe log names and cwd paths.
        from jsonschema import Draft7Validator
        schema = json.loads((Path(__file__).resolve().parents[2] / 'autobuild/schemas/config.schema.json').read_text())
        command_schema = {'$defs': schema['$defs'], 'type': 'array',
                          'items': {'$ref': '#/$defs/validation_command'}}
        if list(Draft7Validator(command_schema).iter_errors(commands)):
            raise ValueError('invalid validation command specs')
        if len({spec['name'] for spec in commands}) != len(commands):
            raise ValueError('duplicate validation command names')
    state = snapshot(root)
    issues = []
    paths = [row['path'] for row in state['files']]
    unsafe = secret_like([row['path'] for row in state['files'] if row['status'] != ' D' and row['status'] != 'D '])
    if unsafe:
        issues.append('secret-like files: ' + ', '.join(unsafe))
    if any(row['status'] in ('DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU') for row in state['files']):
        issues.append('unresolved Git conflicts')
    gitdir = Path(git(root, 'rev-parse', '--absolute-git-dir').decode().strip())
    if any((gitdir / name).exists() for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')):
        issues.append('Git operation in progress')
    if reconciliation.get('fingerprint') != state['fingerprint']:
        issues.append('documentation reconciliation missing or stale')
    for area in AREAS:
        item = reconciliation.get('documentation', {}).get(area, {})
        if item.get('status') not in ('updated', 'not_applicable') or not item.get('reason'):
            issues.append('reconcile documentation: ' + area)
        if item.get('status') == 'updated' and not any(p in paths for p in item.get('paths', [])):
            issues.append('no changed documentation evidence: ' + area)
    # Applicability is semantic; treating every non-document path as executable is conservative.
    executable = any(Path(p).suffix.lower() not in ('.md', '.rst', '.txt') for p in paths)
    exemption = reconciliation.get('validation_not_applicable')
    exemption = isinstance(exemption, str) and bool(exemption.strip())
    if executable and not commands and not exemption:
        issues.append('declare applicable validation commands or explain non-executable changes')
    if executable and commands:
        required = {spec['name'] for spec in commands if spec.get('required', True)}
        for kind in ('test', 'typecheck', 'lint', 'build', 'runtime'):
            scope = reconciliation.get('validation_scope', {}).get(kind, {})
            names = scope.get('commands', [])
            if not (names and all(name in required for name in names)) and not scope.get('not_applicable'):
                issues.append('reconcile validation applicability: ' + kind)
    if run and commands and not unsafe:
        from autobuild.validation.validation_runner import run_validation
        before = state['fingerprint']
        outcome = run_validation(run_id='manual', commands=commands, project_root=root,
                                 worktree=root, changed_files=paths, run_dir=evidence.parent, manual_host=True)
        outcome.document['producer'] = 'manual'
        record = {'root': str(root), 'fingerprint': before, 'commands_config': commands,
                  'validation': outcome.document}
        evidence.write_text(json.dumps(record, indent=2) + '\n')
        if snapshot(root)['fingerprint'] != before:
            issues.append('validation changed repository; reconcile and rerun')
    record = json.loads(evidence.read_text()) if evidence.exists() else {}
    if commands:
        if record.get('root') != str(root) or record.get('fingerprint') != state['fingerprint'] or record.get('commands_config') != commands:
            issues.append('required validation missing or stale')
        else:
            for result in record['validation']['commands']:
                if result['required'] and result['status'] not in ('PASS', 'SKIPPED'):
                    issues.append('required validation did not pass: ' + result['name'])
    expected = reconciliation.get('expected_paths', [])
    unexpected = sorted(set(paths) - set(expected))
    if unexpected:
        issues.append('unacknowledged changed files: ' + ', '.join(unexpected))
    return {'status': 'NEEDS_ATTENTION' if issues else 'PASS', **state, 'issues': issues,
            'validation': record.get('validation'),
            'commit_recommendation_required': bool(paths) and not reconciliation.get('human_requested_commit', False),
            'commit_policy': '~/.agents/GIT.md'}


def main():
    if os.environ.get('AUTOBUILD_RUN_ID') or os.environ.get('AUTOBUILD_WORKTREE'):
        print(json.dumps({'status': 'SKIP', 'reason': 'Autobuild owns completion'}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--reconciliation', type=Path)
    parser.add_argument('--commands', type=Path, help='JSON list of existing validation command specs')
    parser.add_argument('--run-validation', action='store_true')
    args = parser.parse_args()
    try:
        root = Path(git(args.root, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
        if args.snapshot:
            result = snapshot(root)
        else:
            if not args.evidence or not args.reconciliation:
                parser.error('--evidence and --reconciliation are required for completion')
            commands = json.loads(args.commands.read_text()) if args.commands else []
            result = evaluate(root, args.evidence, json.loads(args.reconciliation.read_text()), commands, args.run_validation)
        print(json.dumps(result, indent=2))
        return int(result.get('status') == 'NEEDS_ATTENTION')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'NEEDS_ATTENTION', 'issues': [type(exc).__name__ + ': invalid or unavailable completion evidence']}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
