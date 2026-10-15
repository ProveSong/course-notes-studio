import sys,zipfile,time,hashlib
from pathlib import Path

def main():
    source=Path(sys.argv[1]);target=Path(sys.argv[2]);temporary=target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(source.rglob('*')):
            if not file.is_file() or '__pycache__' in file.parts or file.suffix in {'.pyc','.log'}:continue
            for attempt in range(5):
                try:archive.write(file,file.relative_to(source));break
                except PermissionError:
                    if attempt==4:raise
                    time.sleep(1)
    with zipfile.ZipFile(temporary) as archive:
        invalid=archive.testzip()
        if invalid:raise RuntimeError('Corrupt archive member: '+invalid)
    temporary.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n','utf-8')
    print(target,target.stat().st_size,digest,flush=True)
if __name__=='__main__':main()
