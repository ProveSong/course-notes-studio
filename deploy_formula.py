"""Explicit online deployment; inference never downloads model files."""
import hashlib,json,os
from pathlib import Path
import requests

MODEL='PaddlePaddle/PP-FormulaNet_plus-S'
def main():
    from course_notes.config import Settings
    target=Path(Settings.load().formula_model_dir);target.mkdir(parents=True,exist_ok=True)
    response=requests.get('https://huggingface.co/api/models/'+MODEL,timeout=30);response.raise_for_status()
    revision=response.json()['sha'];files={}
    for name in ['inference.yml','inference.json','inference.pdiparams']:
        url=f'https://huggingface.co/{MODEL}/resolve/{revision}/{name}'
        temporary=target/(name+'.download')
        digest=hashlib.sha256()
        with requests.get(url,stream=True,timeout=(30,240)) as download:
            download.raise_for_status()
            with temporary.open('wb') as output:
                for block in download.iter_content(1024*1024):output.write(block);digest.update(block)
        os.replace(temporary,target/name);files[name]=digest.hexdigest()
        print(name,(target/name).stat().st_size,flush=True)
    (target/'deployment.json').write_text(json.dumps({'repository':MODEL,'revision':revision,'sha256':files},indent=2),'utf-8')
if __name__=='__main__':main()
