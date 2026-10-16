"""Source storage stays separate from the small teaching prompt."""
import re
import json
from .input_cleaner import clean_text,clean_visual,line_key

VERSION = 'compact-5'


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


def pack(evidence):
    """No arbitrary truncation of teaching content; dedup only adjacent visuals."""
    result = {'start': evidence['start'], 'end': evidence['end'], 'speech': [], 'visuals': []}
    formula_pool=[];formula_indices={}
    line_pool=[];line_indices={}
    audit = {'version': VERSION, 'filtered_speech': [], 'visual_aliases': {}, 'empty_visuals': [],'filtered_visual_lines':{}}
    for item in evidence.get('speech', []):
        text = clean_text(item['text'])
        if not text:
            audit['filtered_speech'].append(item['id'])
        else:
            result['speech'].append({k: item[k] for k in ('id', 'start', 'end')} | {'text': text})
    last_signature = None
    for item in evidence.get('visuals', []):
        text,filtered = clean_visual(item)
        if filtered:audit['filtered_visual_lines'][item['id']]=filtered
        # Crop coordinates, confidence and duplicate recognition candidates stay
        # in local evidence. Text integration needs each distinct reading once.
        formulas=[];seen_formulas=set();needs_review=False
        for candidate in item.get('local_formulas', []):
            value=formula_candidate(candidate)
            latex=value.get('latex','')
            if not latex:
                needs_review=True
                continue
            if latex not in seen_formulas:
                formulas.append({'latex':latex});seen_formulas.add(latex)
        value = {'id': item['id'], 'time': item['time']}
        if formulas:
            value['formulas'] = formulas
        if needs_review:value['formula_review_needed']=True
        signature = json.dumps([line_key(text), formulas,needs_review], ensure_ascii=False, sort_keys=True)
        if (text or formulas) and signature == last_signature:
            audit['visual_aliases'][item['id']] = result['visuals'][-1]['id']
            continue
        last_signature = signature
        if not text and not formulas:
            audit['empty_visuals'].append(item['id'])
        line_ids=[]
        for line in text.splitlines():
            key=line_key(line)
            if key not in line_indices:
                line_indices[key]=len(line_pool)+1;line_pool.append(line)
            line_ids.append(line_indices[key])
        value['line_ids']=line_ids
        if formulas:
            ids=[]
            for formula in formulas:
                latex=formula['latex']
                if latex not in formula_indices:
                    formula_indices[latex]=len(formula_pool)+1
                    formula_pool.append(latex)
                ids.append(formula_indices[latex])
            value.pop('formulas')
            value['formula_ids']=ids
        result['visuals'].append(value)
    from .page_context import delta_visuals
    result['visuals']=delta_visuals(result['visuals'])
    if formula_pool:result['formula_candidates']=formula_pool
    if line_pool:result['ocr_lines']=line_pool
    for key in ('context_before', 'context_after'):
        result[key] = [{'text': text} for item in evidence.get(key, [])
                       if (text := clean_text(item['text']))]
    return result, audit


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
