"""Per-image consent, recorded against file digest and destination provider."""
from __future__ import annotations
from .config import RESOURCES
import hashlib, json
import os,uuid
from pathlib import Path
from .config import selected_provider
from .llm import call, parse_json
from .process import check_cancel
from .jsonstore import transaction


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def destination(settings):
    p=selected_provider(settings)
    return {'provider':p.identity,'base_url':p.base_url,'model':p.model}


def resolve_image(job, relative):
    path=(job/relative).resolve()
    if not path.is_relative_to((job/'visuals').resolve()) or not path.is_file():
        raise ValueError('截图必须来自本任务 visuals 目录。')
    return path


def grant_task_consent(job,settings):
    """Called only after the user approves this video's requested frames."""
    if settings.llm_transport!='codex_cli': raise ValueError('任务范围授权仅用于 Codex CLI。')
    manifest=json.loads((job/'manifest.json').read_text('utf-8'))
    visuals=json.loads((job/'visuals.json').read_text('utf-8'))
    policy={'scope':'requested-existing-video-frames','signature':manifest['signature'],
            'destination':destination(settings),'transport':'codex_cli',
            'images':{v['image']:digest(resolve_image(job,v['image'])) for v in visuals}}
    path=job/'review-policy.json';temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(policy,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,path)
    apply_task_consent(job,settings)


def apply_task_consent(job,settings):
    path=job/'review-policy.json'
    if not path.exists(): return
    policy=json.loads(path.read_text('utf-8'));manifest=json.loads((job/'manifest.json').read_text('utf-8'))
    if policy.get('signature')!=manifest['signature'] or policy.get('destination')!=destination(settings) or policy.get('transport')!=settings.llm_transport: return
    with transaction(job/'review-requests.json') as records:
        for record in records:
            if record['status']!='pending': continue
            original=policy['images'].get(record['image'])
            if original!=record['sha256'] or digest(resolve_image(job,record['image']))!=original: continue
            record.update(status='approved',destination=policy['destination'],approved_transport='codex_cli',approval_source='user-task-consent')


def register(job, chunk_id, requests, visuals):
    path=job/'review-requests.json'
    with transaction(path) as records:
        allowed={v['id']:v for v in visuals}
        for request in requests:
            if not isinstance(request,dict) or request.get('visual_id') not in allowed: continue
            visual=allowed[request['visual_id']]; image=resolve_image(job,visual['image'])
            identity=f'{chunk_id}-{visual["id"]}'
            if any(r['id']==identity for r in records): continue
            records.append({'id':identity,'chunk':chunk_id,'visual_id':visual['id'],'image':visual['image'],
                            'time':visual['time'],'sha256':digest(image),'reason':str(request.get('reason','需视觉复核')),'status':'pending'})


def decide(job, ids, settings, approve=True):
    path=job/'review-requests.json'; requested=set(ids)
    with transaction(path) as records:
        if requested-set(r['id'] for r in records): raise ValueError('包含未知的截图请求编号。')
        for record in records:
            if record['id'] not in requested: continue
            if digest(resolve_image(job,record['image']))!=record['sha256']: raise ValueError('截图内容已变更，须重新提出复核请求。')
            record['status']='approved' if approve else 'denied'
            record['destination']=destination(settings)


def process_approved(job, settings, notify, cancel, only_ids=None):
    apply_task_consent(job,settings)
    path=job/'review-requests.json'
    if not path.exists(): return
    records=json.loads(path.read_text('utf-8'))
    for record in records:
        check_cancel(cancel)
        if only_ids is not None and record['id'] not in only_ids: continue
        latest=json.loads(path.read_text('utf-8'))
        record=next(r for r in latest if r['id']==record['id'])
        if record['status']!='approved': continue
        if record.get('approved_transport',settings.llm_transport)!=settings.llm_transport:
            raise ValueError('本截图授权的调用方式已变化，请重新批准。')
        if record.get('destination')!=destination(settings): raise ValueError('LLM 供应商或模型已变化，截图需要重新批准。')
        image=resolve_image(job,record['image'])
        if digest(image)!=record['sha256']: raise ValueError('截图内容已变化，需要重新批准。')
        chunk=json.loads((job/'chunks'/f'{record["chunk"]}.evidence.json').read_text('utf-8'))
        base=(job/'chunks'/f'{record["chunk"]}.md').read_text('utf-8')
        # One image needs nearby speech and OCR, rather than every repeated
        # frame of a whole chunk. Retain the full text as context, capped to
        # keep visual review requests practical for API gateways.
        moment=record['time']
        chunk={**chunk,'speech':[s for s in chunk.get('speech',[]) if s['end']>=moment-30 and s['start']<=moment+30],
               'visuals':[v for v in chunk.get('visuals',[]) if abs(v['time']-moment)<=10]}
        anchor=base.find(record['visual_id'])
        base=base[max(0,anchor-2000):max(0,anchor-2000)+6000] if anchor>=0 else base[:6000]
        instructions=(RESOURCES/'skills/board-structure/SKILL.md').read_text('utf-8')
        notify('截图复核',record['id'])
        if settings.compact_notes:
            from .compact import pack,dumps
            chunk.setdefault('start',max(0,moment-30));chunk.setdefault('end',moment+30)
            compact=pack(chunk)[0]
            compact['visuals']=[v for v in compact['visuals'] if v['id']==record['visual_id'] or any(a[0]==record['visual_id'] for a in v.get('alternates',[]))]
            review_prompt=instructions+'\n复核问题：'+record['reason']+'\n相关文字：'+dumps(compact)
        else:
            review_prompt=instructions+'\n复核问题：'+record['reason']+'\n讲义：'+base+'\n证据：'+json.dumps(chunk,ensure_ascii=False)
        text=call(settings,review_prompt,[image],cancel=cancel)
        result=parse_json(text)
        if not isinstance(result.get('markdown'),str) or not result['markdown'].strip(): raise ValueError('视觉复核结果为空。')
        if 'formulas' in result or 'diagrams' in result:
            from .board_assets import materialize
            (job/'chunks'/f'{record["id"]}.structured-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
            board=materialize(job,record['id'],image,result)
            (job/'chunks'/f'{record["id"]}.board.md').write_text(board,'utf-8')
        (job/'chunks'/f'{record["id"]}.review.md').write_text(result['markdown'],'utf-8')
        if settings.compact_notes:
            (job/'chunks'/f'{record["id"]}.teaching-review.md').write_text(result['markdown'],'utf-8')
        # A long network call may overlap registration of later chunks. Reload
        # before updating so their new requests and decisions are retained.
        with transaction(path) as latest:
            match=next(r for r in latest if r['id']==record['id'])
            if match['status']!='approved' or match.get('destination')!=record.get('destination') or match['sha256']!=record['sha256']:
                raise ValueError('复核期间批准信息已变化，请重新核对。')
            match['status']='reviewed'
