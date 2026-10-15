"""Isolated, non-interactive Codex CLI transport with no filesystem tools."""
from __future__ import annotations
import json,os,shutil,subprocess,tempfile,time,uuid
from contextlib import contextmanager
from pathlib import Path
from .config import ROOT,selected_provider
from .process import check_cancel

TEXT_SCHEMA={'type':'object','properties':{
    'markdown':{'type':'string'},
    'covered_speech_ids':{'type':'array','items':{'type':'string'}},
    'covered_visual_ids':{'type':'array','items':{'type':'string'}},
    'image_requests':{'type':'array','items':{'type':'object','properties':{'visual_id':{'type':'string'},'reason':{'type':'string'}},'required':['visual_id','reason'],'additionalProperties':False}}},
    'required':['markdown','covered_speech_ids','covered_visual_ids','image_requests'],'additionalProperties':False}
BBOX_SCHEMA={'type':'array','items':{'type':'number'},'minItems':4,'maxItems':4}
IMAGE_SCHEMA={'type':'object','properties':{
    'markdown':{'type':'string'},
    'formulas':{'type':'array','items':{'type':'object','properties':{'latex':{'type':'string'},'bbox':BBOX_SCHEMA,'confidence':{'type':'string','enum':['high','medium','low']},'uncertainty':{'type':'string'}},'required':['latex','bbox','confidence','uncertainty'],'additionalProperties':False}},
    'diagrams':{'type':'array','items':{'type':'object','properties':{'title':{'type':'string'},'bbox':BBOX_SCHEMA,'background':{'type':'string','enum':['dark','light','preserve']},'uncertainty':{'type':'string'}},'required':['title','bbox','background','uncertainty'],'additionalProperties':False}}},
    'required':['markdown','formulas','diagrams'],'additionalProperties':False}


def executable(settings):
    if settings.codex_executable:
        path=Path(settings.codex_executable)
        if not path.is_file(): raise FileNotFoundError('Codex CLI 路径不存在。')
        return str(path)
    npm=Path(os.environ.get('APPDATA',''))/'npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
    if npm.is_file(): return str(npm)
    found=shutil.which('codex.exe')
    if found: return found
    raise FileNotFoundError('没有找到 Codex CLI 原生程序，请安装 CLI 或设置 codex_executable。')


def validate_events(text):
    events=[json.loads(line) for line in text.splitlines() if line.strip()]
    terminal=[event for event in events if event.get('type') in ('turn.completed','turn.failed')]
    if terminal and terminal[-1]['type']=='turn.failed': raise RuntimeError('Codex CLI 回合失败。')
    for event in events:
        item=event.get('item',{})
        if item.get('type') not in (None,'agent_message','reasoning','error'):
            raise RuntimeError('Codex CLI 尝试调用工具，已拒绝此结果：'+str(item.get('type')))
    if not any(event.get('type')=='turn.completed' for event in events):
        raise RuntimeError('Codex CLI 未完整结束，不能作为成功结果。')


@contextmanager
def task_directory(settings,provider,cancel):
    if not settings.conversation_file:
        with tempfile.TemporaryDirectory(prefix='course-notes-cli-') as directory:yield Path(directory)
        return
    from .conversation import conversation
    with conversation(settings,provider,cancel) as session:
        directory=Path(settings.conversation_file).parent/'.codex-conversations'/session.key
        directory.mkdir(parents=True,exist_ok=True)
        yield directory


def command_for(binary,workspace,schema,response,thread_id='',persistent=False):
    command=[binary,'-C',str(workspace),'exec']
    if thread_id:command+=['resume',thread_id]
    command+=['--skip-git-repo-check','--json','--output-schema',str(schema),'-o',str(response)]
    if not persistent:command.append('--ephemeral')
    return command


def usage_delta(current,previous):
    return {key:max(0,value-previous.get(key,0)) if isinstance(value,(int,float)) else value for key,value in current.items()}


def call_cli(settings,prompt,images=(),cancel=None):
    p=selected_provider(settings)
    if p.app!='codex' or p.wire_api!='responses': raise ValueError('Codex CLI 方式需要选择 CC Switch 的 Codex Responses 配置。')
    binary=executable(settings);check_cancel(cancel) if cancel else None
    with task_directory(settings,p,cancel) as task:
        cli_home=task/'cli-home';cli_home.mkdir(exist_ok=True);workspace=task/'task';workspace.mkdir(exist_ok=True)
        config=f'''model = {json.dumps(p.model)}
model_provider = "course"
model_reasoning_effort = "low"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
project_doc_max_bytes = 0
suppress_unstable_features_warning = true
[model_providers.course]
name = "Course handout"
base_url = {json.dumps(p.base_url)}
env_key = "COURSE_NOTES_CODEX_KEY"
wire_api = "responses"
request_max_retries = 1
stream_max_retries = 1
[features]
shell_tool = false
unified_exec = false
view_image = false
shell_snapshot = false
apps = false
plugins = false
multi_agent = false
code_mode_host = false
browser_use = false
computer_use = false
image_generation = false
workspace_dependencies = false
skill_search = false
skip_host_skill_discovery = true
unbounded_connection_retries = false
'''
        (cli_home/'config.toml').write_text(config,'utf-8')
        schema=workspace/'schema.json';schema.write_text(json.dumps(IMAGE_SCHEMA if images else TEXT_SCHEMA),'utf-8')
        response=workspace/'response.json';trace=workspace/'events.jsonl';errors=workspace/'stderr.log'
        response.unlink(missing_ok=True)
        # Only the child process uses this isolated CLI configuration. No
        # user configuration or CC Switch credentials are written or modified.
        env={k:v for k,v in os.environ.items() if not k.startswith('CODEX_')}
        env['CODEX_HOME']=str(cli_home);env['COURSE_NOTES_CODEX_KEY']=p.key
        thread_path=task/'thread-id.txt'
        thread_id=thread_path.read_text('utf-8').strip() if thread_path.exists() else ''
        command=command_for(binary,workspace,schema,response,thread_id,bool(settings.conversation_file))
        for path in images: command.extend(['--image',str(Path(path).resolve())])
        command.append('-');started=time.monotonic()
        with trace.open('wb') as stdout,errors.open('wb') as stderr:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,env=env,cwd=workspace,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                process.stdin.write(prompt.encode('utf-8'));process.stdin.close()
                while process.poll() is None:
                    if cancel: check_cancel(cancel)
                    if time.monotonic()-started>settings.codex_timeout_seconds: raise TimeoutError('Codex CLI 超时，原始证据保留。')
                    time.sleep(.2)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill();process.wait()
        event_text=trace.read_text('utf-8',errors='replace').replace(p.key,'[REDACTED]')
        error_text=errors.read_text('utf-8',errors='replace').replace(p.key,'[REDACTED]')
        logs=ROOT/'cli-logs';logs.mkdir(exist_ok=True);identity=uuid.uuid4().hex
        (logs/f'{identity}.jsonl').write_text(event_text,'utf-8')
        (logs/f'{identity}.stderr.log').write_text(error_text,'utf-8')
        events=[json.loads(line) for line in event_text.splitlines() if line.strip()]
        started_thread=next((e.get('thread_id') for e in events if e.get('type')=='thread.started'),None)
        if settings.conversation_file and started_thread:thread_path.write_text(started_thread,'utf-8')
        if process.returncode: raise RuntimeError(f'Codex CLI 退出码 {process.returncode}：'+error_text[-1200:])
        validate_events(event_text)
        from .usage import record_usage
        usage=next((e.get('usage',{}) for e in reversed(events) if e.get('type')=='turn.completed'),{})
        if settings.conversation_file:
            # exec resume reports cumulative thread counters, not this turn's usage.
            usage_path=task/'usage-total.json'
            previous=json.loads(usage_path.read_text('utf-8')) if usage_path.exists() and started_thread==thread_id else {}
            total=usage
            usage=usage_delta(total,previous)
            usage_path.write_text(json.dumps(total),'utf-8')
        record_usage('codex_cli',p.model,prompt,images,usage)
        if not response.exists(): raise RuntimeError('Codex CLI 没有输出最终讲义。')
        text=response.read_text('utf-8')
        value=json.loads(text)
        if not isinstance(value.get('markdown'),str) or not value['markdown'].strip(): raise ValueError('Codex CLI 讲义正文为空。')
        return text
