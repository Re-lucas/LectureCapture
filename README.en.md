# LectureCapture

Save Windows 11 Live Captions as **SRT subtitles and timestamped Markdown**, locally.
[中文说明](README.md) · [MIT license](LICENSE)

The interface is currently in Chinese. It supports online video timestamps through
Windows media sessions and a classroom mode using elapsed capture time. Stopping
and resuming the same lecture appends to existing files instead of replacing them.

## Quick start

1. Use Windows 11 22H2 or newer with working Live Captions. Windows x64 is the tested platform.
2. Install official [Python 3.14 for Windows](https://www.python.org/downloads/windows/), including Tcl/Tk and pip.
3. Download this repository as a ZIP and extract it, or clone it with Git.
4. Double-click **setup.cmd** once to create `.venv` and install locked dependencies from PyPI.
5. Double-click **LectureCapture.cmd** to open the app.

Other Python versions and ARM64 are not yet verified. Initial dependency and Windows
caption-language downloads require internet access; capture does not require an API key.

Manual installation from PowerShell in the project directory:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\LectureCapture.cmd
```

## Capture

Press **Win+Ctrl+L** to open Live Captions and complete the Windows language setup.
For online video, start playback in Edge and select **在线视频**. The player must
publish a usable Windows media session; not every website reports accurate progress.
For classroom audio, select **线下课堂** and enable **Include microphone audio** in
Live Captions → Settings → Preferences. Recheck that setting each time captions open.

Choose a destination and a name such as `Lecture_01`. Click **开始抓取** to start
and **停止并保存** to stop and save. Keep the same destination, name and capture mode
to resume. Change the name for a new lecture.

The default GUI output is `LectureScripts` inside the Windows Documents folder,
including redirected Documents folders. Output includes `.srt`, `.md`, `.raw.jsonl`
and `.session.json`. A temporary lock prevents simultaneous writers.

## Privacy and limits

The capture engine reads the local caption UI and system media-session timestamps.
It has no cloud transcription, telemetry or caption-upload code, and does not save
audio. See [Microsoft's Live Captions documentation](https://support.microsoft.com/en-us/accessibility/windows/use-live-captions-to-better-understand-audio).

Files saved into OneDrive or another synchronized folder follow that folder's sync
settings. Captured text can contain private or copyrighted material: obtain any
required permission before capturing and inspect it before sharing. Do not post
recordings, personal settings or unredacted logs in issues.

Recognition quality depends on Windows, language support and audio quality. Missing
audio during a caption disconnect cannot be recovered. Raw samples are saved as
capture runs, but unfinished samples are not automatically rebuilt into subtitles
after a crash. This is a study aid, not a guaranteed verbatim transcript system.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Tests use synthetic captions; layout tests briefly open Tk windows. Windows CI
checks regressions but does not exercise real microphone transcription.
See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the
[full Chinese guide](README.md) for CLI arguments and implementation details.

Original project code is MIT-licensed. Dependencies retain their own licenses;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The license does not cover
Windows components or captured course material.
