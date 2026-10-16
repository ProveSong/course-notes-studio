from pathlib import Path
from .config import providers


def validate_local_runtime(settings):
    root=Path(settings.deepread_root)
    python=Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'
    if not python.is_file():raise FileNotFoundError(f'本地 GPU Python 不存在：{python}。请在首次配置中指定已有 DeepRead 环境，或运行 setup-gpu.cmd。')
    if settings.device!='cuda':raise ValueError('课程识别需要 GPU，请将 device 设置为 cuda。')
    if settings.formula_backend=='paddle':
        for name in ('inference.json','inference.yml','inference.pdiparams'):
            if not (Path(settings.formula_model_dir)/name).is_file():raise FileNotFoundError('本地公式模型缺少 '+name)
    elif settings.formula_backend=='pix2tex':
        python=Path(settings.pix2tex_python) if settings.pix2tex_python else root/'.venv-pix2tex/Scripts/python.exe'
        if not python.is_file():raise FileNotFoundError('请先部署独立 pix2tex GPU 环境')
        for name in ('weights.pth','image_resizer.pth'):
            if not (Path(settings.pix2tex_model_dir)/name).is_file():raise FileNotFoundError('pix2tex 缺少本地权重 '+name)

def checks(settings):
    home=Path(settings.video_captioner);root=Path(settings.deepread_root)
    files=[('FFmpeg',home/'resource/bin/ffmpeg.exe'),('本地语音识别',home/'resource/bin/Faster-Whisper-XXL/faster-whisper-xxl.exe'),
           ('语音模型',home/f'AppData/models/faster-whisper-{settings.whisper_model}/model.bin'),
           ('GPU Python',Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'),
           ('公式模型',Path(settings.formula_model_dir)/'inference.pdiparams'),
           ('文字检测模型',Path.home()/'.paddlex/official_models/PP-OCRv5_server_det/inference.pdiparams'),
           ('文字识别模型',Path.home()/'.paddlex/official_models/PP-OCRv5_server_rec/inference.pdiparams')]
    rows=[(label,path.is_file(),str(path)) for label,path in files]
    from .credential_store import deepseek_key
    try:rows.append(('DeepSeek API Key',bool(deepseek_key()),'已配置' if deepseek_key() else '未配置；可使用 CC Switch 供应商'))
    except Exception as error:rows.append(('DeepSeek API Key',False,str(error)))
    try:items=providers(settings.cc_database);rows.append(('CC Switch',bool(items),f'{len(items)} 个可用配置'))
    except Exception:rows.append(('CC Switch',False,'未配置；DeepSeek API 可独立使用'))
    return rows
