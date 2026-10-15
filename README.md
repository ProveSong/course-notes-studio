# Course Notes Studio · 课程回放讲义整理器

将课程视频整理为可独立学习的 Markdown 课程讲解。保留定义、推导、例题、有意义的闲聊和师生问答，补充解释明确标注，避免逐句转录与截图日志占满正文。

Windows 桌面 GUI 提供批量视频队列、总进度、阶段进度、取消、任务恢复、截图授权、公式/图形整理，以及用户勾选后的完成关机倒计时。

## 快速开始

1. 从本项目 **Releases** 下载 `CourseNotesStudio-0.2.1-windows-x64.zip`，解压到普通文件夹，双击 `CourseNotesStudio.exe`。GUI 已包含 Python 运行时。
2. 首次使用 GPU OCR：安装 **Python 3.11 x64** 和支持 CUDA 12.6 的 NVIDIA 驱动，然后运行 `setup-gpu.cmd`。该步骤需要联网、数 GB 下载和可用磁盘空间；出现安装错误时终止并显示原因。OCR 推断本身离线运行，禁止 CPU 降级。
3. 安装 [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner)，在其中下载本地 Faster-Whisper `large-v2` 模型。本程序调用其本机 FFmpeg 和 Faster-Whisper-XXL，不上传音频。
4. 使用 DeepSeek 时，在“首次配置 / 环境检查”填写 API Key，接口选 `messages`，模型选 `deepseek-flash`，然后在主窗口选择 **DeepSeek API**。也可在 [CC Switch](https://github.com/farion1231/cc-switch) 中配置其他 LLM，选择数据库、供应商、模型与 `api` / `codex_cli`。使用 CLI 时需安装 [Codex CLI](https://github.com/openai/codex)。LLM 服务费用由所选供应商决定。
5. 选择单个视频，或用“批量导入视频 / 导入文件夹”建立队列，再选择输出目录，点击“开始整理”。默认须在“查看并批准截图复核”中批准后发送图片；也可勾选“本次运行自动同意全部视频任务的截图复核”，授权当前队列中的必要截图请求。开关默认关闭，下次启动不会保留。

首次配置保存在 `%LOCALAPPDATA%\CourseNotesStudio\settings.json`。模型与独立 GPU Python 环境保存在该目录的 `DeepRead` 中，软件更新不会删除它们。课程输出默认在用户文档目录的 `Course Notes` 中。可用 `COURSE_NOTES_HOME` 环境变量指定不同数据目录。

首次环境检查检查组件文件及数据库；GPU 是否可运行由部署及推断阶段实际验证。界面程序可直接运行，完整识别仍依赖已安装的 NVIDIA 驱动、本地 GPU 模型、VideoCaptioner 与 LLM 配置。

## DeepSeek 与批量处理

DeepSeek Key 用 Windows DPAPI 加密保存在软件数据目录的 `deepseek-key.dpapi`，也支持 `DEEPSEEK_API_KEY` 环境变量。密钥输入框留空会保留已存 Key。无需 CC Switch 即可使用 DeepSeek。主窗口模型覆盖栏留空时采用首次配置中的模型；切换供应商会清空覆盖栏。

Messages 模式默认使用支持图像的 `deepseek-flash`，关闭思考输出，仅请求 JSON 正文；文字整合与必要截图复核均可使用该模型。地址自动解析为 `https://api.deepseek.com/anthropic/v1/messages`，自定义网关须填 Messages 根地址。按 [DeepSeek Harness 视觉适配器](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek) 文档及协议实现直接请求，软件不内置或启动 Harness CLI。旧 `chat_completions` 文字兼容模式或不支持视觉的模型，可另选 CC Switch 视觉配置。截图始终遵守授权设置。自动测试覆盖协议、响应完成判断、取消、授权和密钥加密；真实服务调用需要有效密钥与账户额度。

队列按顺序处理，每个视频保存独立讲义与任务目录；同批同名视频用路径摘要区分。某个视频失败后继续下一个，输出目录的 `batch-results.json` 记录成功、失败与任务路径。取消会停止队列。仅全队列成功且没有待复核内容时，才执行用户勾选的完成关机。

同一视频、同一供应商及模型共用持久对话：API 按原顺序携带历史，Codex CLI 使用同一个线程的 `resume`。讲义片段与截图复核顺序执行，重启后恢复历史，不会为每个片段新建对话。不同视频、模型或地址隔离，以免串课或将历史发送给其他供应商。历史保存在任务目录，仅在收到完整响应后提交；保留稳定前缀以利服务端缓存。`llm-usage.json` 保留供应商返回的缓存命中 usage，实际命中率由服务端决定。历史不会为省 token 静默截断，超出模型上下文容量时会报错并保留任务供调整。

自动截图授权仅覆盖本次运行的队列及模型请求的已采集画面，不会上传所有采样帧。记录绑定截图哈希、任务、实际供应商地址、模型和调用方式；更换目的地或图片后不会沿用原授权。截图调用会产生 API 费用。

## 输出与工作流

```text
视频 → 本地语音识别 + 画面采样
     → 本地 GPU 文字 / 公式 OCR
     → 本地去重与精简输入
     → LLM 课程讲解
     → 逐项批准或本次队列自动授权 → 必要的公式复核 / 图形去背景
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

语音、文字与公式 OCR 在本地推断。LLM 整合会发送精简后的课堂文本给所选供应商；仅 OCR 离线不等于整个程序完全离线。截图须逐项批准或由用户明确勾选本次队列自动授权，绑定图片哈希、供应商、地址与模型。API 密钥按需从 CC Switch、环境变量或本机 DPAPI 加密文件读取，不写入软件包、仓库或任务配置。用户负责确保有权处理或分享自己的课程材料。

## 许可证

本项目按 **GPL-3.0-or-later** 发布。第三方组件与模型遵循各自许可证；模型不随软件包分发。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
