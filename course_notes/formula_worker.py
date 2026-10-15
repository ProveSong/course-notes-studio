"""GPU only; explicit local weights; network blocked before ML imports."""
import hashlib,json,os,socket,sys
from pathlib import Path

request=json.loads(Path(sys.argv[1]).read_text('utf-8'))
root=Path(request['root']);job=Path(request['job'])
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',HF_HUB_DISABLE_TELEMETRY='1')
handles=[]
directory=root/'.venv-paddle/Lib/site-packages/torch/lib'
if directory.is_dir():
    os.environ['PATH']=str(directory)+os.pathsep+os.environ.get('PATH','')
    if hasattr(os,'add_dll_directory'):handles.append(os.add_dll_directory(str(directory)))
def blocked(*args,**kwargs):raise RuntimeError('本地公式识别禁止联网。')
socket.socket.connect=blocked;socket.socket.connect_ex=blocked;socket.create_connection=blocked
import torch
import paddle
if not paddle.is_compiled_with_cuda():raise RuntimeError('公式识别需要 Paddle GPU，禁止 CPU 降级。')
paddle.set_device('gpu:0')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from course_notes.board_assets import read_image,crop_box,extract_ink,latex_warnings,write_image
from paddleocr import FormulaRecognition
cache_dir=job/'formula-cache';cache_dir.mkdir(exist_ok=True)
engine=None;records=[]
for index,task in enumerate(request['tasks'],1):
    source=(job/task['image']).resolve()
    if not source.is_relative_to(job):raise ValueError('公式图片必须在任务目录中。')
    image=read_image(source);crop,pixels=crop_box(image,task['bbox'])
    background=task.get('background','auto')
    if background=='auto':
        import numpy as np
        background='dark' if float(np.median(crop))<128 else 'light'
    # Formula OCR needs intact strokes; diagram morphology can erase symbols.
    import cv2
    import numpy as np
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    if background=='dark':gray=255-gray
    lo,hi=np.percentile(gray,[2,98])
    gray=np.clip((gray.astype(np.float32)-lo)*255/max(1.,hi-lo),0,255).astype(np.uint8)
    gray=cv2.copyMakeBorder(gray,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
    white=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    key=hashlib.sha256(white.tobytes()+str(white.shape).encode()+request['model_sha256'].encode()+b'formula-v2').hexdigest()
    cache=cache_dir/(key+'.json')
    if cache.exists():value=json.loads(cache.read_text('utf-8'))
    else:
        if engine is None:
            engine=FormulaRecognition(model_name='PP-FormulaNet_plus-S',model_dir=request['model'],device='gpu:0',enable_mkldnn=False)
        prediction=next(iter(engine.predict(white)))
        latex=prediction.get('rec_formula','')
        value={'latex':latex,'syntax_warnings':latex_warnings(latex),'backend':'PP-FormulaNet_plus-S','device':'gpu:0','model_sha256':request['model_sha256'],'status':'candidate-unverified'}
        cache.write_text(json.dumps(value,ensure_ascii=False),'utf-8')
        write_image(cache_dir/(key+'.png'),white)
    records.append({**value,'row':task['row'],'bbox':task['bbox'],'image':task['image'],'crop_sha256':key,'proposal':task.get('proposal','explicit-region')})
    (job/'formulas.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    print(f'公式 OCR {index}/{len(request["tasks"])} '+value['latex'][:100],flush=True)
