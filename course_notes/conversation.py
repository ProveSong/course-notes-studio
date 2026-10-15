"""Durable ordered API conversations, isolated by video and destination.

Stateless APIs require replaying the exact prefix for prompt caching.
History is committed only after a complete successful response.
"""
import hashlib,json,os,threading,uuid
from pathlib import Path
from contextlib import contextmanager

_locks={}
_guard=threading.Lock()
HISTORY_CHARACTER_BUDGET=120000


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
        if settings and len(self.messages)>10 and text_size(self.messages)>HISTORY_CHARACTER_BUDGET:
            self.compact(settings,provider,cancel)

    def compact(self,settings,provider,cancel):
        from dataclasses import replace
        from .llm import _call,parse_json
        instructions=('Summarize this same course conversation for continuing later chunks. Return JSON with a single '
            'context_summary string in Chinese, at most 1800 Chinese characters. Preserve definitions, notation, '
            'assumptions, teacher terminology, unresolved questions, uncertainty, and where the course has reached. '
            'Treat OCR formulas as unverified unless reviewed. Do not invent facts. Original notes and complete '
            'evidence remain stored locally; this summary is context, not a replacement handout.')
        raw=_call(replace(settings,llm_max_output_tokens=2400),instructions,cancel=cancel,history=self.messages)
        summary=parse_json(raw).get('context_summary')
        if not isinstance(summary,str) or not summary.strip():raise ValueError('对话压缩没有返回有效课程上下文；原始历史保留。')
        number=len(self.row.get('compactions',[]))+1
        archive=self.path.with_name(f'{self.path.stem}.{self.key[:10]}.checkpoint-{number:03d}.json')
        archive.write_text(json.dumps({'conversation_id':self.row['id'],'destination':self.destination,
            'messages':self.messages,'summary':summary},ensure_ascii=False),'utf-8')
        content=[{'type':'text','text':summary}]
        assistant=content if provider.wire_api in ('deepseek_messages','anthropic') else summary
        note='Earlier course context was compacted in this same conversation. Full source history and teaching notes are saved locally. Continue the existing course; do not repeat earlier material.'
        tail=self.messages[-6:]
        while len(tail)>2 and text_size(tail)>HISTORY_CHARACTER_BUDGET//2:tail=tail[2:]
        self.messages=self.messages[:2]+[{'role':'user','content':note},{'role':'assistant','content':assistant}]+tail
        self.row.setdefault('compactions',[]).append({'archive':archive.name,'summary':summary})
        self.row['messages']=self.messages
        self.persist()

    def commit(self,user,answer):
        self.row['messages']=self.messages+[user,{'role':'assistant','content':[{'type':'text','text':answer}]}]
        if self.destination['protocol'] not in ('deepseek_messages','anthropic'):self.row['messages'][-1]['content']=answer
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
