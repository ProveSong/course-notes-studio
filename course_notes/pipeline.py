from __future__ import annotations
from .config import RESOURCES
import hashlib, json, math, threading, traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
import cv2
from .config import Settings
from .asr import transcribe
from .visuals import extract, _time
from .ocr import annotate
from .llm import generate, parse_json, prompt, validate_handout, repair_handout
from .process import check_cancel
from .review import register, destination


def save_json(path, value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')


def assemble(job, target):
    manifest=json.loads((job/'manifest.json').read_text('utf-8'))
    evidence=json.loads((job/'evidence.json').read_text('utf-8'))
    expected=math.ceil(manifest['duration']/manifest.get('chunk_seconds',180))
    finished=len(list((job/'chunks').glob('C*.result.json')))
    if manifest.get('notes_style')=='teaching':
        sections=['# '+manifest['title']]
        seen_diagrams=set()
        for number in range(1,expected+1):
            chunk=job/'chunks'/f'C{number:04d}.md'
            if chunk.exists(): sections.append(chunk.read_text('utf-8'))
            corrections=[p.read_text('utf-8').strip() for p in sorted((job/'chunks').glob(f'C{number:04d}-*.teaching-review.md'))]
            corrections=list(dict.fromkeys(text for text in corrections if text))
            if corrections:sections.append('### 板书补正\n\n'+'\n\n'.join(corrections))
            for asset in sorted((job/'board-assets').glob(f'C{number:04d}-*/manifest.json')):
                data=json.loads(asset.read_text('utf-8'))
                for artifact in data.get('artifacts',[]):
                    if artifact.get('type')!='diagram':continue
                    title=data['analysis']['diagrams'][artifact['index']-1]['title']
                    image=job/artifact['white']
                    key=hashlib.sha256(image.read_bytes()).hexdigest()
                    if key in seen_diagrams:continue
                    seen_diagrams.add(key)
                    sections.append(f'![{title}]({artifact["white"]})')
        # Both source galleries and reviewed diagrams use job-relative paths.
        # Audit, transcripts and raw screenshot galleries stay in the job folder.
        text='\n\n'.join(sections)+'\n'
        text=text.replace('](board-assets/',f']({job.name}/board-assets/')
        text=text.replace('](visuals/',f']({job.name}/visuals/')
        target.write_text(text,'utf-8')
        return target
    sections=['# '+manifest['title'],
              f'> 讲义整合进度：{finished}/{expected} 个时间片段。'+('整段文字整合完成。' if finished==expected else '这是尚未完成的阶段输出。'),
              '> 依据课程语音转录与本地 OCR 逐段整理。含明确标注的模型补充。自动识别、画面采样可能遗漏信息，尚待人工核验。所有原始转录与画面索引附后。']
    if any((job/'chunks').glob('C*.review.md')):
        sections.append('> 各片段后的“经用户批准的截图复核”记录实际看图后的确认与修正。正文及附录保留了原始 OCR 的不确定读法；遇到同一画面的冲突，应结合对应复核说明阅读。复核仍可能有辨认错误。')
    if (job/'formula-gallery.html').is_file():
        sections.append(f'> [本地公式排版与原始裁剪核对页]({job.name}/formula-gallery.html)。图片清理结果、透明 PNG 与原始裁剪在对应片段内列出。')
    for number in range(1,expected+1):
        name=f'C{number:04d}'
        chunk=job/'chunks'/f'{name}.md'
        if (job/'chunks'/f'{name}.result.json').exists():
            sections.append(chunk.read_text('utf-8'))
        else:
            begin=(number-1)*manifest.get('chunk_seconds',180)
            sections.append(f'## {name} [{_time(begin)}–{_time(min(manifest["duration"],begin+manifest.get("chunk_seconds",180)))}]\n\n**本片段讲义尚未完成；原始转录和采样画面已保留在附录。**')
        reviews=sorted((job/'chunks').glob(name+'-*.review.md'))
        if reviews: sections.append('### 本片段经用户批准的截图复核\n\n'+'\n\n'.join(p.read_text('utf-8') for p in reviews))
        boards=sorted((job/'chunks').glob(name+'-*.board.md'))
        if boards: sections.extend(p.read_text('utf-8') for p in boards)
    requests=job/'review-requests.json'
    if requests.exists():
        pending=[r for r in json.loads(requests.read_text('utf-8')) if r['status']!='reviewed']
        if pending: sections.append('## 截图复核状态\n\n'+'\n'.join(f'- {r["id"]} [{_time(r["time"])}] {r["status"]}：{r["reason"]}' for r in pending))
    gap_notes=job/'gap-speech-notes.md'
    if gap_notes.exists(): sections.append(gap_notes.read_text('utf-8'))
    gap_path=job/'gap-speech.json'
    if gap_path.exists():
        gap_data=json.loads(gap_path.read_text('utf-8'))
        sections.append('## 未检出区间的第二次语音识别（待核听）\n\n使用本地 '+gap_data['model']+' 模型关闭语音活动过滤复核。以下内容可能重复、误识别或含静音幻觉，不作为已确认的老师原话。\n\n'+'\n\n'.join(f'[{_time(s["start"])}–{_time(s["end"])}] **{s["id"]}** {s["text"]}' for s in gap_data['segments']))
    sections.append('## 完整原始语音转录（含离题内容，未经人工校验）\n\n'+'\n\n'.join(f'[{_time(s["start"])}–{_time(s["end"])}] **{s["id"]}**\n\n{s["text"]}' for s in evidence['speech']))
    sections.append('## 全部画面与 OCR 索引\n\n'+'\n\n'.join(f'### {v["timestamp"]} {v["id"]}\n\n![课程画面 {v["timestamp"]}]({job.name}/{v["image"]})\n\n{v.get("ocr_text") or "[OCR 未辨认出文字，待核对原图]"}' for v in evidence['visuals']))
    sections.append('## 自动采集边界\n\n语音转录未检出区间见任务目录 `coverage.json`，不能据此认定区间内没有声音。视频按时间采样并保留全部采样画面，不代表逐帧检查了所有视觉变化。完整视频仍是最终依据。')
    # Prompt uses job-relative image paths. Correct them in the final document.
    text='\n\n'.join(sections)+'\n'
    text=text.replace('](visuals/',f']({job.name}/visuals/').replace('](assets/',f']({job.name}/visuals/')
    text=text.replace('](board-assets/',f']({job.name}/board-assets/')
    target.write_text(text,'utf-8')
    return target


def run(video: Path, output: Path, settings=None, notify=lambda a,b:None, cancel=None, auto_approve_images=False, resume_completed=False):
    settings=settings or Settings.load(); cancel=cancel or threading.Event(); video=video.resolve(); output=output.resolve()
    if not video.is_file(): raise FileNotFoundError(video)
    if settings.chunk_seconds<=0 or settings.sample_seconds<=0: raise ValueError('片段/采样间隔必须大于零。')
    if not 1<=settings.llm_workers<=8: raise ValueError('LLM 并发数量必须在 1 到 8 之间。')
    output.mkdir(parents=True,exist_ok=True); job=output/(video.stem+'_job'); job.mkdir(exist_ok=True)
    manifest_path=job/'manifest.json'
    signature={'video':str(video),'size':video.stat().st_size,'mtime_ns':video.stat().st_mtime_ns,
               'asr':{'model':settings.whisper_model,'language':settings.language,'device':settings.device},
               'visual':{'sample_seconds':settings.sample_seconds,'change_threshold':settings.change_threshold},'ocr':settings.ocr_mode}
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text('utf-8'))
        if old['signature']!=signature: raise ValueError('输入或识别参数已变化，请使用新的输出目录，避免复用旧证据。')
        if old.get('chunk_seconds',settings.chunk_seconds)!=settings.chunk_seconds:
            raise ValueError('分段时长已变化，请使用新的输出目录，避免混合不同时间范围的讲义。')
    from dataclasses import replace
    from .task_session import for_job
    settings=for_job(settings,job)
    cap=cv2.VideoCapture(str(video)); fps=cap.get(cv2.CAP_PROP_FPS); duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps; cap.release()
    target=output/(video.stem+('—课程讲解.md' if settings.compact_notes else '.md'))
    save_json(manifest_path,{'signature':signature,'title':video.stem,'duration':duration,'target':str(target),'destination':destination(settings),'chunk_seconds':settings.chunk_seconds,'notes_style':'teaching' if settings.compact_notes else 'evidence','conversation_file':settings.conversation_file,'conversation_video':settings.conversation_video})
    speech_path=job/'speech.json'
    speech=json.loads(speech_path.read_text('utf-8')) if speech_path.exists() else transcribe(video,job,settings,cancel,notify)
    speech=[{**s,'id':f'S{i:06d}'} for i,s in enumerate(speech,1)]; save_json(speech_path,speech)
    visual_path=job/'visuals.json'
    visuals=json.loads(visual_path.read_text('utf-8')) if visual_path.exists() else extract(video,job,settings,cancel,notify)
    ocr_path=job/'ocr.json'
    cached=json.loads(ocr_path.read_text('utf-8')) if ocr_path.exists() else []
    if len(cached)!=len(visuals): cached=annotate(visuals,job,settings,notify,cancel)
    if settings.formula_backend!='none':
        from .formulas import annotate_formulas
        cached=annotate_formulas(cached,job,settings,notify,cancel)
    visual=[{**v,'id':f'V{i:06d}'} for i,v in enumerate(cached,1)]; save_json(ocr_path,visual)
    evidence={'speech':speech,'visuals':visual}; save_json(job/'evidence.json',evidence)
    if auto_approve_images:
        from .review import grant_task_consent
        from .config import visual_settings
        grant_task_consent(job,visual_settings(settings),automatic=True)
    elif (job/'review-policy.json').exists():
        policy=json.loads((job/'review-policy.json').read_text('utf-8'))
        if policy.get('automatic'):(job/'review-policy.json').unlink()
    gaps=[]; end=0
    for s in speech:
        if s['start']-end>2: gaps.append({'start':end,'end':s['start'],'status':'ASR未检出，需人工核对'})
        end=max(end,s['end'])
    if duration-end>2: gaps.append({'start':end,'end':duration,'status':'ASR未检出，需人工核对'})
    save_json(job/'coverage.json',{'duration':duration,'speech_segments':len(speech),'visual_frames':len(visual),'asr_gaps':gaps,'claim':'保留全部采集证据，不保证原始视频零遗漏'})
    chunks=job/'chunks'; chunks.mkdir(exist_ok=True); previous=''
    instructions=(RESOURCES/'skills/course-handout/SKILL.md').read_text('utf-8')
    report=[]
    # Each chunk receives neighboring raw speech as context. This makes requests
    # independent and permits a small bounded pool without dropping prior facts.
    pool=ThreadPoolExecutor(max_workers=1)
    futures={}
    def context_for(start):
        return '\n'.join(f'[{_time(s["start"])}] {s["text"]}' for s in speech if start-600<=s['start']<start)[-6000:]
    def current_for(start,stop):
        return {'start':start,'end':stop,'speech':[s for s in speech if start<=s['start']<stop],
                'visuals':[v for v in visual if start<=v['time']<stop],
                'context_before':[s for s in speech if start-30<=s['start']<start],
                'context_after':[s for s in speech if stop<=s['start']<stop+30]}
    def fetch(current,context,name):
        check_cancel(cancel)
        actual_prompt=prompt(current,context,settings.compact_notes)
        fingerprint=hashlib.sha256(json.dumps([actual_prompt,destination(settings),settings.llm_transport,settings.llm_max_output_tokens],ensure_ascii=False).encode()).hexdigest()
        if settings.compact_notes:
            from .compact import pack
            _,audit=pack(current)
            audit.update(input_characters=len(actual_prompt),legacy_input_characters=len(prompt(current,context,False)))
            save_json(chunks/f'{name}.input-audit.json',audit)
        path=chunks/f'{name}.result.json'
        if path.exists():
            cache=json.loads(path.read_text('utf-8'))
            if cache.get('fingerprint')==fingerprint or (resume_completed and cache.get('destination')==destination(settings) and cache.get('transport')==settings.llm_transport):
                return cache['fingerprint'],None,cache['result']
        raw_path=chunks/f'{name}.response.txt'; fingerprint_path=chunks/f'{name}.response-fingerprint.txt'
        raw=None
        if raw_path.exists() and fingerprint_path.exists() and fingerprint_path.read_text('utf-8')==fingerprint:
            raw=raw_path.read_text('utf-8')
            try:
                validate_handout(raw)
                return fingerprint,raw,None
            except ValueError:pass
        import time
        last_error=''
        for attempt in range(3):
            check_cancel(cancel)
            try:
                if raw is not None:
                    import uuid
                    (chunks/f'{name}.invalid-{uuid.uuid4().hex[:8]}.txt').write_text(raw,'utf-8')
                    raw=repair_handout(settings,raw,cancel)
                else:
                    # DeepSeek thinking tokens share the Messages max_tokens
                    # budget. If a valid JSON answer is cut off, retry once
                    # with a larger budget while keeping the user's medium
                    # reasoning effort enabled and the same evidence scope.
                    from dataclasses import replace
                    retry_settings = settings
                    if attempt > 0 and 'max_tokens' in last_error:
                        retry_settings = replace(settings, llm_max_output_tokens=max(16000, settings.llm_max_output_tokens))
                    raw=generate(current,retry_settings,context,notify,cancel)
                validate_handout(raw)
                break
            except Exception as error:
                last_error=str(error)
                (chunks/f'{name}.error.txt').write_text(str(error),'utf-8')
                if attempt==2: raise
                check_cancel(cancel); notify('讲义整合',f'{name} 接口失败，重试 {attempt+1}/2'); time.sleep(2)
        (chunks/f'{name}.response.txt').write_text(raw,'utf-8')
        fingerprint_path.write_text(fingerprint,'utf-8')
        return fingerprint,raw,None
    succeeded=False
    try:
        for number,begin in enumerate(range(0,math.ceil(duration),settings.chunk_seconds),1):
            end=min(duration,begin+settings.chunk_seconds); name=f'C{number:04d}'
            futures[name]=pool.submit(fetch,current_for(begin,end),context_for(begin),name)
        for n,start in enumerate(range(0,math.ceil(duration),settings.chunk_seconds),1):
            check_cancel(cancel); stop=min(duration,start+settings.chunk_seconds); name=f'C{n:04d}'
            current={'start':start,'end':stop,'speech':[s for s in speech if start<=s['start']<stop],
                     'visuals':[v for v in visual if start<=v['time']<stop],
                     'context_before':[s for s in speech if start-30<=s['start']<start],
                     'context_after':[s for s in speech if stop<=s['start']<stop+30]}
            save_json(chunks/f'{name}.evidence.json',current)
            try:
                while True:
                    check_cancel(cancel)
                    try:
                        fingerprint,raw,result=futures[name].result(timeout=.5)
                        break
                    except FutureTimeout:
                        if futures[name].done(): raise
            except Exception:
                cancel.set(); pool.shutdown(wait=False,cancel_futures=True); raise
            path=chunks/f'{name}.result.json'
            if result is None:
                notify('讲义整合',f'{name} [{_time(start)}–{_time(stop)}]，{len(current["speech"])} 段发言 / {len(current["visuals"])} 张画面')
                try: result=parse_json(raw)
                except ValueError:
                    cancel.set(); pool.shutdown(wait=False,cancel_futures=True); raise
                if not isinstance(result.get('markdown'),str) or not result['markdown'].strip(): raise ValueError(name+' 正文为空。')
                if not isinstance(result.get('image_requests',[]),list): raise ValueError('截图请求格式错误')
                # Any unaccounted evidence is preserved explicitly, not silently dropped.
                missing_s=[] if settings.compact_notes else [s for s in current['speech'] if s['id'] not in result.get('covered_speech_ids',[]) or s['id'] not in result['markdown']]
                missing_v=[] if settings.compact_notes else [v for v in current['visuals'] if v['id'] not in result.get('covered_visual_ids',[]) or v['id'] not in result['markdown']]
                if missing_s or missing_v:
                    result['markdown']+='\n\n### 覆盖检查补入的原始证据（需进一步整理）\n\n'
                    result['markdown']+='\n\n'.join(f'[{_time(s["start"])}] **{s["id"]}** {s["text"]}' for s in missing_s)
                    result['markdown']+='\n\n'+'\n\n'.join(f'[{v["timestamp"]}] **{v["id"]}** ![原图]({v["image"]})\n\n{v.get("ocr_text") or "[待辨认]"}' for v in missing_v)
                result['coverage_fallback_speech']=[s['id'] for s in missing_s]; result['coverage_fallback_visual']=[v['id'] for v in missing_v]
                save_json(path,{'fingerprint':fingerprint,'result':result,'transport':settings.llm_transport,'destination':destination(settings)})
            (chunks/f'{name}.md').write_text(result['markdown'],'utf-8'); previous=result['markdown']
            register(job,name,result.get('image_requests',[]),current['visuals'])
            report.append({'chunk':name,'start':start,'end':stop,'speech':len(current['speech']),'visuals':len(current['visuals']),
                           'fallback_speech':result.get('coverage_fallback_speech',[]),'fallback_visual':result.get('coverage_fallback_visual',[])})
            save_json(job/'chunk-coverage.json',report)
            assemble(job,target)
        succeeded=True
    finally:
        if not succeeded: cancel.set()
        pool.shutdown(wait=succeeded,cancel_futures=True)
    if auto_approve_images:
        from .config import visual_settings
        from .review import process_approved
        process_approved(job,visual_settings(settings),notify,cancel)
        assemble(job,target)
    notify('完成',f'讲义已保存；检查 review-requests.json 中的截图复核申请：{job}')
    return target


def run_safe(video, output, settings, notify, cancel, auto_approve_images=False, resume_completed=False):
    try: return run(Path(video),Path(output),settings,notify,cancel,auto_approve_images,resume_completed)
    except Exception:
        Path(output).mkdir(parents=True,exist_ok=True); (Path(output)/'error.log').write_text(traceback.format_exc(),'utf-8'); raise
