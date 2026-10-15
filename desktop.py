"""Desktop entrypoint; --smoke-test checks the packaged app without a video."""
import sys,json
from pathlib import Path

def main():
    if '--smoke-test' in sys.argv:
        from course_notes.app import App
        from course_notes.config import ROOT,RESOURCES
        app=App(enable_control=False);app.withdraw();app.update_idletasks();app.destroy()
        result={'gui':'ok','data_directory':str(ROOT),'skills_present':(RESOURCES/'skills/course-handout/compact.md').is_file()}
        if '--report' in sys.argv:Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps(result),'utf-8')
        if not result['skills_present']:raise RuntimeError('Skills missing')
    else:
        from course_notes.app import main as gui
        gui()
if __name__=='__main__':
    try:main()
    except Exception:
        import traceback,tkinter.messagebox
        from course_notes.config import ROOT
        (ROOT/'startup-error.log').write_text(traceback.format_exc(),'utf-8')
        tkinter.messagebox.showerror('Course Notes Studio','启动失败，详情：'+str(ROOT/'startup-error.log'))
        raise
