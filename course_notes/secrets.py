"""Windows DPAPI storage; keys never enter settings or task manifests."""
import ctypes,os
from ctypes import wintypes
from .config import ROOT

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def crypt(value,decrypt=False):
    if os.name!='nt':raise RuntimeError('仅 Windows 支持本地密钥保存；其他系统请设置 DEEPSEEK_API_KEY 环境变量。')
    buffer=ctypes.create_string_buffer(value);source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    if decrypt:ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    if not ok:raise ctypes.WinError()
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)

def save_deepseek_key(value):
    path=ROOT/'deepseek-key.dpapi'
    if value.strip():path.write_bytes(crypt(value.strip().encode()))
    elif path.exists():path.unlink()

def deepseek_key():
    value=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if value:return value
    path=ROOT/'deepseek-key.dpapi'
    return crypt(path.read_bytes(),True).decode() if path.exists() else ''
