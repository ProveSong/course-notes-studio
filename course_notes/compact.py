"""Source storage stays separate from the small teaching prompt."""
import re
import json

VERSION = 'compact-2'


def formula_candidate(formula):
    value={k:formula[k] for k in ('latex','bbox','status','confidence','uncertainty','syntax_warnings') if k in formula and formula[k]}
    latex=str(formula.get('latex',''))
    if formula.get('status')=='candidate-unverified' and (formula.get('syntax_warnings') or re.search(r'(.{4,100}?)\1{5,}',latex)):
        value.pop('latex',None);value.pop('syntax_warnings',None)
        value.update(status='needs-visual-review')
    elif value.get('status')=='candidate-unverified':
        # The prompt already states all local candidates are unverified.
        value.pop('status')
    return value


def clean_text(text):
    lines = []
    for line in str(text).splitlines():
        normalized = re.sub(r'[\s。.!！?？,，、：:]+', '', line)
        if normalized in {'继续播放', '不知道', '继续播放不知道'}:
            continue
        if re.fullmatch(r'(?:版权所有|版权归.*所有|Copyright\s*©?\s*\d{4}.*|All rights reserved[.。]?)', line.strip(), re.I):
            continue
        lines.append(line.strip())
    return '\n'.join(lines).strip()


def pack(evidence):
    """No arbitrary truncation of teaching content; dedup only adjacent visuals."""
    result = {'start': evidence['start'], 'end': evidence['end'], 'speech': [], 'visuals': []}
    audit = {'version': VERSION, 'filtered_speech': [], 'visual_aliases': {}, 'empty_visuals': []}
    for item in evidence.get('speech', []):
        text = clean_text(item['text'])
        if not text:
            audit['filtered_speech'].append(item['id'])
        else:
            result['speech'].append({k: item[k] for k in ('id', 'start', 'end')} | {'text': text})
    last_signature = None
    for item in evidence.get('visuals', []):
        text = clean_text(item.get('ocr_text', ''))
        formulas = [formula_candidate(f) for f in item.get('local_formulas', [])]
        value = {'id': item['id'], 'time': item['time'], 'text': text}
        if formulas:
            value['formulas'] = formulas
        signature = json.dumps([text, formulas], ensure_ascii=False, sort_keys=True)
        if (text or formulas) and signature == last_signature:
            audit['visual_aliases'][item['id']] = result['visuals'][-1]['id']
            result['visuals'][-1].setdefault('alternates',[]).append([item['id'],item['time']])
            continue
        last_signature = signature
        if not text and not formulas:
            audit['empty_visuals'].append(item['id'])
        result['visuals'].append(value)
    for key in ('context_before', 'context_after'):
        result[key] = [{'text': text} for item in evidence.get(key, [])
                       if (text := clean_text(item['text']))]
    return result, audit


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
