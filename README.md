# Course Notes Studio · 课程回放讲义整理器

将课程视频整理为可独立学习的 Markdown 课程讲解。保留定义、推导、例题、有意义的闲聊和师生问答，补充解释明确标注，避免逐句转录与截图日志占满正文。

Windows 桌面 GUI 提供总进度、阶段进度、取消、任务恢复、截图批准、公式/图形整理，以及用户勾选后的完成关机倒计时。

## 快速开始

1. 从本项目 **Releases** 下载 `CourseNotesStudio-0.1.0-windows-x64.zip`，解压到普通文件夹，双击 `CourseNotesStudio.exe`。GUI 已包含 Python 运行时。
2. 首次使用 GPU OCR：安装 **Python 3.11 x64** 和支持 CUDA 12.6 的 NVIDIA 驱动，然后运行 `setup-gpu.cmd`。该步骤需要联网、数 GB 下载和可用磁盘空间；出现安装错误时终止并显示原因。OCR 推断本身离线运行，禁止 CPU 降级。
3. 安装 [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner)，在其中下载本地 Faster-Whisper `large-v2` 模型。本程序调用其本机 FFmpeg 和 Faster-Whisper-XXL，不上传音频。
4. 在 [CC Switch](https://github.com/farion1231/cc-switch) 中配置 LLM，点击 GUI 的“首次配置 / 环境检查”，选择 VideoCaptioner 目录和 CC Switch 数据库。选择供应商、模型与 `api` / `codex_cli`。使用 CLI 时需安装 [Codex CLI](https://github.com/openai/codex)。LLM 服务费用由所选供应商决定。
5. 选择视频和输出目录，点击“开始整理”。仅在具体内容需要看图时提出截图请求；点击“查看并批准截图复核”后才允许发送图片。新视频需要单独批准。

首次配置保存在 `%LOCALAPPDATA%\CourseNotesStudio\settings.json`。模型与独立 GPU Python 环境保存在该目录的 `DeepRead` 中，软件更新不会删除它们。课程输出默认在用户文档目录的 `Course Notes` 中。可用 `COURSE_NOTES_HOME` 环境变量指定不同数据目录。

首次环境检查检查组件文件及数据库；GPU 是否可运行由部署及推断阶段实际验证。界面程序可直接运行，完整识别仍依赖已安装的 NVIDIA 驱动、本地 GPU 模型、VideoCaptioner 与 LLM 配置。

## 输出与工作流

```text
视频 → 本地语音识别 + 画面采样
     → 本地 GPU 文字 / 公式 OCR
     → 本地去重与精简输入
     → LLM 课程讲解
     → 用户批准具体截图 → 必要的公式复核 / 图形去背景
```

- `视频名—课程讲解.md`：教学正文，含补充解释与必要板书补正。
- `视频名_job/`：完整转录、OCR、帧、模型候选、审批、缓存、阶段结果和错误记录。原始资料不进入公开仓库。
- `llm-usage.json`：记录服务返回的实际 token usage、输入字符数与图片数；日志位置在软件数据目录。

原始资料保留供复查；不把证据编号、水印、孤立的“继续播放 不知道。”、机械重复和处理日志塞进课程正文。默认 `compact_notes=true`。需要历史逐条证据模式时可在设置中关闭。

## 公式、图形与准确性

文字 OCR 沿用 [DeepRead.OCR](https://github.com/Mahidhar21/DeepRead.OCR_AIML_22) 的 PaddleOCR / TrOCR 部署思路。公式由本地 **PP-FormulaNet_plus-S** 提供 LaTeX 候选，优先复用已有复核结果，再对具体歧义请求用户批准的视觉 LLM。图形使用本地脚本裁剪、去背景与增强笔迹，不生成不存在的线条。

公式检测目前使用文字框启发式，可能漏掉复杂结构或截断分式。手写黑板公式小样本仍有明显误读；语法通过不能当作识别正确。自动采样、ASR、OCR 和 LLM 均可能遗漏或错误，重要内容应结合原始资料核验。软件不承诺逐帧零遗漏。

曾评估 [qs956/Latex_OCR_Pytorch](https://github.com/qs956/Latex_OCR_Pytorch)：其 README 链接的预训练权重目前无法获取，相关 [Issue #8](https://github.com/qs956/Latex_OCR_Pytorch/issues/8) 也有报告，故没有将其标为已集成后端。

默认省 token 模式去掉采集元数据、重复板书文本、重叠上下文和无用输出。一次已有课程材料的离线比较显示输入字符量下降约 70%；这是字符对比，不是收费 token 比例或所有视频的保证。不会用固定截断删除关键推理，也不以减少 token 为由直接信任错误公式。

## 源码运行与构建

Windows 安装 Python 3.11 后，双击 `run-source.cmd` 自动创建 GUI 虚拟环境并启动。GPU 环境另运行 `setup-gpu.cmd`。

```powershell
py -3.11 -m pip install -r requirements.txt
py -3.11 desktop.py
py -3.11 -m course_notes --help
py -3.11 -m unittest discover -s tests
# 构建可分发桌面包：
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

`skills/course-handout` 负责初稿，`skills/course-explainer` 提供课程讲解编辑规范，`skills/board-structure` 负责获批截图复核和本地提图脚本。skills 随软件一起分发。测试使用模拟数据，不附课程视频、音频、私人讲义或模型权重。

标记 `v*` 的 Git tag 触发 GitHub Actions 构建 Windows ZIP、执行单元测试和打包 GUI 启动检查，再发布 Release。也可手动运行工作流构建下载 artifact。程序未进行代码签名，Windows 可能显示未知发布者提示。

## 隐私与授权

语音、文字与公式 OCR 在本地推断。LLM 整合会发送精简后的课堂文本给所选供应商；仅 OCR 离线不等于整个程序完全离线。截图上传须逐项批准，绑定图片哈希、供应商、地址与模型。API 密钥按需从 CC Switch 读取，不写入软件包、仓库或任务配置。用户负责确保有权处理或分享自己的课程材料。

## 许可证

本项目按 **GPL-3.0-or-later** 发布。第三方组件与模型遵循各自许可证；模型不随软件包分发。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
