"""Deterministic prompt-only cleanup; original OCR and speech stay untouched."""
import re


def line_key(value):
    # Chinese OCR inserts spaces inside words. Keep Latin/unit spacing: m s
    # and ms can represent different dimensions and must not be merged.
    value=re.sub(r'\s+',' ',value).strip()
    return re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',value)


def clean_text(text):
    lines=[]
    for value in str(text).splitlines():
        line=value.strip()
        if not line:continue
        normalized=re.sub(r'[\s。.!！?？,，、：:]+','',line)
        if normalized in {'继续播放','不知道','继续播放不知道'}:continue
        # A fixed video watermark can be split across OCR regions or appended
        # to real teaching text. Remove only the identifiable boilerplate span.
        line=re.sub(r'课堂教学视频受?知识产权保护.*$','',line).strip()
        if re.fullmatch(r'[，,。.!！\s]*(?:违者追究法律责任|不得翻录转载|未经[^，,。!！]{1,45}[授报]权[，,]?不得翻录转载)[!！。.,，\s]*',line):continue
        if re.fullmatch(r'(?:版权所有|版权归.*所有|Copyright\s*©?\s*\d{4}.*|All rights reserved[.。]?)',line,re.I):continue
        if line:lines.append(line)
    return '\n'.join(lines)


def clean_visual(item):
    """Geometry-backed player chrome removal, never a short-word blacklist."""
    regions=item.get('ocr_regions',[])
    # Use regions only when they account for every source line. Otherwise the
    # text-only fallback must retain content absent from incomplete geometry.
    source=[s.strip() for s in item.get('ocr_text','').splitlines() if s.strip()]
    region_text=[str(r.get('text','')).strip() for r in regions if str(r.get('text','')).strip()]
    use_regions=source==region_text and bool(regions)
    clock=any(re.fullmatch(r'\d{1,2}[:：]\d{2}',str(r.get('text','')).strip())
              and len(r.get('bbox',[]))==4 and r['bbox'][0]>=700 and r['bbox'][1]<50 for r in regions)
    emblem=any(str(r.get('text','')).strip()=='1898' and len(r.get('bbox',[]))==4
               and r['bbox'][0]<125 and r['bbox'][3]<165 for r in regions)
    filtered=[];kept=[];seen=set()
    values=regions if use_regions else [{'text':s} for s in source]
    for index,region in enumerate(values):
        raw=str(region.get('text',''));box=region.get('bbox',[])
        reason=''
        if use_regions and len(box)==4:
            if clock and box[0]>=740 and box[1]<90 and box[3]<110:reason='player-overlay'
            elif emblem and box[0]<125 and box[3]<165 and (raw.strip()=='1898' or len(raw.strip())<=2):reason='institution-emblem'
        text=clean_text(raw)
        if not text:reason=reason or 'watermark-or-empty'
        if reason:
            filtered.append({'line':index,'reason':reason})
            continue
        for line in text.splitlines():
            key=line_key(line)
            if key in seen:
                filtered.append({'line':index,'reason':'duplicate-line'})
                continue
            seen.add(key);kept.append(line)
    return '\n'.join(kept),filtered
