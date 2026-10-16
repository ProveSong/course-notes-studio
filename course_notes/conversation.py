"""Durable ordered API conversations, isolated by task and destination.

Stateless APIs require replaying the exact prefix for prompt caching.
History is committed only after a complete successful response.
"""
import copy,hashlib,json,os,threading,uuid
from pathlib import Path
from contextlib import contextmanager

_locks={}
_guard=threading.Lock()
HISTORY_CHARACTER_BUDGET=32000


def split_instructions(prompt):
    for marker in ('\n材料：','\n复核问题：','\n问题：'):
        if marker in prompt:
            prefix,body=prompt.split(marker,1)
            return prefix,marker+body
    return '',prompt


def economical_history(messages):
    """Keep originals locally. Replay each rule once and never replay old images."""
    result=copy.deepcopy(messages);seen=set();last_video=''
    def text(value):
        prefix,body=split_instructions(value)
        if not prefix:return value
        # These turns already have a complete answer below. The old raw OCR,
        # speech and formula proposals add no new evidence to the next request.
        # Keep their answers for continuity and the full inputs in local history.
        if body.startswith('\n材料：'):
            try:
                evidence=json.loads(body[len('\n材料：'):].strip())
                interval=f'{evidence.get("start", "?")}–{evidence.get("end", "?")} 秒'
            except (ValueError,AttributeError):interval='此前片段'
            body='\n材料：'+interval+'已处理，完整证据在本地；下方为已生成讲义。'
        elif '\n相关文字：' in body:
            body=body.split('\n相关文字：',1)[0]+'\n相关材料和原图已处理，保存在本地。'
        if prefix in seen:return body.lstrip('\n')
        seen.add(prefix)
        return prefix+body
    for message in result:
        video=message.pop('task_video','')
        content=message.get('content','')
        if isinstance(content,str):
            if message['role']=='user':message['content']=text(content)
        else:
            blocks=[]
            for block in content:
                if block.get('type') in ('image','input_image'):
                    continue
                if message['role']=='user' and block.get('type') in ('text','input_text'):
                    block['text']=text(block.get('text',''))
                blocks.append(block)
            message['content']=blocks or [{'type':'text','text':'此前已处理的截图；原图保留在本地。'}]
        if video and video!=last_video and message['role']=='user':
            label=f'任务视频：{video}。\n'
            if isinstance(message['content'],str):message['content']=label+message['content']
            else:message['content'].insert(0,{'type':'text','text':label})
            last_video=video
    return result,seen


def text_size(messages):
    count=0
    for message in messages:
        content=message.get('content','')
        if isinstance(content,str):count+=len(content)
        else:
            for block in content:
                count+=len(block.get('text','')) if block.get('type') in ('text','input_text') else 2400
    return count


class Conversation:
    def __init__(self,path,provider,settings=None,cancel=None):
        self.path=path
        self.destination={'provider':provider.identity,'base_url':provider.base_url,
                          'model':provider.model,'protocol':provider.wire_api}
        self.key=hashlib.sha256(json.dumps(self.destination,sort_keys=True).encode()).hexdigest()
        self.data=json.loads(path.read_text('utf-8')) if path.exists() else {'conversations':{}}
        self.row=self.data['conversations'].get(self.key,{'id':uuid.uuid4().hex,'destination':self.destination,'messages':[]})
        if self.row['destination']!=self.destination:raise ValueError('对话目的地不一致。')
        self.messages=self.row['messages']
        if settings and len(self.messages)>2 and text_size(economical_history(self.messages)[0])>HISTORY_CHARACTER_BUDGET:
            self.compact(settings,provider,cancel)

    def request(self,prompt,video=''):
        history,seen=economical_history(self.messages)
        prefix,body=split_instructions(prompt)
        current=body.lstrip('\n') if prefix and prefix in seen else prompt
        if video and video!=self.row.get('current_video'):
            current=f'本任务当前视频：{video}。只整理当前视频证据；此前视频仅供术语衔接，不混入未讲内容。\n'+current
        return history,current

    def compact(self,settings,provider,cancel):
        from dataclasses import replace
        from .llm import _call,parse_json
        instructions=('Summarize this same task conversation for continuing later videos and chunks. Return JSON with a single '
            'context_summary string in Chinese, at most 1800 Chinese characters. Preserve definitions, notation, '
            'assumptions, teacher terminology, unresolved questions, uncertainty, and where the course has reached. '
            'Treat OCR formulas as unverified unless reviewed. Do not invent facts. Original notes and complete '
            'evidence remain stored locally; this summary is context, not a replacement handout.')
        history=economical_history(self.messages)[0]
        raw=_call(replace(settings,llm_max_output_tokens=2400),instructions,cancel=cancel,history=history)
        summary=parse_json(raw).get('context_summary')
        if not isinstance(summary,str) or not summary.strip():raise ValueError('对话压缩没有返回有效课程上下文；原始历史保留。')
        number=len(self.row.get('compactions',[]))+1
        archive=self.path.with_name(f'{self.path.stem}.{self.key[:10]}.checkpoint-{number:03d}.json')
        archive.write_text(json.dumps({'conversation_id':self.row['id'],'destination':self.destination,
            'messages':self.messages,'summary':summary},ensure_ascii=False),'utf-8')
        content=[{'type':'text','text':summary}]
        assistant=content if provider.wire_api in ('deepseek_messages','anthropic') else summary
        # Preserve task rules, not the first chunk's entire raw evidence forever.
        rules=[]
        for message in history:
            if message['role']!='user':continue
            c=message.get('content','')
            texts=[c] if isinstance(c,str) else [b.get('text','') for b in c]
            for value in texts:
                prefix,_=split_instructions(value)
                if prefix and prefix not in rules:rules.append(prefix)
        note='同一任务的早期上下文已压缩；完整原文和讲义保存在本地。视频内容分别整理，不重复输出旧讲义。\n'+'\n'.join(rules)
        tail=history[-4:]
        while tail and text_size(tail)>HISTORY_CHARACTER_BUDGET//3:tail=tail[2:]
        self.messages=[{'role':'user','content':note},{'role':'assistant','content':assistant}]+tail
        self.row.setdefault('compactions',[]).append({'archive':archive.name,'summary':summary})
        self.row['messages']=self.messages
        self.persist()

    def commit(self,user,answer,video=''):
        if video:user=dict(user,task_video=video)
        self.row['messages']=self.messages+[user,{'role':'assistant','content':[{'type':'text','text':answer}]}]
        if self.destination['protocol'] not in ('deepseek_messages','anthropic'):self.row['messages'][-1]['content']=answer
        if video:self.row['current_video']=video
        self.persist()

    def persist(self):
        self.data['conversations'][self.key]=self.row
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary.write_text(json.dumps(self.data,ensure_ascii=False,separators=(',',':')),'utf-8')
        os.replace(temporary,self.path)


@contextmanager
def conversation(settings,provider,cancel=None):
    from .process import check_cancel
    path=Path(settings.conversation_file).resolve()
    with _guard:lock=_locks.setdefault(str(path),threading.Lock())
    while not lock.acquire(timeout=.2):
        if cancel:check_cancel(cancel)
    try:
        if cancel:check_cancel(cancel)
        yield Conversation(path,provider,settings,cancel)
    finally:lock.release()
