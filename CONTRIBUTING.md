# Contributing

Issues and pull requests are welcome. Chinese and English reports are both fine.

For a bug, include Windows/Python versions, capture mode, reproduction steps and
expected/actual behavior. Use a short invented caption example when possible.
Remove usernames, personal paths, course content and credentials from all reports,
screenshots and logs. Do not attach `settings.json` or complete recordings.

Use Python 3.14 on Windows and the locked dependencies. Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Test changes to timestamps, append/resume or file locking with synthetic data.
Do not change Windows security settings to make the app run. Dependencies must
remain separate downloads with their original notices preserved.

## Publication check

The public repository starts from a sanitized snapshot. Do not merge or push
unreviewed private history into it, and do not use `git push --mirror`.

Before publishing, inspect the diff and the intended branch:

```powershell
python scripts/check_publication.py --ref HEAD
```

The checker scans every reachable commit on that ref, including file names,
commit messages and author metadata. It rejects files outside the explicit public
allowlist and several common sensitive-data patterns, without printing matched
values. It is a guardrail, not a guarantee: manually review changes as well.
Use `--snapshot` to check only the selected commit's files and metadata when
preparing a new clean snapshot. Add intentional new public files to the allowlist
only after reviewing their contents. Personal transcripts and local settings
must never be added to it.

Pull requests use GitHub's normal branch history and should include relevant
validation. By contributing code, you agree to license that contribution under
this project's MIT license.
