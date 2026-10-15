"""Sequential video queue, independent output paths and durable result report."""
import hashlib,json,threading
from pathlib import Path
from dataclasses import replace
from .process import check_cancel,Cancelled
from .pipeline import run_safe

class LinkedCancel(threading.Event):
    def __init__(self,parent):super().__init__();self.parent=parent
    def is_set(self):return self.parent.is_set() or super().is_set()
    def wait(self,timeout=None):
        if self.parent.is_set():return True
        return super().wait(timeout) or self.parent.is_set()

def plan(videos,output):
    paths=list(dict.fromkeys(Path(v).resolve() for v in videos))
    counts={p.stem.casefold():sum(q.stem.casefold()==p.stem.casefold() for q in paths) for p in paths}
    return [(p,Path(output)/(p.stem+'-'+hashlib.sha256(str(p).encode()).hexdigest()[:8]) if counts[p.stem.casefold()]>1 else Path(output)) for p in paths]

def run_batch(videos,output,settings,notify,cancel,auto_approve_images=False,on_video=lambda *args:None):
    entries=plan(videos,output);report=[];Path(output).mkdir(parents=True,exist_ok=True)
    for index,(video,directory) in enumerate(entries,1):
        check_cancel(cancel);on_video(index,len(entries),video,directory)
        current=replace(settings)
        manifest=directory/(video.stem+'_job')/'manifest.json'
        try:
            if manifest.exists():current.chunk_seconds=json.loads(manifest.read_text('utf-8')).get('chunk_seconds',current.chunk_seconds)
            target=run_safe(video,directory,current,notify,LinkedCancel(cancel),auto_approve_images=auto_approve_images)
            row={'video':str(video),'status':'success','target':str(target),'job':str(directory/(video.stem+'_job'))}
        except Cancelled:raise
        except Exception as error:
            if cancel.is_set():raise
            row={'video':str(video),'status':'failed','error':str(error),'job':str(directory/(video.stem+'_job'))}
            notify('批量队列',f'{video.name} 失败，继续下一个视频：{error}')
        report.append(row)
        (Path(output)/'batch-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report
