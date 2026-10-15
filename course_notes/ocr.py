from __future__ import annotations
import json, threading
from pathlib import Path
from .process import run_command

def annotate(rows, job, settings, notify, cancel=None):
    root=Path(settings.deepread_root).resolve()
    python=Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'
    if not python.is_file(): raise FileNotFoundError(f'本地 DeepRead 环境未部署：{python}')
    request=job/'ocr-request.json'
    request.write_text(json.dumps({'root':str(root),'mode':settings.ocr_mode,'rows':rows,'job':str(job.resolve())},ensure_ascii=False),'utf-8')
    notify('DeepRead OCR','启动本地模型进程（禁止网络访问）')
    run_command([python,Path(__file__).with_name('ocr_worker.py'),request.resolve()],job/'deepread.log',cancel or threading.Event())
    result=json.loads((job/'ocr.json').read_text('utf-8'))
    notify('DeepRead OCR',f'已完成 {len(result)} 张本地识别')
    return result
