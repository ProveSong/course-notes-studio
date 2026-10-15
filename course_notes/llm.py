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
    if settings and settings.conversation_file and (settings.llm_transport=='api' or settings.provider=='deepseek:direct'):
        from .conversation import conversation
        p=selected_provider(settings)
        with conversation(settings,p,cancel) as session:
            result=_call(settings,prompt,images,cancel,session.messages)
            if p.wire_api=='deepseek_messages':
                from .deepseek_messages import user_message
                message=user_message(p,prompt,images)
            elif p.wire_api in ('responses','anthropic'):
                if p.wire_api=='responses':
                    content=[{'type':'input_text','text':prompt}]
                    for path in images:content.append({'type':'input_image','image_url':'data:image/jpeg;base64,'+base64.b64encode(Path(path).read_bytes()).decode('ascii')})
                else:
                    content=[{'type':'text','text':prompt}]
                    for path in images:content.append({'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(Path(path).read_bytes()).decode('ascii')}})
                message={'role':'user','content':content}
            else:message={'role':'user','content':prompt}
            session.commit(message,result)
            return result
    return _call(settings,prompt,images,cancel)


def _call(settings, prompt, images=(), cancel=None, history=()):
    """Images must be resolved by the approval gate, never by the model itself."""
    if settings and settings.llm_transport=='codex_cli' and settings.provider!='deepseek:direct':
        from .codex_cli import call_cli
        return call_cli(settings,prompt,images,cancel)
    p = selected_provider(settings)
    if p.wire_api=='deepseek_messages':
        from .deepseek_messages import call_messages
        return call_messages(settings,p,prompt,images,cancel,history)
    if p.wire_api=='chat_completions':
        if images:raise ValueError('DeepSeek 文字 API 不支持截图；请使用单独配置的视觉模型。')
        body={'model':p.model,'messages':[*history,{'role':'user','content':prompt}],
              'response_format':{'type':'json_object'},'max_tokens':min(getattr(settings,'llm_max_output_tokens',8192),8192),'stream':False}
        response=requests.post(endpoint(p.base_url,'chat/completions'),headers={'Authorization':'Bearer '+p.key},json=body,timeout=(30,1200))
    elif p.wire_api == 'responses':
        content = [{'type': 'input_text', 'text': prompt}]
        for path in images:
            data = base64.b64encode(Path(path).read_bytes()).decode('ascii')
            content.append({'type':'input_image', 'image_url':'data:image/jpeg;base64,'+data})
        body = {'model':p.model, 'input':[*history,{'role':'user','content':content}], 'max_output_tokens':getattr(settings,'llm_max_output_tokens',10000),'stream':True}
        if p.model.startswith(('gpt-5','gpt-6','o3','o4')): body['reasoning']={'effort':'low'}
        response = requests.post(endpoint(p.base_url,'responses'), headers={'Authorization':'Bearer '+p.key}, json=body, timeout=(30,1200))
    elif p.wire_api == 'anthropic':
        content = [{'type':'text','text':prompt}]
        for path in images:
            content.append({'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(Path(path).read_bytes()).decode('ascii')}})
        body = {'model':p.model,'max_tokens':getattr(settings,'llm_max_output_tokens',10000),'messages':[*history,{'role':'user','content':content}]}
        response = requests.post(endpoint(p.base_url,'messages'),headers={'x-api-key':p.key,'anthropic-version':'2023-06-01'},json=body,timeout=(30,900))
    else:
        raise ValueError('不支持的 LLM 接口：'+p.wire_api)
    # Do not persist headers or credentials in diagnostics.
    response.encoding='utf-8'
    if response.status_code >= 400:
        detail=response.text[:1200]
        if '<html' in detail.lower() or '<!doctype' in detail.lower():
            detail='服务网关请求失败，请检查供应商状态后重试。'
        raise RuntimeError(f'LLM HTTP {response.status_code}: {detail.replace(p.key,"[REDACTED]")}')
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
    if p.wire_api=='chat_completions':
        choices=data.get('choices',[])
        if not choices or choices[0].get('finish_reason')!='stop':raise RuntimeError('DeepSeek 输出未完整结束，请减小片段时长或调整输出预算。')
        text=choices[0].get('message',{}).get('content','') or ''
    elif p.wire_api=='anthropic':
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


def validate_handout(text):
    result=parse_json(text)
    markdown=result.get('markdown')
    if not isinstance(markdown,str) or not markdown.strip():raise ValueError('讲义正文为空。')
    if any(ord(c)<32 and c not in '\n\r\t' for c in markdown):raise ValueError('讲义含错误转义的控制字符。')
    if '\n' not in markdown and markdown.count(r'\n')>=2:raise ValueError('讲义换行被重复转义。')
    if not isinstance(result.get('image_requests',[]),list):raise ValueError('截图请求格式错误。')
    return result


def repair_handout(settings,raw,cancel=None):
    return call(settings,'修复下面课程讲义的 JSON 编码。只返回一个合法 JSON 对象，不加代码围栏。'
        '保留原文内容和 image_requests，不增删教学内容。markdown 解码后必须有真正的换行；'
        'LaTeX 的反斜杠在 JSON 字符串中须正确转义，避免控制字符和重复转义。原响应：\n'+raw,cancel=cancel)


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
