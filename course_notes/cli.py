from __future__ import annotations
import argparse, threading
from pathlib import Path
from .config import ROOT, Settings, available_providers,visual_settings
from .pipeline import run


def main():
    ap=argparse.ArgumentParser(description='课程回放 → 证据包 → Markdown 讲义')
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('run'); p.add_argument('video',type=Path,nargs='+'); p.add_argument('-o','--output',type=Path,default=Path('lectures')); p.add_argument('--model'); p.add_argument('--device',choices=['cuda','cpu']); p.add_argument('--provider')
    p.add_argument('--auto-approve-images',action='store_true',help='本次运行自动批准全部视频任务请求的截图')
    p.add_argument('--ocr-mode',choices=['printed','handwritten'])
    p.add_argument('--sample-seconds',type=float); p.add_argument('--chunk-seconds',type=int)
    p.add_argument('--llm-transport',choices=['api','codex_cli']);p.add_argument('--codex-executable')
    p.add_argument('--formula-backend',choices=['paddle','none']);p.add_argument('--legacy-evidence',action='store_true')
    r=sub.add_parser('review',help='列出或批准特定截图后执行视觉复核'); r.add_argument('job',type=Path)
    r.add_argument('--approve',nargs='+',metavar='REQUEST_ID'); r.add_argument('--deny',nargs='+',metavar='REQUEST_ID'); r.add_argument('--process',action='store_true');r.add_argument('--approve-all',action='store_true')
    b=sub.add_parser('board',help='对已批准截图结构化公式、提取去背景图形');b.add_argument('job',type=Path)
    sub.add_parser('providers'); sub.add_parser('init')
    a=ap.parse_args(); s=Settings.load()
    if a.cmd=='providers':
        for x in available_providers(s): print(x.identity,'\t',x.label,'\t',x.base_url)
    elif a.cmd=='init': s.save(); print('已写入',ROOT/'settings.json')
    elif a.cmd=='board':
        s=visual_settings(s)
        import json
        from .board import process
        from .pipeline import assemble
        process(a.job,s,lambda stage,msg:print(stage,msg,flush=True),threading.Event())
        manifest=json.loads((a.job/'manifest.json').read_text('utf-8'));assemble(a.job,Path(manifest['target']))
    elif a.cmd=='review':
        s=visual_settings(s)
        import json
        from .review import decide, process_approved, destination
        from .pipeline import assemble
        if a.approve and a.deny: raise ValueError('批准和拒绝请分开执行。')
        if a.approve_all:
            if a.deny:raise ValueError('不能同时批准全部和拒绝。')
            from .review import grant_task_consent
            grant_task_consent(a.job,s,automatic=True)
        if a.approve: decide(a.job,a.approve,s,True)
        if a.deny: decide(a.job,a.deny,s,False)
        if a.process: process_approved(a.job,s,lambda stage,msg: print(stage,msg),threading.Event())
        path=a.job/'review-requests.json'
        print('截图发送目的地：',destination(s))
        if path.exists():
            for record in json.loads(path.read_text('utf-8')): print(record['id'],record['status'],record['image'],record['reason'])
        manifest=json.loads((a.job/'manifest.json').read_text('utf-8')); assemble(a.job,Path(manifest['target']))
    else:
        if a.model: s.model=a.model
        if a.device: s.device=a.device
        if a.provider: s.provider=a.provider
        if a.ocr_mode: s.ocr_mode=a.ocr_mode
        if a.sample_seconds: s.sample_seconds=a.sample_seconds
        if a.chunk_seconds: s.chunk_seconds=a.chunk_seconds
        if a.llm_transport: s.llm_transport=a.llm_transport
        if a.codex_executable: s.codex_executable=a.codex_executable
        if a.formula_backend:s.formula_backend=a.formula_backend
        if a.legacy_evidence:s.compact_notes=False
        if s.provider=='deepseek:direct':s.llm_transport='api'
        from .batch import run_batch
        results=run_batch(a.video,a.output,s,lambda stage,msg:print(f'[{stage}] {msg}',flush=True),threading.Event(),a.auto_approve_images,
                          lambda index,total,video,directory:print(f'队列 {index}/{total}：{video}',flush=True))
        for result in results:print(result)
        if any(r['status']=='failed' for r in results):raise SystemExit(1)
