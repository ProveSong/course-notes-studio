"""Collect licenses from the exact environment used for the binary build."""
from importlib.metadata import distributions
from pathlib import Path
import shutil,sys

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    for package in distributions():
        name=package.metadata.get('Name','dependency')
        version=package.version
        selected=[f for f in package.files or [] if any(part.lower() in {'licenses','license','license.txt','license.md','copying','copyright','notice','notice.txt'} for part in f.parts)]
        for index,relative in enumerate(selected):
            source=Path(package.locate_file(relative))
            if source.is_file():
                directory=out/(name+'-'+version);directory.mkdir(exist_ok=True)
                shutil.copyfile(source,directory/(str(index)+'-'+source.name))
    for relative in ['LICENSE.txt','tcl/tcl8.6/license.terms','tcl/tk8.6/license.terms']:
        source=Path(sys.base_prefix)/relative
        if source.is_file():shutil.copyfile(source,out/('Python-'+source.parent.name+'-'+source.name))
if __name__=='__main__':main()
