"""One durable conversation for a whole task; evidence remains in video jobs."""
import hashlib,json
from dataclasses import replace
from pathlib import Path


def batch_settings(entries,output,settings):
    if settings.conversation_file:
        return replace(settings)
    identity=hashlib.sha256(json.dumps([str(v) for v,_ in entries],ensure_ascii=False).encode()).hexdigest()[:24]
    path=Path(output).resolve()/'.task-conversations'/f'{identity}.json'
    if not path.exists():
        # Continue the last used legacy conversation, not ten concatenated histories.
        # No network call and no change to the original files or provenance.
        from .config import selected_provider
        from .conversation import Conversation
        try:provider=selected_provider(settings)
        except (ValueError,FileNotFoundError):provider=None
        if provider:
            key=Conversation(path,provider).key
            for video,directory in reversed(entries):
                legacy=directory/(video.stem+'_job')/'deepseek-conversation.json'
                if not legacy.exists():continue
                data=json.loads(legacy.read_text('utf-8'))
                row=data.get('conversations',{}).get(key)
                if not row:continue
                row=dict(row,migrated_from=str(legacy))
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'conversations':{key:row}},ensure_ascii=False),'utf-8')
                temporary.replace(path)
                break
    return replace(settings,conversation_file=str(path))


def for_job(settings,job):
    """Manual review and retries use the same task session recorded locally."""
    manifest=Path(job)/'manifest.json'
    data=json.loads(manifest.read_text('utf-8')) if manifest.exists() else {}
    return replace(settings,
        conversation_file=settings.conversation_file or data.get('conversation_file') or str(Path(job)/'deepseek-conversation.json'),
        conversation_video=settings.conversation_video or data.get('conversation_video','video-1'))
