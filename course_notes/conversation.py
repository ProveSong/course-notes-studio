"""Durable ordered API conversations, isolated by video and destination.

Stateless APIs require replaying the exact prefix for prompt caching.
History is committed only after a complete successful response.
"""
import hashlib,json,os,threading,uuid
from pathlib import Path
from contextlib import contextmanager

_locks={}
_guard=threading.Lock()


class Conversation:
    def __init__(self,path,provider):
        self.path=path
        self.destination={'provider':provider.identity,'base_url':provider.base_url,
                          'model':provider.model,'protocol':provider.wire_api}
        self.key=hashlib.sha256(json.dumps(self.destination,sort_keys=True).encode()).hexdigest()
        self.data=json.loads(path.read_text('utf-8')) if path.exists() else {'conversations':{}}
        self.row=self.data['conversations'].get(self.key,{'id':uuid.uuid4().hex,'destination':self.destination,'messages':[]})
        if self.row['destination']!=self.destination:raise ValueError('对话目的地不一致。')
        self.messages=self.row['messages']

    def commit(self,user,answer):
        self.row['messages']=self.messages+[user,{'role':'assistant','content':[{'type':'text','text':answer}]}]
        if self.destination['protocol'] not in ('deepseek_messages','anthropic'):self.row['messages'][-1]['content']=answer
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
        yield Conversation(path,provider)
    finally:lock.release()
