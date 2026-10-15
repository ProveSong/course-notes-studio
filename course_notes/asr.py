"""Standalone extraction of VideoCaptioner's local FasterWhisper command workflow.

Reference: app/core/bk_asr/faster_whisper.py in WEIFENG2333/VideoCaptioner.
No GUI, paid ASR, translation, subtitle optimization, or app imports are used.
"""
from __future__ import annotations
import re, json
from pathlib import Path
from .process import run_command


def parse_srt(text: str) -> list[dict]:
    segments = []
    def seconds(t):
        h,m,s,ms = re.split('[:,.]', t)
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000
    for block in re.split(r'\n\s*\n', text.replace('\r\n','\n').strip().lstrip('\ufeff')):
        lines = block.splitlines()
        match_index = next((i for i,l in enumerate(lines) if '-->' in l), None)
        if match_index is None:
            continue
        times = re.findall(r'\d{1,3}:\d{2}:\d{2}[,.]\d{3}', lines[match_index])
        if len(times) != 2:
            raise ValueError('字幕时间格式错误')
        start,end = map(seconds,times)
        content = '\n'.join(lines[match_index+1:]).strip()
        if end < start:
            raise ValueError('字幕结束时间早于开始时间')
        if content:
            segments.append({'start':start, 'end':end, 'text':content})
    if text.strip() and not segments:
        raise ValueError('字幕中没有有效的 SRT 时间段')
    return sorted(segments,key=lambda s:s['start'])


def transcribe(video: Path, job: Path, settings, cancel, notify):
    home = Path(settings.video_captioner)
    ffmpeg = home / 'resource/bin/ffmpeg.exe'
    exe = home / 'resource/bin/Faster-Whisper-XXL/faster-whisper-xxl.exe'
    model_dir = home / 'AppData/models'
    model = model_dir / f'faster-whisper-{settings.whisper_model}'
    for path in (ffmpeg, exe, model/'model.bin'):
        if not path.is_file():
            raise FileNotFoundError(f'本地语音组件不存在：{path}')
    wav = job / 'audio.wav'
    notify('语音识别', '提取 16 kHz 单声道音频')
    run_command([ffmpeg,'-y','-i',video,'-vn','-ac','1','-ar','16000',wav], job/'ffmpeg.log', cancel)
    notify('语音识别', f'运行本地 {settings.whisper_model} / {settings.device}，进度见 asr.log')
    # Match the installed VideoCaptioner adapter's supported flags. Pass the
    # existing model folder directly, so the binary cannot select another model.
    command = [exe, '-m', settings.whisper_model, '--model_dir', model_dir, wav, '-l',settings.language,
               '-d',settings.device, '--output_format','srt', '-o',job,
               '--vad_filter','true','--vad_threshold','0.40', '--one_word','0',
               '--sentence','--max_line_width','30','--max_line_count','1',
               '--max_comma','20','--max_comma_cent','50', '--beep_off']
    warning=None
    try:
        run_command(command,job/'asr.log',cancel,cwd=exe.parent)
    except RuntimeError as error:
        # This installed build can crash during teardown after exporting all
        # subtitles. Accept only a completed export covering the audio tail.
        log=(job/'asr.log').read_text('utf-8',errors='replace')
        srt=job/'audio.srt'
        if not srt.exists() or 'Subtitles are written to' not in log or 'Operation finished in:' not in log: raise
        import wave
        with wave.open(str(wav),'rb') as source: duration=source.getnframes()/source.getframerate()
        candidate=parse_srt(srt.read_text('utf-8-sig'))
        if not candidate or duration-candidate[-1]['end']>60: raise
        warning=str(error)+'；字幕已完整导出且覆盖音轨末尾，保留输出并记录退出异常。'
        notify('语音识别',warning)
    srt = job/'audio.srt'
    if not srt.is_file():
        raise RuntimeError('Whisper 未生成 audio.srt，请检查 asr.log')
    segments=parse_srt(srt.read_text('utf-8-sig'))
    (job/'asr-outcome.json').write_text(json.dumps({'segments':len(segments),'warning':warning},ensure_ascii=False,indent=2),'utf-8')
    return segments
