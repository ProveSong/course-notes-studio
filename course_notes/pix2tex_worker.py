"""Offline, isolated CUDA pix2tex backend; cached candidates need verification."""
import hashlib,json,os,socket,sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NO_ALBUMENTATIONS_UPDATE='1')
def blocked(*args,**kwargs):raise RuntimeError('Local formula recognition cannot access the network')
socket.socket.connect=blocked;socket.socket.connect_ex=blocked;socket.create_connection=blocked
request=json.loads(Path(sys.argv[1]).read_text('utf-8'))
job=Path(request['job']).resolve();model=Path(request['model']).resolve()
for name in ('weights.pth','image_resizer.pth'):
    if not (model/name).is_file():raise FileNotFoundError(model/name)
import torch
if not torch.cuda.is_available():raise RuntimeError('pix2tex requires CUDA; CPU fallback disabled')
from munch import Munch
from PIL import Image
import pix2tex
from pix2tex.cli import LatexOCR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from course_notes.board_assets import read_image,crop_box,latex_warnings,write_image
import cv2,numpy as np
cache_dir=job/'pix2tex-cache';cache_dir.mkdir(exist_ok=True)
engine=None;records=[]
for index,task in enumerate(request['tasks'],1):
    source=(job/task['image']).resolve()
    if not source.is_relative_to(job):raise ValueError('Image must remain within the job')
    crop,_=crop_box(read_image(source),task['bbox'])
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    background=task.get('background','auto')
    if background=='dark' or (background=='auto' and np.median(gray)<128):gray=255-gray
    gray=cv2.copyMakeBorder(gray,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
    key=hashlib.sha256(gray.tobytes()+str(gray.shape).encode()+request['model_sha256'].encode()+b'pix2tex-v1').hexdigest()
    cache=cache_dir/(key+'.json')
    if cache.exists():value=json.loads(cache.read_text('utf-8'))
    else:
        if engine is None:
            config=Path(pix2tex.__file__).parent/'model/settings/config.yaml'
            engine=LatexOCR(Munch(config=str(config),checkpoint=str(model/'weights.pth'),no_cuda=False,no_resize=False))
            engine.args.temperature=0.01
        torch.manual_seed(0)
        with torch.inference_mode():latex=engine(Image.fromarray(gray))
        value={'latex':latex,'syntax_warnings':latex_warnings(latex),'backend':'pix2tex-0.1.4','device':'cuda:0','model_sha256':request['model_sha256'],'status':'candidate-unverified'}
        cache.write_text(json.dumps(value,ensure_ascii=False),'utf-8');write_image(cache_dir/(key+'.png'),gray)
    records.append({**value,'row':task['row'],'bbox':task['bbox'],'image':task['image'],'crop_sha256':key,'proposal':task.get('proposal','explicit-region')})
    (job/'formulas.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    print(f'公式 OCR {index}/{len(request["tasks"])}',flush=True)
