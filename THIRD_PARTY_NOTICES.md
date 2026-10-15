# Third-party components

- **VideoCaptioner** — https://github.com/WEIFENG2333/VideoCaptioner — GPL-3.0. The ASR adapter follows its local Faster-Whisper command workflow. Its application, FFmpeg and Faster-Whisper binaries are user-installed and are not redistributed here. License text: `LICENSES/VideoCaptioner-GPL-3.0.txt`.
- **DeepRead.OCR_AIML_22** — https://github.com/Mahidhar21/DeepRead.OCR_AIML_22 — MIT, copyright 2025 Mahidhar21. Local OCR adapters follow its model deployment approach; the upstream repository and weights are not bundled. License notice retained in `LICENSES/DeepRead-MIT.txt`.
- **PaddleOCR / PaddleX / PaddlePaddle** — https://github.com/PaddlePaddle/PaddleOCR — Apache-2.0. Installed separately for GPU inference; model licenses must be reviewed at their upstream distribution. Formula model: https://huggingface.co/PaddlePaddle/PP-FormulaNet_plus-S.
- **Handwritten_model** — https://huggingface.co/imperiusrex/Handwritten_model. Downloaded separately for optional handwriting mode. Refer to the model repository for current license and usage terms.
- **PyTorch / Transformers** — https://github.com/pytorch/pytorch (BSD-style) / https://github.com/huggingface/transformers (Apache-2.0). Optional GPU environment dependencies, not included in the GUI archive.
- **Codex CLI / CC Switch** — https://github.com/openai/codex / https://github.com/farion1231/cc-switch. User-installed external tools. Credentials are read locally on demand; these applications are not bundled.
- **OpenCV, NumPy, Pillow, Requests, Python, Tcl/Tk and PyInstaller** are included or used by the desktop build under their upstream licenses. PyInstaller's bootloader exception permits distribution of packaged applications. Build scripts collect installed dependency license files into the desktop archive.

No course recording, transcript, screenshot, private API configuration or model weight is licensed or distributed by this project. Downloading external components does not change their licenses.
