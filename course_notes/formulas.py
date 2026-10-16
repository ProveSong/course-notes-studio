"""Local formula OCR queue and content-addressed inference cache."""
import hashlib
import json
import re
import threading
from pathlib import Path
from .process import run_command
from .formula_regions import candidates


def annotate_formulas(rows, job, settings, notify, cancel=None):
    if settings.formula_backend=='none':return rows
    if settings.formula_backend not in ('paddle','pix2tex'):raise ValueError('未知的本地公式后端。')
    job=Path(job).resolve()
    reviewed={}
    for path in sorted((job/'board-assets').glob('*/manifest.json')):
        data=json.loads(path.read_text('utf-8'))
        source_hash=data.get('source_sha256')
        if source_hash:
            reviewed[source_hash]=[{'latex':f['latex'],'bbox':f['bbox'],'confidence':f.get('confidence','low'),
                                    'uncertainty':f.get('uncertainty',''),
                                    'status':'reviewed-candidate','backend':'approved-board-cache'}
                                   for f in data.get('analysis',{}).get('formulas',[])]
    rows=[{k:v for k,v in row.items() if k!='local_formulas'} for row in rows]
    tasks=[]
    for index,row in enumerate(rows):
        if reviewed:
            source=(job/row['image']).resolve()
            if not source.is_relative_to(job):raise ValueError('公式图片必须在任务目录中。')
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            if source_hash in reviewed:
                row['local_formulas']=reviewed[source_hash]
                continue
        for region in candidates(row):
            tasks.append({'row':index,'image':row['image'],**region})
    if not tasks:
        count=sum(len(row.get('local_formulas',[])) for row in rows)
        notify('公式 OCR',f'复用已有复核公式 {count} 条；无需启动新识别' if count else '没有可用的公式区域；不向 LLM 自动发送图片')
        return rows
    pix2tex=settings.formula_backend=='pix2tex'
    if pix2tex and not settings.pix2tex_model_dir:
        raise ValueError('请先配置 pix2tex_model_dir 本地权重目录。')
    model=Path(settings.pix2tex_model_dir if pix2tex else settings.formula_model_dir).resolve()
    files=['weights.pth','image_resizer.pth'] if pix2tex else ['inference.yml','inference.json','inference.pdiparams']
    if any(not (model/name).is_file() for name in files):
        raise FileNotFoundError('缺少本地公式权重，请先部署所选公式后端，或显式设置 formula_backend=none。')
    model_hash=hashlib.sha256()
    for name in files:
        with (model/name).open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):model_hash.update(block)
    root=Path(settings.deepread_root).resolve()
    python=Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'
    if pix2tex:
        python=Path(settings.pix2tex_python) if settings.pix2tex_python else root/'.venv-pix2tex/Scripts/python.exe'
    request=job/'formula-request.json'
    if request.exists():
        old=json.loads(request.read_text('utf-8'))
        if old.get('backend','paddle')!=settings.formula_backend:
            raise ValueError('公式后端已变化，请使用新的输出目录，保留原始识别与讲义。')
    request.write_text(json.dumps({'backend':settings.formula_backend,'root':str(root),'job':str(job),'model':str(model),'model_sha256':model_hash.hexdigest(),'tasks':tasks},ensure_ascii=False),'utf-8')
    notify('公式 OCR',f'本地 GPU 离线识别 {len(tasks)} 个区域，重复裁剪复用缓存')
    worker='pix2tex_worker.py' if pix2tex else 'formula_worker.py'
    run_command([python,Path(__file__).with_name(worker),request],job/'formula.log',cancel or threading.Event())
    records=json.loads((job/'formulas.json').read_text('utf-8'))
    result=[{**row,'local_formulas':row.get('local_formulas',[])} for row in rows]
    for record in records:
        result[record['row']]['local_formulas'].append(record)
    return result
