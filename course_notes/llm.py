from __future__ import annotations
from .config import RESOURCES

import base64
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests
from .config import selected_provider


def endpoint(base, resource):
    return base.rstrip('/') + ('/' if base.rstrip('/').endswith('/v1') else '/v1/') + resource


def call(settings, prompt, images=(), cancel=None):
    """Images must be resolved by the approval gate, never by the model itself."""
    if settings and settings.llm_transport=='codex_cli':
        from .codex_cli import call_cli
        return call_cli(settings,prompt,images,cancel)
    p = selected_provider(settings)
    if p.wire_api == 'responses':
        content = [{'type': 'input_text', 'text': prompt}]
        for path in images:
            data = base64.b64encode(Path(path).read_bytes()).decode('ascii')
            content.append({'type':'input_image', 'image_url':'data:image/jpeg;base64,'+data})
        body = {'model':p.model, 'input':[{'role':'user','content':content}], 'max_output_tokens':getattr(settings,'llm_max_output_tokens',10000),'stream':True}
        if p.model.startswith(('gpt-5','gpt-6','o3','o4')): body['reasoning']={'effort':'low'}
        response = requests.post(endpoint(p.base_url,'responses'), headers={'Authorization':'Bearer '+p.key}, json=body, timeout=(30,1200))
    elif p.wire_api == 'anthropic':
        content = [{'type':'text','text':prompt}]
        for path in images:
            content.append({'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(Path(path).read_bytes()).decode('ascii')}})
        body = {'model':p.model,'max_tokens':getattr(settings,'llm_max_output_tokens',10000),'messages':[{'role':'user','content':content}]}
        response = requests.post(endpoint(p.base_url,'messages'),headers={'x-api-key':p.key,'anthropic-version':'2023-06-01'},json=body,timeout=(30,900))
    else:
        raise ValueError('不支持的 LLM 接口：'+p.wire_api)
    # Do not persist headers or credentials in diagnostics.
    response.encoding='utf-8'
    if response.status_code >= 400:
        detail=response.text[:1200]
        if '<html' in detail.lower() or '<!doctype' in detail.lower():
            detail='服务网关请求失败，请检查供应商状态后重试。'
        raise RuntimeError(f'LLM HTTP {response.status_code}: {detail}')
    try:
        data = response.json()
    except ValueError:
        # Some Responses gateways return SSE even without stream=true.
        events=[]; fragments=[]
        for line in response.text.splitlines():
            if line.startswith('data: ') and line[6:] != '[DONE]':
                try:
                    event=json.loads(line[6:]); events.append(event)
                    if event.get('type')=='response.output_text.delta': fragments.append(event.get('delta',''))
                except ValueError: pass
        complete=next((x.get('response') for x in reversed(events) if x.get('type')=='response.completed'),None)
        if not complete:
            raise RuntimeError('LLM 响应未完成；未保存为成功结果。')
        data=complete
    if data.get('status') in ('incomplete','failed','cancelled'):
        raise RuntimeError('LLM 响应未完整结束：'+str(data.get('status')))
    if p.wire_api=='anthropic':
        if data.get('stop_reason')=='max_tokens': raise RuntimeError('LLM 输出被截断，请减小片段时长。')
        text='\n'.join(x.get('text','') for x in data.get('content',[]) if x.get('type')=='text')
    else:
        text=data.get('output_text') or '\n'.join(x.get('text','') for o in data.get('output',[]) for x in o.get('content',[]) if x.get('type')=='output_text')
    if not text.strip(): raise RuntimeError('LLM 返回空文本。')
    if settings is not None:
        from .usage import record_usage
        record_usage('api',p.model,prompt,images,data.get('usage',{}))
    return text.strip()


def parse_json(text):
    if text.startswith('```'):
        text='\n'.join(text.splitlines()[1:-1])
    try: result=json.loads(text)
    except ValueError as e: raise ValueError('LLM 未返回完整 JSON，原始响应保留供重试。') from e
    if not isinstance(result,dict): raise ValueError('LLM 结果必须为 JSON 对象。')
    return result


def prompt(evidence, previous='', compact=False):
    if compact:
        from .compact import pack, dumps
        instructions=(RESOURCES/'skills/course-handout/compact.md').read_text('utf-8')
        return instructions+'\n材料：'+dumps(pack(evidence)[0])
    instructions=(RESOURCES/'skills/course-handout/SKILL.md').read_text('utf-8')
    return instructions+'\n\n前一片段末尾（仅上下文）：\n'+previous[-6000:]+'\n\n本片段证据 JSON：\n'+json.dumps(evidence,ensure_ascii=False)


def generate(evidence, settings, previous, notify, cancel=None):
    notify('讲义整合','发送带编号的文字证据；不发送截图')
    return call(settings,prompt(evidence,previous,settings.compact_notes),cancel=cancel)
