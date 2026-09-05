# 我的 Codex Skills

个人技能备份。当前包含 [文字提取与校对](skills/extract-text/SKILL.md)：图片、扫描件、PDF 文字提取，以及视频／音频转写和原音双引擎机器复核。

## 第一次放到 GitHub

1. 解压本包，打开 `codex-skills-github` 文件夹。
2. 打开 [GitHub 新建仓库](https://github.com/new?name=codex-skills&visibility=private)，仓库名称建议 `codex-skills`。仅用于自己跨电脑备份时选择 **Private**；希望任何人能读取时才选择 Public。
3. 本包已有 README 和忽略规则，建仓库时不用额外生成这些文件，点击 **Create repository**。
4. 空仓库点击 **uploading an existing file**；已有文件的仓库点击 **Add file → Upload files**。
5. 将本文件夹里的 `README.md`、`.gitignore` 和整个 `skills` 文件夹拖进上传区，保持目录结构。上传解压后的文件，不要只上传 ZIP，也不要再套一层 `codex-skills-github` 目录。
6. 提交说明可写 `Add extract-text skill`，提交上传；检查首页能看到 `skills/extract-text/SKILL.md`，然后保存仓库链接。

上传完成后的仓库结构：

```text
codex-skills/
├── README.md
├── .gitignore
└── skills/
    └── extract-text/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/
        └── scripts/
```

GitHub 官方步骤：[创建仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)、[上传文件或文件夹](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。

## 换电脑后使用

在新电脑安装并登录 Codex。如果仓库是私有的，确保新电脑可以通过有权限的 GitHub 登录访问它；不需要把访问令牌写入仓库或聊天记录。

把以下文字发送给新电脑上的 Codex，替换第一行的仓库链接：

> 我的技能仓库是：在这里粘贴 GitHub 仓库链接。
> 请使用 Skill Installer 安装其中的 skills/extract-text，并按 references/audio-runtime.md 配置本机 Whisper small 和 SenseVoice 双引擎环境。
> 优先使用已安装的 Python 3.12；Codex 有内置 Python 时使用内置解释器。授权下载所需依赖和约 727 MB 模型。请验证安装结果；如果已有同名 Skill，先检查并备份再更新。

安装 Skill 与安装音频运行环境是两个步骤。只复制技能目录即可获得说明和脚本；原音识别还需要完成模型安装。图片／PDF 提取沿用新电脑上 Codex 的相关工具。

目前实际验证的平台为 **Windows x64 + Python 3.12**。macOS/Linux 可使用 Python 脚本入口，但本包未在这些平台实测；不要将 Windows 的 venv 直接复制过去。

完成配置后，可以说：

> 用文字提取与校对，把这个视频转写并对照原音，给我校订稿和待确认的地方。

视频链接仍需要取得实际原视频或音频才能做原音复核。平台现成字幕可以作为候选稿，不能代替声音。

## 文件与运行环境

- `skills/extract-text`：可上传和安装的技能说明、脚本。
- `setup_audio.py`：首次配置时安装独立 Python 环境、下载固定版本模型并检查哈希。日常识别不会再次下载模型。
- 本地音频模型约 **727 MB**，另需依赖库和运行空间。它们不包含在仓库中，在新电脑首次配置时重新下载。
- 音视频原文件、转写成稿、测试素材、账号配置和 Python 虚拟环境均不包含在本包中。

详细操作见 [原音双引擎说明](skills/extract-text/references/audio-runtime.md)。两个模型分别读取原音并报告分歧，属于机器复核；一致不代表绝对正确。

## 后续更新

以后修改 Skill 后，将更新过的 `skills/extract-text` 文件同步到这个仓库。新电脑需要新版时，告诉 Codex“从这个仓库更新 extract-text，保留并备份已有本地修改”。GitHub 备份不代表所有电脑会自动同步。

第三方项目和模型的来源及许可说明见 [工具来源](skills/extract-text/references/transcription-tools.md) 和 [运行环境说明](skills/extract-text/references/audio-runtime.md)。此仓库不重新分发模型权重。
