# LectureCapture

**把 Windows 11 实时辅助字幕保存为可复习的文字稿与 SRT 字幕。**

Capture Windows 11 Live Captions locally as SRT subtitles and timestamped Markdown.
[English quick start](README.en.md) · [MIT license](LICENSE)

支持在线视频与线下课堂。视频模式跟随浏览器媒体会话的播放时间，课堂模式按采集时长计时。
同一节课停止后可以继续追加，不覆盖已有记录；窗口缩小时自动重排，开始/停止按钮始终在底部。
界面目前为中文。

## 系统要求

- Windows 11，22H2 或更新版本，并能正常打开实时辅助字幕。当前验证平台为 Windows x64。
- 官方 [Python 3.14](https://www.python.org/downloads/windows/)，安装时保留 Tcl/Tk 与 pip。其他 Python 版本和 ARM64 尚未验证。
- 在线视频建议先用 Edge；播放器须向 Windows 发布可用的媒体会话。不是每个网站都会上报正确的进度。
- 第一次安装 Python 依赖、第一次下载 Windows 字幕语言包需要联网。准备好后，本工具不需要云 API 或 API key。

## 安装与启动

1. 在本仓库点 **Code → Download ZIP**，完整解压；也可以 `git clone https://github.com/Re-lucas/LectureCapture.git`。
2. 安装上面的官方 Python。
3. 在解压后的项目目录双击 **setup.cmd**。它创建独立的 `.venv`，并从 PyPI 安装锁定版本的依赖。
4. 安装完成后，双击 **LectureCapture.cmd** 打开面板。

也可以用 PowerShell 手动安装：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\LectureCapture.cmd
```

直接双击 `launch.pyw` 或 `LectureCapture.pyw` 也会切换到项目环境，但需要 Windows 已正确关联 `.pyw`。
推荐使用 `.cmd` 入口；本仓库不提供未签名 EXE，也不要求关闭 Defender 或智能应用控制。
启动失败时错误写入本地 `runtime/startup.log`。

## 在线视频

1. 按 **Win+Ctrl+L** 打开实时辅助字幕，首次使用按 Windows 提示下载语言包。
2. 在 Edge 播放视频，确认字幕窗口确实显示文字。
3. 打开 LectureCapture，选择 **在线视频**，选择保存文件夹并填写名称，例如 `Lecture_01`。
4. 查看预检状态，点 **开始抓取**；结束后点 **停止并保存**。

默认保存到 Windows「文档」下的 `LectureScripts`，图形界面会识别文档目录的重定向。
可选择别的文件夹；`settings.json` 会在本地保存上一次的选择。

## 线下课堂

1. 选择 **线下课堂**，按 **Win+Ctrl+L** 打开实时辅助字幕。
2. 在字幕窗口的 **设置 → 首选项 → 包括麦克风音频** 中启用麦克风；每次打开字幕窗口都要确认。
3. 确认字幕能识别现场声音，再点 **开始抓取**；下课点 **停止并保存**。

电脑播放的音频可能优先于麦克风。录课堂时建议保持电脑静音；远距离、混响和多人同时讲话会影响识别质量。

## 停止后继续

保持同一名称、文件夹与采集方式，点 **继续抓取 · 保留已有记录**。
工具向已有文件追加，SRT 编号继续递增。视频模式使用实际视频位置；课堂模式从上一段累计时长继续，停止期间不计时。
换一节课请换名称。

| 文件 | 内容 |
| --- | --- |
| `<名称>.srt` | 带时间戳的字幕 |
| `<名称>.md` | 带时间戳的可读文字稿 |
| `<名称>.raw.jsonl` | 字幕及媒体状态的原始采样，采集时逐条写入 |
| `<名称>.session.json` | 采集方式与累计时长，供安全续录使用 |
| `.<名称>.capture.lock` | 防止两个实例同时写同一记录；停止后自动释放 |

格式损坏、方式不匹配或输出被其他程序改动时，工具拒绝不安全的续写。
字幕短暂断开后每两秒尝试重连；断开期间的语音无法补录。
异常退出后未导出的 raw 不会自动重建 SRT；原始采样也不能保证完全恢复一份成稿。

## 隐私与使用边界

采集引擎只读取本机字幕窗口的 UI Automation 文本与 Windows 系统媒体会话（SMTC），
没有字幕上传、遥测、在线账号或云转写代码；不保存原始音频。
[微软说明](https://support.microsoft.com/en-us/accessibility/windows/use-live-captions-to-better-understand-audio)
介绍了实时辅助字幕的本机处理方式。

保存的文字可能包含姓名、课程内容和其他个人信息。请在录制前遵守授课者的要求及场所规则，分享前检查内容。
字幕默认不进入 Git。选择 OneDrive 等同步文件夹时，文件会按该文件夹的同步设置上传，这不是 LectureCapture 发起的上传。
不要把录制结果、`settings.json` 或原始启动日志直接附到公开 issue；报错时先去掉用户名、路径和课程内容。

识别由 Windows 完成；本工具不保证所有语言、Windows 版本或播放器均可用。它用于学习整理，不是可靠的逐字记录系统。

## 命令行

在项目目录的 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe capture.py --name Lecture_01 --out "$env:USERPROFILE\Documents\LectureScripts"
.\.venv\Scripts\python.exe capture.py --mode classroom --name Lecture_02 --out "$env:USERPROFILE\Documents\LectureScripts"
```

`capture.cmd` 可直接双击运行交互式视频采集，也支持转发参数。
命令行示例使用常规文档路径；OneDrive 等重定向路径请用实际路径替换，或使用图形界面。

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| `--name` | 必填 | 文件名称，不含目录和后缀 |
| `--out` | Windows 文档目录 | 输出文件夹 |
| `--mode` | `video` | `video` 或 `classroom` |
| `--app` | `msedge` | 媒体会话应用 ID 过滤字串 |
| `--settle` | `1.2` | 一行不再变化多久后定稿（秒） |
| `--poll` | `0.3` | 采样间隔（秒） |
| `--no-split` | 关闭 | 不按句子切分 |
| `--list-sessions` | 关闭 | 显示所选媒体会话状态后退出，仍需 `--name` |

## 工作原理与开发

UI Automation 直接读取字幕文本，不使用 OCR。字幕逐词增长与原地修正经合并后输出，句内时间按文本长度估算。
视频模式基于 SMTC 的 `position`、`last_updated_time` 与播放速率外推，减少浏览器只在播放事件时刷新位置造成的冻结。
小于五秒的后退抖动会钳制；更大后退按跳转处理。具体精度仍取决于播放器上报及字幕识别延迟。

在 Windows 上运行回归：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

测试使用虚构字幕与临时目录，不需要录真实课堂。布局测试会短暂创建 Tk 窗口。
GitHub Actions 也运行 Windows/Python 3.14 回归；CI 不验证真实麦克风或字幕识别效果。

- `LectureCapture.pyw`：Tk 图形界面。
- `capture.py`：字幕、时间轴、追加与文件锁。
- `bootstrap.py` / `launch.pyw`：项目 Python 切换及启动错误报告。
- `requirements.lock.txt`：已验证依赖版本；`requirements.txt` 为未锁定的直接依赖清单。
- `scripts/check_publication.py`：公开发布前检查文件白名单、常见敏感信息及目标分支历史。
- [CONTRIBUTING.md](CONTRIBUTING.md)：提 issue、开发与公开发布检查。

## 许可证

项目原创源码采用 [MIT](LICENSE)。第三方依赖保留各自许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
项目许可证不覆盖课程录音、字幕内容或 Windows 组件。
