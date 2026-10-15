from pathlib import Path
from .config import providers

def checks(settings):
    home=Path(settings.video_captioner);root=Path(settings.deepread_root)
    files=[('FFmpeg',home/'resource/bin/ffmpeg.exe'),('本地语音识别',home/'resource/bin/Faster-Whisper-XXL/faster-whisper-xxl.exe'),
           ('语音模型',home/f'AppData/models/faster-whisper-{settings.whisper_model}/model.bin'),
           ('GPU Python',Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'),
           ('公式模型',Path(settings.formula_model_dir)/'inference.pdiparams'),
           ('文字检测模型',Path.home()/'.paddlex/official_models/PP-OCRv5_server_det/inference.pdiparams'),
           ('文字识别模型',Path.home()/'.paddlex/official_models/PP-OCRv5_server_rec/inference.pdiparams')]
    rows=[(label,path.is_file(),str(path)) for label,path in files]
    try:items=providers(settings.cc_database);rows.append(('CC Switch',bool(items),f'{len(items)} 个可用配置'))
    except Exception as error:rows.append(('CC Switch',False,str(error)))
    return rows
