"""Tool-free Messages calls using the vision wire format documented by DeepSeek Harness.

https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek
Images reach this adapter only through the existing consent gate.
"""
import base64
import json
import mimetypes
from pathlib import Path

import requests
from .process import check_cancel


def read_events(lines):
    data=[]
    for line in lines:
        if isinstance(line,bytes):line=line.decode('utf-8')
        if not line:
            if data:
                yield json.loads('\n'.join(data));data=[]
        elif line.startswith('data:'):data.append(line[5:].lstrip(' '))
    if data:raise RuntimeError('DeepSeek Messages 事件未完整结束。')


def user_message(provider,prompt,images):
    if images and provider.model!='deepseek-flash':
        raise ValueError('当前 DeepSeek 视觉适配支持 deepseek-flash；请更换截图模型。')
    content=[{'type':'text','text':prompt+'\n仅输出请求的 JSON 对象，不要代码围栏或额外说明。'}]
    encoded_size=0
    for path in images:
        path=Path(path)
        media=mimetypes.guess_type(path.name)[0]
        if media not in ('image/jpeg','image/png','image/webp','image/gif'):
            raise ValueError('不支持的截图格式。')
        data=base64.b64encode(path.read_bytes()).decode('ascii');encoded_size+=len(data)
        if encoded_size>20*1024*1024:raise ValueError('截图超过 20 MiB，请减少每次复核数量。')
        content.append({'type':'image','source':{'type':'base64','media_type':media,'data':data}})
    return {'role':'user','content':content}


def call_messages(settings, provider, prompt, images=(), cancel=None, history=()):
    from .llm import endpoint
    message=user_message(provider,prompt,images)
    if cancel:check_cancel(cancel)
    effort=settings.deepseek_reasoning_effort
    # Official effort mapping: medium -> high; the native tiers are low/high/max.
    mapped={'off':'off','low':'low','medium':'high','high':'high','max':'max'}.get(effort)
    if mapped is None:raise ValueError('未知 DeepSeek 思考强度。')
    body={'model':provider.model,'max_tokens':settings.llm_max_output_tokens,'stream':True,
          'thinking':{'type':'disabled' if mapped=='off' else 'enabled'},'messages':[*history,message]}
    if mapped!='off':body['output_config']={'effort':mapped}
    response=requests.post(endpoint(provider.base_url,'messages'),
        headers={'x-api-key':provider.key,'anthropic-version':'2023-06-01'},json=body,
        stream=True,allow_redirects=False,timeout=(30,120))
    try:
        response.encoding='utf-8'
        if response.status_code!=200:
            detail=response.text[:1000].replace(provider.key,'[REDACTED]')
            raise RuntimeError(f'DeepSeek Messages HTTP {response.status_code}: {detail}')
        blocks={};usage={};reason=None;stopped=False;started=False
        for event in read_events(response.iter_lines(decode_unicode=True)):
            if cancel:check_cancel(cancel)
            kind=event.get('type')
            if kind=='error':
                raise RuntimeError('DeepSeek Messages: '+json.dumps(event.get('error',{}),ensure_ascii=False).replace(provider.key,'[REDACTED]'))
            if kind=='message_start':
                started=True;usage.update(event.get('message',{}).get('usage',{}))
            elif kind=='content_block_start':
                block=event.get('content_block',{})
                if block.get('type') not in ('text','thinking','redacted_thinking'):
                    raise RuntimeError('DeepSeek 返回了未请求的工具或内容。')
                if block.get('type')=='text':blocks[event['index']]=block.get('text','')
            elif kind=='content_block_delta' and event.get('delta',{}).get('type')=='text_delta':
                index=event['index']
                if index not in blocks:raise RuntimeError('DeepSeek 文本事件顺序错误。')
                blocks[index]+=event['delta']['text']
            elif kind=='message_delta':
                reason=event.get('delta',{}).get('stop_reason',reason);usage.update(event.get('usage',{}))
            elif kind=='message_stop':stopped=True
        if not started or not stopped or reason!='end_turn':
            raise RuntimeError('DeepSeek Messages 输出未完整结束：'+str(reason))
        text='\n'.join(blocks[i] for i in sorted(blocks)).strip()
        if not text:raise RuntimeError('DeepSeek 返回空正文。')
        from .usage import record_usage
        record_usage('api',provider.model,prompt,images,usage)
        return text
    finally:response.close()
