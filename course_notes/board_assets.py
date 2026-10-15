"""Deterministic board crop/ink extraction; no network, no generative redraw."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
import cv2
import numpy as np


def read_image(path):
    value=cv2.imdecode(np.frombuffer(Path(path).read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
    if value is None:raise ValueError('无法读取板书原图。')
    return value


def write_image(path,image):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    ok,data=cv2.imencode(path.suffix,image)
    if not ok:raise ValueError('板书图片编码失败。')
    path.write_bytes(data.tobytes())


def crop_box(image,bbox):
    if not isinstance(bbox,list) or len(bbox)!=4 or any(type(v) not in (int,float) or not np.isfinite(v) for v in bbox):raise ValueError('bbox 必须为四个有限坐标。')
    left,top,right,bottom=bbox
    if not (0<=left<right<=1000 and 0<=top<bottom<=1000):raise ValueError('bbox 超出 0–1000 或为空。')
    h,w=image.shape[:2];x1=int(left*w/1000);y1=int(top*h/1000);x2=int(np.ceil(right*w/1000));y2=int(np.ceil(bottom*h/1000))
    if x2-x1<12 or y2-y1<12:raise ValueError('图形区域过小，无法可靠提取。')
    return image[y1:y2,x1:x2].copy(),[x1,y1,x2,y2]


def latex_warnings(latex):
    warnings=[];depth=0
    for token in re.findall(r'\\.|[{}]',latex):
        if token=='{':depth+=1
        elif token=='}':
            depth-=1
            if depth<0:break
    if depth!=0:warnings.append('LaTeX 花括号不平衡，保留原始候选供修正。')
    stack=[]
    for kind,name in re.findall(r'\\(begin|end)\{([^}]+)\}',latex):
        if kind=='begin':stack.append(name)
        elif not stack or stack.pop()!=name:warnings.append('LaTeX 环境不匹配。');break
    if stack:warnings.append('LaTeX 环境未结束。')
    if re.search(r'\\(?:input|include|write|catcode|def|href|url|html\w*)\b',latex):warnings.append('包含不适合公式展示的命令，仅显示候选文本。')
    if '$' in latex:warnings.append('公式字段不应含美元分隔符。')
    return warnings


def display_latex(latex):
    # Preserve circled step numbers using portable TeX rather than raw glyphs.
    value=re.sub('[①-⑳]',lambda match:r'\text{\textcircled{'+str(ord(match[0])-ord('①')+1)+'}}',latex)
    if len(re.findall(r'\\left\b',value))!=len(re.findall(r'\\right\b',value)):
        value=value.replace(r'\left.','').replace(r'\right.','')
        value=re.sub(r'\\(?:left|right|middle)\b','',value)
    return value


def extract_ink(crop,background):
    if background not in ('dark','light','preserve'):raise ValueError('未知背景类型。')
    if background=='preserve':return cv2.cvtColor(crop,cv2.COLOR_BGR2BGRA),crop.copy(),{'method':'preserve','warning':'复杂背景仅裁剪，未去背景。'}
    # Flatten slow illumination; no line fitting, gap filling or large closing.
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    size=min(61,max(15,(min(gray.shape)//12)|1));kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(size,size))
    signal=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT if background=='dark' else cv2.MORPH_BLACKHAT,kernel).astype(np.float32)
    peak=max(12.,float(np.percentile(signal,99.5)));floor=max(3.,min(10.,peak*.10))
    alpha=np.round(np.clip((signal-floor)/max(1.,peak-floor),0,1)**.80*255).astype(np.uint8)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    color=np.zeros_like(crop)
    # White chalk becomes dark ink; saturated colored marks keep their hue.
    board_hue=float(np.median(hsv[:,:,0]));distance=np.abs(hsv[:,:,0].astype(float)-board_hue);distance=np.minimum(distance,180-distance)
    colored=(hsv[:,:,1]>80)&((distance>18) if background=='dark' else True)
    color[colored]=np.minimum(crop[colored].astype(np.float32)*.65,180).astype(np.uint8)
    transparent=np.dstack([color,alpha])
    weight=alpha[:,:,None].astype(np.float32)/255
    white=np.round(color*weight+255*(1-weight)).astype(np.uint8)
    ratio=float(np.mean(alpha>40))
    warning='局部去背景可能削弱淡笔迹或保留擦痕；请与原始裁剪核对。'
    if ratio<.002 or ratio>.65:warning+=' 检测到异常笔迹占比，须人工检查背景模式或裁剪区域。'
    return transparent,white,{'method':'local-morphological-ink','kernel':size,'contrast_peak':peak,'noise_floor':floor,'ink_ratio':ratio,'warning':warning}


def materialize(job,identity,image,analysis):
    job=Path(job).resolve();image=Path(image).resolve()
    if not re.fullmatch(r'C\d{4}-V\d{6}',identity):raise ValueError('无效板书编号。')
    source=read_image(image);out=job/'board-assets'/identity;out.mkdir(parents=True,exist_ok=True)
    moment=''
    requests=job/'review-requests.json'
    if requests.exists():
        record=next((r for r in json.loads(requests.read_text('utf-8')) if r['id']==identity),None)
        if record:
            seconds=int(record['time']);moment=f'[{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}] '
    artifacts=[];sections=['### 公式结构与板书图形（基于已批准原图）',f'来源：{moment}**{identity}**。原始笔迹清理不等于数学纠错；无法辨认部分保留不确定标记。']
    if analysis.get('markdown'):sections.append(analysis['markdown'])
    for n,formula in enumerate(analysis.get('formulas',[]),1):
        latex=formula.get('latex','')
        if not isinstance(latex,str) or not latex.strip():continue
        crop,pixels=crop_box(source,formula['bbox']);write_image(out/f'formula-{n:02}-source.png',crop)
        normalized=display_latex(latex);warnings=latex_warnings(normalized)
        display=('```text\n'+latex.replace('```','` ` `')+'\n```\n\n'+' '.join(warnings)) if warnings else '$$\n'+normalized+'\n$$'
        sections.append(f'公式 {n}（置信度 {formula.get("confidence","unknown")}；区域 {formula["bbox"]}）：\n\n'+display+'\n\n'+str(formula.get('uncertainty',''))+f'\n\n![公式原始裁剪](board-assets/{identity}/formula-{n:02}-source.png)')
        if normalized!=latex:sections.append('展示兼容调整：圈号改用 TeX 表示，或移除不成对的定界符尺寸命令；未补写数学内容。原始 LaTeX 候选保留在本条 manifest.json。')
        artifacts.append({'type':'formula','index':n,'bbox_pixels':pixels,'display_latex':normalized,'syntax_warnings':warnings,'source_crop':f'board-assets/{identity}/formula-{n:02}-source.png'})
    for n,diagram in enumerate(analysis.get('diagrams',[]),1):
        crop,pixels=crop_box(source,diagram['bbox']);transparent,white,parameters=extract_ink(crop,diagram['background'])
        prefix=f'diagram-{n:02}';write_image(out/f'{prefix}-source.png',crop);write_image(out/f'{prefix}-transparent.png',transparent);write_image(out/f'{prefix}-white.png',white)
        relative=f'board-assets/{identity}/{prefix}'
        sections.append(str(diagram.get('title',f'图形 {n}'))+'\n\n'+f'![清理后的板书图形]({relative}-white.png)\n\n[透明 PNG]({relative}-transparent.png) · [原始裁剪]({relative}-source.png)\n\n'+str(diagram.get('uncertainty',''))+' '+parameters['warning'])
        artifacts.append({'type':'diagram','index':n,'bbox_pixels':pixels,'transparent':relative+'-transparent.png','white':relative+'-white.png','parameters':parameters})
    if not artifacts:sections.append('本次原图未定位到可可靠结构化的公式或可提取图形；参见复核说明。')
    skill=Path(__file__).parents[1]/'skills/board-structure/SKILL.md'
    manifest={'identity':identity,'source_image':image.relative_to(job).as_posix(),'source_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'skill_sha256':hashlib.sha256(skill.read_bytes()).hexdigest(),'renderer_version':2,'analysis':analysis,'artifacts':artifacts}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    return '\n\n'.join(sections)
