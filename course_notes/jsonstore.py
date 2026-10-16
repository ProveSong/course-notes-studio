"""Atomic JSON updates shared by pipeline and screenshot review workers."""
import json, os, tempfile, time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def transaction(path):
    path=Path(path)
    with path.with_suffix(path.suffix+'.lock').open('a+b') as lock:
        lock.seek(0,2)
        if lock.tell()==0: lock.write(b'0'); lock.flush()
        lock.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            records=json.loads(path.read_text('utf-8')) if path.exists() else []
            yield records
            fd,name=tempfile.mkstemp(dir=path.parent,suffix='.json.tmp')
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as target:
                    json.dump(records,target,ensure_ascii=False,indent=2)
                # GUI/antivirus readers can briefly deny replacement on Windows.
                # Retain the transaction lock and the complete temporary file.
                for attempt in range(8):
                    try:
                        os.replace(name,path)
                        break
                    except PermissionError:
                        if attempt==7:raise
                        time.sleep(.05 * (attempt+1))
            finally:
                if os.path.exists(name): os.unlink(name)
        finally:
            lock.seek(0)
            if os.name=='nt': msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
