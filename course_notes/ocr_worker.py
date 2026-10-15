"""DeepRead inference adapter: local model files and network-blocked subprocess."""
import json, os, socket, sys
from pathlib import Path
request=json.loads(Path(sys.argv[1]).read_text('utf-8'))
root=Path(request['root']); job=Path(request['job']); models=root/'models'
cuda_dirs=[root/'.venv-paddle/Lib/site-packages/torch/lib']
_dll_handles=[]
for directory in cuda_dirs:
    if directory.is_dir():
        os.environ['PATH']=str(directory)+os.pathsep+os.environ.get('PATH','')
        _dll_handles.append(os.add_dll_directory(str(directory)))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',GRADIO_ANALYTICS_ENABLED='False')
def no_network(*args,**kwargs): raise RuntimeError('DeepRead 识别进程禁止网络访问；请先部署本地模型。')
socket.socket.connect=no_network; socket.socket.connect_ex=no_network; socket.create_connection=no_network

import cv2
import numpy as np
cv2.setNumThreads(2)
import torch  # Windows: load Torch CUDA DLLs before Paddle to avoid DLL collision.
import paddle
if not paddle.is_compiled_with_cuda(): raise RuntimeError('需要 GPU 版 PaddlePaddle，禁止 CPU 降级。')
paddle.set_device('gpu:0')
from paddleocr import PaddleOCR, TextDetection
cache=Path.home()/'.paddlex/official_models'
det=cache/'PP-OCRv5_server_det'; rec=cache/'PP-OCRv5_server_rec'
for path in (det,rec):
    if not path.is_dir(): raise FileNotFoundError(f'缺少本地 Paddle 模型：{path}')
mode=request['mode']
if mode=='printed':
    engine=PaddleOCR(text_detection_model_name='PP-OCRv5_server_det',text_detection_model_dir=str(det),text_recognition_model_name='PP-OCRv5_server_rec',text_recognition_model_dir=str(rec),use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,lang='ch',device='gpu:0',enable_mkldnn=False)
elif mode=='handwritten':
    import torch
    if not torch.cuda.is_available(): raise RuntimeError('需要 CUDA 版 PyTorch，禁止 CPU 降级。')
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    processor=TrOCRProcessor.from_pretrained(models/'handwritten',local_files_only=True)
    model=VisionEncoderDecoderModel.from_pretrained(models/'handwritten',local_files_only=True).to('cuda').eval()
    detector=TextDetection(model_name='PP-OCRv5_server_det',model_dir=str(det),device='gpu:0',enable_mkldnn=False)
else: raise ValueError(f'未知 OCR 模式：{mode}')
rows=[]
if (job/'ocr.json').exists():
    old=json.loads((job/'ocr.json').read_text('utf-8'))
    expected=request['rows'][:len(old)]
    if all(a['image']==b['image'] and a.get('ocr_backend')=='DeepRead-local-'+mode and a.get('device')=='gpu:0' for a,b in zip(old,expected)) and len(old)<=len(request['rows']): rows=old
for row in request['rows']:
    if any(done['image']==row['image'] for done in rows): continue
    image=job/row['image']; print('OCR',row['timestamp'],flush=True)
    if mode=='printed':
        array=cv2.imdecode(np.frombuffer(image.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        predictions=list(engine.predict(array))
        texts=[t for p in predictions for t in p.get('rec_texts',[])]
        scores=[float(t) for p in predictions for t in p.get('rec_scores',[])]
        regions=[]
        height,width=array.shape[:2]
        for prediction in predictions:
            for text,box in zip(prediction.get('rec_texts',[]),prediction.get('rec_polys',[])):
                box=np.asarray(box)
                regions.append({'text':text,'bbox':[max(0,int(box[:,0].min()*1000/width)-6),max(0,int(box[:,1].min()*1000/height)-10),min(1000,int(np.ceil(box[:,0].max()*1000/width))+6),min(1000,int(np.ceil(box[:,1].max()*1000/height))+10)]})
    else:
        arr=cv2.imdecode(np.frombuffer(image.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR); crops=[];boxes=[]
        for p in detector.predict(arr):
            for box in p.get('dt_polys',[]):
                box=np.array(box,dtype=np.float32); w=max(1,int(max(np.linalg.norm(box[0]-box[1]),np.linalg.norm(box[2]-box[3])))); h=max(1,int(max(np.linalg.norm(box[0]-box[3]),np.linalg.norm(box[1]-box[2]))))
                matrix=cv2.getPerspectiveTransform(box,np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]],dtype=np.float32))
                crops.append(cv2.cvtColor(cv2.warpPerspective(arr,matrix,(w,h)),cv2.COLOR_BGR2RGB))
                boxes.append(box)
        texts=[]; scores=[];regions=[]
        for crop in crops or [cv2.cvtColor(arr,cv2.COLOR_BGR2RGB)]:
            with torch.no_grad(): ids=model.generate(processor(images=crop,return_tensors='pt').pixel_values.to('cuda'),max_new_tokens=128)
            texts.append(processor.batch_decode(ids,skip_special_tokens=True)[0])
        height,width=arr.shape[:2]
        for text,box in zip(texts,boxes):
            regions.append({'text':text,'bbox':[max(0,int(box[:,0].min()*1000/width)-6),max(0,int(box[:,1].min()*1000/height)-10),min(1000,int(np.ceil(box[:,0].max()*1000/width))+6),min(1000,int(np.ceil(box[:,1].max()*1000/height))+10)]})
    rows.append({**row,'ocr_text':'\n'.join(texts),'ocr_scores':scores,'ocr_regions':regions,'ocr_status':'recognized' if texts else 'no_text_detected','ocr_backend':'DeepRead-local-'+mode,'device':'gpu:0',
                 'ocr_warning':'手写模型对中文和数学公式的准确率未经保证，输出必须对照原图复核。' if mode=='handwritten' else '普通文字 OCR 不提供可靠的二维数学公式 LaTeX 识别。'})
    (job/'ocr.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
