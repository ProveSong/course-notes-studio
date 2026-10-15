from .config import RESOURCES
"""Approved visual structure enrichment and reusable local rendering cache."""
import json,hashlib
from pathlib import Path
from .review import apply_task_consent,destination,digest,resolve_image
from .llm import call,parse_json
from .board_assets import materialize
from .process import check_cancel


def enrich(job,settings,identity,cancel,notify=lambda a,b:None):
    job=Path(job);check_cancel(cancel);apply_task_consent(job,settings)
    records=json.loads((job/'review-requests.json').read_text('utf-8'))
    record=next(r for r in records if r['id']==identity)
    if record['status'] not in ('approved','reviewed'):raise ValueError('板书结构化需要截图批准。')
    if record.get('destination')!=destination(settings):raise ValueError('板书结构化目的地已变化，需要重新批准。')
    if record.get('approved_transport',settings.llm_transport)!=settings.llm_transport:raise ValueError('调用方式已变化。')
    image=resolve_image(job,record['image'])
    if digest(image)!=record['sha256']:raise ValueError('板书原图已变更，需要重新批准。')
    instructions=(RESOURCES/'skills/board-structure/SKILL.md').read_text('utf-8')
    fingerprint=hashlib.sha256(json.dumps([record['sha256'],destination(settings),settings.llm_transport,instructions],ensure_ascii=False).encode()).hexdigest()
    cache=job/'chunks'/f'{identity}.board-response.json'
    value=json.loads(cache.read_text('utf-8')) if cache.exists() else {}
    if value.get('fingerprint')==fingerprint:result=value['result']
    else:
        rendered=job/'board-assets'/identity/'manifest.json'
        existing=json.loads(rendered.read_text('utf-8')) if rendered.exists() else {}
        if existing.get('source_sha256')==record['sha256'] and existing.get('analysis',{}).get('formulas') is not None:
            result=existing['analysis']
            text=materialize(job,identity,image,result)
            (job/'chunks'/f'{identity}.board.md').write_text(text,'utf-8')
            return result
        chunk=json.loads((job/'chunks'/f'{record["chunk"]}.evidence.json').read_text('utf-8'))
        speech=[s for s in chunk.get('speech',[]) if s['end']>=record['time']-30 and s['start']<=record['time']+30]
        notify('板书结构化',identity)
        local=[f for v in chunk.get('visuals',[]) if v.get('image')==record['image'] for f in v.get('local_formulas',[])]
        from .compact import dumps
        prompt=instructions+'\n问题：'+record['reason']+'\n附近语音：'+dumps([s['text'] for s in speech])+'\n本地公式候选：'+dumps([{k:f[k] for k in ('latex','bbox','status') if k in f} for f in local])
        result=parse_json(call(settings,prompt,[image],cancel=cancel))
        if not isinstance(result.get('markdown'),str) or not isinstance(result.get('formulas'),list) or not isinstance(result.get('diagrams'),list):raise ValueError('板书结构结果缺少字段。')
        cache.write_text(json.dumps({'fingerprint':fingerprint,'result':result},ensure_ascii=False,indent=2),'utf-8')
    # Local rendering can be retried without paying for another vision request.
    text=materialize(job,identity,image,result)
    (job/'chunks'/f'{identity}.board.md').write_text(text,'utf-8')
    if settings.compact_notes:
        (job/'chunks'/f'{identity}.teaching-review.md').write_text(result['markdown'],'utf-8')
    return result


def process(job,settings,notify,cancel):
    from dataclasses import replace
    settings=replace(settings,conversation_file=str(job/'deepseek-conversation.json'))
    apply_task_consent(job,settings)
    records=json.loads((Path(job)/'review-requests.json').read_text('utf-8'))
    for record in records:
        if record['status'] in ('approved','reviewed'):
            enrich(job,settings,record['id'],cancel,notify)
