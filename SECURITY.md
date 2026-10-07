# Security and privacy

This project reads local Windows Live Captions text and Windows media sessions.
It does not require cloud API credentials and contains no transcription-upload
service. Installing dependencies and downloading the initial Windows caption
language pack require internet access.

Captured text, settings and startup logs may reveal personal details. These are
local files, excluded from publication. The app cannot control a selected output
folder's OneDrive or other synchronization settings.

Please report vulnerabilities using this repository's **Security → Report a
vulnerability** option when available. If private reporting is unavailable,
open an issue asking for a private contact channel without posting credentials,
personal data or exploit details. Ordinary bugs can be reported as issues with
synthetic examples and redacted logs.

Use the current source version. Do not disable Defender, Smart App Control or
other Windows protections as a workaround. Review dependency notices before
redistributing a bundled build.
