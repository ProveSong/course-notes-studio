"""Local formula OCR queue and content-addressed inference cache."""
import hashlib
import json
import re
import threading
from pathlib import Path
from .process import run_command


def candidates(row):
    # Detector polygons are proposals, not proof that the whole formula was
    # captured. Existing verified board boxes can also be provided explicitly.
    for region in row.get('ocr_regions', []):
        text=region.get('text','')
        if re.search(r'[=∑∫√∞≤≥∈∉⊂∀∃→α-ωΑ-Ω]|[a-zA-Z]\s*\^|\\(?:frac|sum|int)',text):
            yield {'bbox':region['bbox'],'background':'auto','proposal':'text-detector'}
    yield from row.get('formula_regions', [])


def annotate_formulas(rows, job, settings, notify, cancel=None):
    if settings.formula_backend=='none':return rows
    if settings.formula_backend!='paddle':raise ValueError('未知的本地公式后端。')
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
    model=Path(settings.formula_model_dir).resolve()
    files=['inference.yml','inference.json','inference.pdiparams']
    if any(not (model/name).is_file() for name in files):
        raise FileNotFoundError('缺少本地公式权重，请运行 deploy_formula.py，或显式设置 formula_backend=none。')
    model_hash=hashlib.sha256()
    for name in files:
        with (model/name).open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):model_hash.update(block)
    root=Path(settings.deepread_root).resolve()
    python=Path(settings.deepread_python) if settings.deepread_python else root/'.venv-paddle/Scripts/python.exe'
    request=job/'formula-request.json'
    request.write_text(json.dumps({'root':str(root),'job':str(job),'model':str(model),'model_sha256':model_hash.hexdigest(),'tasks':tasks},ensure_ascii=False),'utf-8')
    notify('公式 OCR',f'本地 GPU 离线识别 {len(tasks)} 个区域，重复裁剪复用缓存')
    run_command([python,Path(__file__).with_name('formula_worker.py'),request],job/'formula.log',cancel or threading.Event())
    records=json.loads((job/'formulas.json').read_text('utf-8'))
    result=[{**row,'local_formulas':row.get('local_formulas',[])} for row in rows]
    for record in records:
        result[record['row']]['local_formulas'].append(record)
    return result
