"""Check the exact Git content intended for publication; never echo secrets."""

import argparse
from pathlib import Path
import re
import subprocess
import sys

PUBLIC_FILES = frozenset({
    '.gitignore', '.github/workflows/test.yml',
    'LICENSE', 'README.md', 'README.en.md', 'CONTRIBUTING.md',
    'SECURITY.md', 'THIRD_PARTY_NOTICES.md',
    'LectureCapture.cmd', 'LectureCapture.pyw', 'bootstrap.py',
    'capture.cmd', 'capture.py', 'launch.pyw', 'setup.cmd',
    'requirements.txt', 'requirements.lock.txt', 'settings.example.json',
    'scripts/check_publication.py', 'tests/test_bootstrap.py',
    'tests/test_capture.py', 'tests/test_gui_layout.py', 'tests/test_resume.py',
    'tests/test_publication.py',
})

PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github-token': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'api-key': re.compile(r'\bsk-[A-Za-z0-9_-]{20,}'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url': re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    'machine-path': re.compile(r'(?i)[A-Z]:[\\/](?:Users|Workspace)[\\/]'),
    'private-ip': re.compile(r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|'
                             r'172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|'
                             r'100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2})\b'),
    'personal-email': re.compile(r'\b(?!noreply@github\.com\b)[A-Za-z0-9._%+\-]+@(?!users\.noreply\.github\.com\b|'
                                 r'example\.(?:com|org|net)\b)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
}


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise RuntimeError('Git inspection failed; check the repository and ref.')
    return result.stdout


def findings(text):
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def inspect(root, ref='HEAD', snapshot=False):
    sha = git(root, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    # Reject shallow repositories: absent history is not evidence of clean history.
    if not snapshot and git(root, 'rev-parse', '--is-shallow-repository').strip() == b'true':
        raise RuntimeError('Full history required; fetch with depth 0 or use --snapshot intentionally.')
    commits = [sha] if snapshot else git(root, 'rev-list', sha).decode().splitlines()
    issues, seen, files = [], set(), set()
    for commit in commits:
        meta = git(root, 'show', '-s', '--format=%an%n%ae%n%cn%n%ce%n%B', commit).decode('utf-8')
        for category in findings(meta):
            issues.append((commit[:8], '<commit metadata>', category))
        for entry in git(root, 'ls-tree', '-rz', commit).split(b'\0'):
            if not entry:
                continue
            header, raw_path = entry.split(b'\t', 1)
            mode, kind, blob = header.decode().split()
            path = raw_path.decode('utf-8')
            files.add(path)
            if path not in PUBLIC_FILES or mode != '100644' or kind != 'blob':
                issues.append((commit[:8], path, 'outside-public-allowlist'))
                continue
            if blob in seen:
                continue
            seen.add(blob)
            data = git(root, 'cat-file', 'blob', blob)
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                issues.append((commit[:8], path, 'not-utf8-text'))
                continue
            if '\0' in text:
                issues.append((commit[:8], path, 'binary-content'))
            for category in findings(text):
                issues.append((commit[:8], path, category))
    return {'ref': sha, 'commits': len(commits), 'files': len(files), 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    try:
        result = inspect(Path(__file__).resolve().parents[1], args.ref, args.snapshot)
    except (RuntimeError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for commit, path, category in result['issues']:
        # Values are deliberately not included in diagnostic output.
        print(f'FAIL {commit} {path}: {category}')
    print(f"Checked {result['commits']} commits, {result['files']} paths; "
          f"{len(result['issues'])} findings.")
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
