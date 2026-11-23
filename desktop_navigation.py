"""Small native OS navigation adapter; no chat SDK or embedded browser."""
import os, subprocess, sys

def open_native(target):
    if os.name=='nt':os.startfile(str(target))
    else:
        command='open' if sys.platform=='darwin' else 'xdg-open'
        subprocess.run([command,str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15)

