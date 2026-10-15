from __future__ import annotations
import json, math
from pathlib import Path
import cv2
from .process import check_cancel


def _time(seconds):
    return f'{int(seconds)//3600:02d}:{int(seconds)%3600//60:02d}:{int(seconds)%60:02d}'


def extract(video: Path, job: Path, settings, cancel, notify):
    out = job / 'visuals'; out.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened(): raise RuntimeError(f'无法打开视频：{video}')
    fps = cap.get(cv2.CAP_PROP_FPS) or 25; total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    previous = None; last_saved = -1e9; rows=[]; i=0
    # Seek to each scheduled sample instead of decoding every full-resolution
    # frame. Preserve every scheduled sample, including unchanged or blurry ones.
    t=0.0; duration=total/fps
    while t<duration:
        check_cancel(cancel); cap.set(cv2.CAP_PROP_POS_MSEC,t*1000); ok, frame = cap.read()
        if not ok: break
        small=cv2.resize(frame,(320,180)); gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        score=1.0 if previous is None else float(cv2.absdiff(gray,previous).mean()/255)
        if True:
            name=f'{int(t):07d}.jpg'; path=out/name
            ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,90])
            if not ok: raise RuntimeError('截图编码失败')
            path.write_bytes(encoded.tobytes())
            rows.append({'time':t,'timestamp':_time(t),'image':str(path.relative_to(job).as_posix()),'source':'video-frame','change_score':round(score,4)})
            last_saved=t; notify('画面采样', f'{_time(t)}，已保存 {len(rows)} 张')
        previous=gray
        t+=settings.sample_seconds
    cap.release(); (job/'visuals.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8'); return rows
