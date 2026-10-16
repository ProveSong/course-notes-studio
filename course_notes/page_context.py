"""Exact page evidence signatures and reversible adjacent-page deltas.

No fuzzy equivalence of math symbols, no loss of corrections or page reversions.
Raw frames and full evidence remain local.
"""
import hashlib,json
from .input_cleaner import clean_visual,line_key


def page_signature(visual):
    text,_=clean_visual(visual)
    lines=[line_key(line) for line in text.splitlines() if line_key(line)]
    formulas=[f.get('latex','') for f in visual.get('local_formulas',[])]
    return hashlib.sha256(json.dumps([lines,formulas],ensure_ascii=False).encode()).hexdigest()


def delta_visuals(visuals):
    """Use compact deltas only for dense, mostly unchanged adjacent pages."""
    output=[];previous=None
    for visual in visuals:
        current=dict(visual)
        if previous is not None:
            old=previous.get('line_ids',[]);new=visual.get('line_ids',[])
            old_f=previous.get('formula_ids',[]);new_f=visual.get('formula_ids',[])
            # Unique pools preserve exact spelling/signs; IDs are not inferred
            # semantic identities. Store complete order when lines reorder.
            shared=set(old)&set(new)
            retained_old=[x for x in old if x in shared]
            retained_new=[x for x in new if x in shared]
            if len(old)>=8 and len(new)>=8 and len(shared)>=.75*max(len(old),len(new)) and retained_old==retained_new:
                patch={'base_visual_id':previous['id'],
                       'added_line_ids':[x for x in new if x not in old],
                       'removed_line_ids':[x for x in old if x not in new]}
                # Line insertions can change meaning by location, so retain the
                # whole sequence whenever both additions and removals occur.
                if not patch['added_line_ids'] and not patch['removed_line_ids']:
                    current.pop('line_ids',None);current['page_delta']=patch
                if old_f==new_f and new_f:
                    current.pop('formula_ids',None)
                    current['formula_base_visual_id']=previous['id']
        output.append(current);previous=visual
    return output


def representative(visuals):
    """Choose a full-page frame; no cropping or remote transmission here."""
    if not visuals:return None
    def score(visual):
        text,_=clean_visual(visual)
        # Favor readable evidence over isolated-symbol/noisy detections.
        usable=sum(len(line.strip())>=3 for line in text.splitlines())
        return (usable,len(text),len(visual.get('local_formulas',[])))
    return max(visuals,key=score)


def block_delta(previous,current):
    """Exact structured-content reuse; changed signs/conditions remain changes."""
    def key(block):
        return (block.get('kind',''),block.get('content',''),block.get('uncertainty',''))
    old_keys={key(block) for block in previous}
    new_keys={key(block) for block in current}
    return {'added':[block for block in current if key(block) not in old_keys],
            'removed':[block for block in previous if key(block) not in new_keys],
            'unchanged':sum(key(block) in old_keys for block in current)}
