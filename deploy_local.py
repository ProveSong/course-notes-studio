"""Explicit online setup. Runtime OCR workers block all network access."""
import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
from pathlib import Path
import torch
import paddle
from course_notes.config import Settings

def main():
    if not torch.cuda.is_available() or not paddle.is_compiled_with_cuda():raise RuntimeError('CUDA GPU is required; CPU fallback is disabled.')
    paddle.set_device('gpu:0')
    settings=Settings.load();root=Path(settings.deepread_root);(root/'models').mkdir(parents=True,exist_ok=True)
    from paddleocr import PaddleOCR
    print('Preparing PP-OCRv5 GPU text models...',flush=True)
    PaddleOCR(text_detection_model_name='PP-OCRv5_server_det',text_recognition_model_name='PP-OCRv5_server_rec',use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,lang='ch',device='gpu:0',enable_mkldnn=False)
    print('Preparing optional handwritten model...',flush=True)
    from huggingface_hub import snapshot_download
    snapshot_download('imperiusrex/Handwritten_model',local_dir=root/'models/handwritten',ignore_patterns=['*.bin','*.h5','*.msgpack','*.onnx'])
    print('Preparing local formula model...',flush=True)
    from deploy_formula import main as deploy_formula
    deploy_formula()
    print('GPU models ready. Start Course Notes Studio and configure VideoCaptioner / CC Switch.',flush=True)
if __name__=='__main__':main()
