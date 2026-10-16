# 可选本地 LaTeX-OCR 后端

支持 [lukas-blecher/LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR) 的 pix2tex 0.1.4。适用于完整、清晰的独立公式裁剪。碎片、图形标签和手写板书不能保证准确；输出始终标记为待核验候选，语法正确也不代表数学内容正确。

在独立 Python 环境安装 pix2tex 0.1.4、CUDA 版 PyTorch 和匹配的 torchvision。验证 `torch.cuda.is_available()` 为真。参考测试依赖：PyTorch 2.6.0+cu126、timm 0.5.4、x-transformers 0.15.0、albumentations 1.3.1；不要覆盖正在使用的 Paddle 环境。

从上游 v0.0.1 release 下载 `weights.pth` 和 `image_resizer.pth` 到同一目录。在“首次配置”填写独立 Python 和权重路径，在“本地 GPU 公式识别”选择 `pix2tex`。更换公式后端请使用新的输出目录，原任务保留真实的识别来源。

运行时只读取本地权重，网络连接被禁止，CUDA 不可用时明确报错。截图复核、文字整合仍使用用户配置的供应商；此后端不调用 LLM。缓存保存在任务的 `pix2tex-cache`，键包含裁剪内容、尺寸、权重指纹和预处理版本；与 Paddle 缓存分开。已批准的板书公式仍优先复用。

本机三张真实缓存裁剪的试验：完整 `y=y[u(x)]` 可识别；另两张碎片出现错误或花括号不平衡。此小样本不足以证明优于 Paddle，因此不自动替换现有任务后端。建议先对完整公式作本地比较，再决定新批次使用哪种后端。禁止把两个后端的结果合并冒充已验证的公式。

代码采用 MIT 许可，见 `LICENSES/LaTeX-OCR-MIT.txt`。模型文件不随软件发行，部署时从上游获取。
