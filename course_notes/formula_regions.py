"""Conservative geometry grouping of OCR fragments into formula line proposals.

Coordinates remain normalized 0..1000. Grouping is a proposal, not a detector
of complete mathematical structure. Explicit reviewed regions are kept intact.
"""
import re
import statistics

VERSION = 'formula-lines-1'
MATH = re.compile(r'[=∑∫√∞≤≥∈∉⊂∀∃→α-ωΑ-Ω]|[a-zA-Z]\s*\^|\\(?:frac|sum|int)')


def candidates(row):
    regions=[]
    for region in row.get('ocr_regions',[]):
        box=region.get('bbox',[])
        if len(box)!=4 or not all(isinstance(x,(int,float)) for x in box):continue
        l,t,r,b=box
        if not (0<=l<r<=1000 and 0<=t<b<=1000):continue
        text=region.get('text','')
        if not text.strip() or b-t>160:continue
        # Long prose lines and player chrome should not bridge columns.
        if len(re.findall(r'[\u4e00-\u9fff]',text))>12:continue
        regions.append((list(box),text))
    groups=[([box], [text]) for box,text in regions]
    def bounds(boxes):return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    changed=True
    while changed:
        changed=False
        for i in range(len(groups)):
            if changed:break
            for j in range(i+1,len(groups)):
                a,ta=groups[i];b,tb=groups[j];x=bounds(a);y=bounds(b)
                ha=x[3]-x[1];hb=y[3]-y[1]
                overlap=max(0,min(x[3],y[3])-max(x[1],y[1]))
                gap=max(0,max(x[0],y[0])-min(x[2],y[2]))
                all_boxes=a+b
                height=statistics.median(box[3]-box[1] for box in all_boxes)
                centers=[(box[1]+box[3])/2 for box in all_boxes]
                # Padded OCR boxes on neighboring lines overlap. A strict
                # baseline band prevents transitive merging of entire boards.
                same_line=overlap>=.6*min(ha,hb) and max(centers)-min(centers)<=.32*height
                if same_line and gap<=min(45,max(18,1.2*min(ha,hb))):
                    groups[i]=(a+b,ta+tb);groups.pop(j);changed=True;break
    for boxes,texts in groups:
        if not any(MATH.search(t) for t in texts):continue
        box=bounds(boxes)
        # Preserve local margin for superscripts, fraction bars and arrowheads.
        margin=min(10,max(4,(box[3]-box[1])*.1))
        yield {'bbox':[max(0,int(box[0]-8)),max(0,int(box[1]-margin)),min(1000,int(box[2]+8)),min(1000,int(box[3]+margin))],
               'background':'auto','proposal':VERSION,'source_boxes':boxes}
    yield from row.get('formula_regions',[])
