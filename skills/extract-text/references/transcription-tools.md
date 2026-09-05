# 转写工具与 GitHub 方案

在 2026-09-06 检查了以下仓库的说明、Skill 和部分实现。这里记录选型依据，不把文档声明当作当前本机已经安装或端到端验证的能力。只在需要选择转写路径时加载本文件。

| 项目 | 适用能力 | 对本 Skill 的选择 |
|---|---|---|
| [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner)，[现成 Skill](https://github.com/WEIFENG2333/VideoCaptioner/blob/master/skills/SKILL.md) | ASR 转写、LLM 字幕纠错、翻译及视频合成；GPL-3.0 | 可选转写后端。字幕优化是文本处理；默认安装还包含 GUI 依赖。未为本 Skill 安装它或其模型。 |
| [video-editing-skill](https://github.com/maxazure/video-editing-skill) | 本地转写、保留原始结果、同步媒体听审页面及剪辑流程 | 参考“原稿与核对稿分开、疑句定位听审”的流程；整包剪辑功能超出本需求，未安装。 |
| [subtitle-maker](https://github.com/DianeHoo/subtitle-maker) | 转写后做拼写、标点和分段校订 | 文档与实际识别后端存在差异，默认语言偏英语；未直接采用。 |
| [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | 抖音信息／下载与外部 API 转写 | 查阅时仓库已归档，转写仍需外部服务配置；不是本机默认后端。 |

本 Skill 的说明和辅助脚本为本次编写，没有复制上述项目的代码。现已另装 Whisper small 与 SenseVoice 本地原音识别后端，使用方式见 [本机双引擎流程](audio-runtime.md)。模型保存在独立运行环境，小型 Skill 备份包不包含模型或服务账号。

## 优先使用已有条件

1. 有完整平台字幕、SRT/VTT 或先前转写，直接复用并校订。
2. 用户给的是抖音链接且 BibiGPT 当前可用，按音视频流程读取现成结果或在本次授权范围内提交链接。接口、登录或收费限制发生变化时现场判断。
3. 本地原媒体要求转写并核对时，运行已安装的原音双引擎脚本；已有字幕作为候选稿参与比对。只提取现成文字时不必额外跑模型。
4. 换电脑或运行环境缺失时，按本机双引擎流程的恢复步骤配置；现有安装无需另外的 API 密钥。不要把仅复制 Skill 文件当作同时复制了模型。

## VideoCaptioner：仅在实际安装后使用

当前上游命令参考：[CLI 文档](https://github.com/WEIFENG2333/VideoCaptioner/blob/master/docs/cli.md)。执行前用对应子命令 `--help` 核实版本参数；无参数调用可能启动 GUI。

```text
videocaptioner transcribe --help
videocaptioner transcribe input.mp4 --asr bijian --language zh -o raw.srt
```

`bijian`／`jianying` 是网络服务路径，不是离线识别；上游称无需 API 密钥，实际可用性需验证。`whisper-cpp` 是可选本地路径，但仍需模型及运行环境；不要自动下载大模型。

后续可直接由 Codex 校订。只有明确选择该程序的 LLM 功能、已有可用 API 凭据时才调用 `subtitle`；保留时间轴的文字纠错需关闭自动分段：

```text
videocaptioner subtitle raw.srt --no-translate --no-split -o corrected.srt
```

该命令仍需 LLM 配置；不要打印密钥，也不要使用默认 `process` 把任务扩展为翻译、配音或合成视频。

## 本地疑句定位

已安装 FFmpeg 时可截取真实疑句范围，例如开始于 83 秒、长 12 秒的音频：

```text
ffmpeg -nostdin -n -ss 83 -i input.mp4 -t 12 -vn -ac 1 -ar 16000 review-83s.wav
```

替换为实际文件和时间；参数通过数组或可靠的 shell 引号传递。截取成功只代表得到片段，后续仍需实际音频核实能力。输出另存，不覆盖源文件。
