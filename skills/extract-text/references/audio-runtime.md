# 本机原音双引擎复核

实际安装的后端为 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 的 Whisper small 和 [sherpa-onnx SenseVoice](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html) INT8。两者在 CPU 上分别读取原音，无需外部 API；识别阶段不上传音频，不自动下载模型。

## 运行

Windows 默认运行环境为“文档/Codex/skill-runtimes/extract-text-audio”；可用 `CODEX_AUDIO_RUNTIME` 指定其他已安装目录。使用当前 Skill 的绝对路径调用 [启动脚本](../scripts/run_audio_verify.ps1)：

```powershell
& '当前Skill目录\scripts\run_audio_verify.ps1' '原视频或音频绝对路径' --output-dir '本次任务全新工作目录' --language zh
```

已有 BibiGPT、平台字幕或人工稿时，加 `--candidate '仅含原文的TXT或SRT或VTT绝对路径'`；候选原文不会送入识别模型，仅在独立识别结束后比较。

只核对部分原音时加 `--start 83 --duration 12`，单位为秒。字幕文件使用原视频时间坐标；纯文本候选须只含对应范围的正文。默认中文，也支持英、日、韩、粤语和自动判断；粤语由 Whisper 中文模型与 SenseVoice 粤语模式比较，不能保证方言字形一致。

输出目录须为全新路径。执行失败会报错，已创建输出时另有 `failure.json`；不能把部分文件当完成结果。缺原媒体时，先在用户授权范围内取得视频或音频：公开链接可用当前可用下载器／网页导出；现成字幕页面不代表已经取得声音。平台取不到原音就说明具体原因，保留已做的文字工作。

## 脚本实际做什么

[audio_verify.py](../scripts/audio_verify.py) 将选中原音解码为 16 kHz 单声道，Whisper 独立识别整段，SenseVoice 按连续 24 秒窗口覆盖全部选定音频，包括 Whisper 没有文字的时段。Whisper 词级时间戳用于粗略对应窗口，不是人工校准。

| 文件 | 用途 |
|---|---|
| `whisper.raw.txt`、`whisper.raw.srt` | 第一引擎原始结果及估计时间戳 |
| `sensevoice.raw.txt` | 第二引擎原始文字 |
| `audio_evidence.json` | 输入来源、实际覆盖范围、引擎版本、逐窗识别证据 |
| `review_report.json` | 引擎之间／候选与原音识别之间的差异及疑点定位 |
| `review_clips/*.wav` | 自动提取的疑点原音片段 |

SenseVoice 的时间区间是实际读取的音频窗口，不是逐句字幕时间。仅 Whisper 的真实识别时间戳可用于 SRT，不用窗口时间伪造逐句对齐。

## 形成校订稿

- 先读取 `review_report.json`，再按需读取原始稿和对应证据。输出状态称“已完成原音双引擎机器复核（范围……）”，不用“人工听审”或“准确率100%”。
- 两个引擎一致且候选稿不同的地方，可依据两份原音识别证据提出修订并保留修改记录。两个引擎分歧时，结合语境、术语和来源信息判断；必要时扩大疑句前后范围再运行局部识别，不无故重复全片。
- 差异检查保守保留字词、数值符号与否定词；“15”和“十五”、繁简字、窗口切分也可能被报出。先区分书写形式与含义改变，相同数值的表达可以统一，但不能把“十五／五十”或“不是／是”当格式变化忽略。
- 同音姓名、噪声片段或两个模型仍不一致的内容，保留候选和具体依据，列为待确认。模型一致仍可能同时识别错；不要拿一致率冒充准确率。
- 完成必要的文字校订和原稿差异检查后，在用户的交付目录给出校订稿与简短修改记录。识别过程文件默认留工作目录，用户需要时再交付，避免正文混入程序日志。

## 环境恢复与迁移

当前安装已通过本机原创中文 TTS 的真实推理测试，另测了带起始偏移的跨窗口音频。模型约 727 MB；运行环境和模型不放入小型 Skill 压缩包。换电脑时需另装：

```text
已有Python解释器 setup_audio.py --runtime-root 新电脑运行环境绝对路径
```

[setup_audio.py](../scripts/setup_audio.py) 建独立 venv、安装固定版本依赖、从官方维护者的 Hugging Face 仓库下载固定提交并验证文件大小和哈希。只在首次设置／修复且任务已授权时运行；日常识别不调用 setup。模型来源及校验值保存在运行环境 `setup-manifest.json`。

Whisper 使用 MIT 许可；Sherpa 代码为 Apache 许可，SenseVoice 权重适用其上游 FunASR 模型协议，保留下载的 README／LICENSE 及来源。移植到非 Windows 环境时直接用该 venv 的 Python 调用 `audio_verify.py` 并传 `--runtime-root`，不使用 PowerShell 启动器。
