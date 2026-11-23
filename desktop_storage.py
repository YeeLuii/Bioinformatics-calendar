"""Atomic JSON and one cross-process writer lock per workspace."""
import contextlib, json, os, pathlib, threading, time

THREAD_LOCK=threading.RLock()

def read_json(path,default=None):
    p=pathlib.Path(path)
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default

def write_json(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

@contextlib.contextmanager
def workspace_lock(directory):
    with THREAD_LOCK:
        p=pathlib.Path(directory)/'.ai4s.write.lock'
        with p.open('a+b') as f:
            if p.stat().st_size==0:f.write(b'0');f.flush()
            deadline=time.monotonic()+8
            while True:
                try:
                    f.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic()>deadline:raise TimeoutError('工作区正在写入，请稍后重试')
                    time.sleep(.05)
            try:yield
            finally:
                f.seek(0)
                if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
