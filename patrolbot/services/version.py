"""patrolbot version / git information helper."""
from __future__ import annotations

import subprocess
import os

_APP_VERSION = '1.0'

def _run(cmd: list[str]) -> str:
    """Run a git command and return stripped stdout, or '' on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.stdout.strip() if result.returncode == 0 else ''
    except Exception:
        return ''


def get_version_info() -> dict:
    """Return a dict with app version + git metadata (best-effort)."""
    commit = _run(['git', 'rev-parse', '--short', 'HEAD'])
    branch = _run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    tag = _run(['git', 'describe', '--tags', '--abbrev=0'])
    commit_date = _run(['git', 'log', '-1', '--format=%ci'])
    commit_msg = _run(['git', 'log', '-1', '--format=%s'])
    dirty = _run(['git', 'status', '--porcelain'])

    return {
        'app_version': _APP_VERSION,
        'git_commit': commit or None,
        'git_branch': branch or None,
        'git_tag': tag or None,
        'git_commit_date': commit_date or None,
        'git_commit_message': commit_msg or None,
        'git_dirty': bool(dirty),
        'version_string': _build_version_string(commit, branch, tag, dirty),
    }


def _build_version_string(commit: str, branch: str, tag: str, dirty: str) -> str:
    parts = [_APP_VERSION]
    if tag and tag != _APP_VERSION:
        parts = [tag]
    if branch and branch not in ('HEAD', 'main', 'master'):
        parts.append(f'({branch})')
    if commit:
        suffix = f'{commit}{"*" if dirty else ""}'
        parts.append(f'@{suffix}')
    return ' '.join(parts)
