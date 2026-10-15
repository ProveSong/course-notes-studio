from __future__ import annotations
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from .config import Settings
from .pipeline import run_safe


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Course Notes Studio · 课程回放讲义整理器'); self.geometry('1000x780'); self.cancel=threading.Event()
        self.video=tk.StringVar(); self.output=tk.StringVar(value=Settings.load().output_root); self.status=tk.StringVar(value='选择课程视频后开始')
        self._row('课程视频',self.video,True); self._row('输出目录',self.output,False)
        self.settings=Settings.load()
        config=ttk.Frame(self); config.pack(fill='x',padx=14,pady=4)
        from .config import providers
        try:self.provider_options=providers(self.settings.cc_database)
        except Exception:self.provider_options=[]
        initial=next((p for p in self.provider_options if p.identity==self.settings.provider),self.provider_options[0] if self.provider_options else None)
        self.provider_choice=tk.StringVar(value=initial.label if initial else '')
        ttk.Label(config,text='LLM').pack(side='left'); self.provider_box=ttk.Combobox(config,textvariable=self.provider_choice,values=[p.label for p in self.provider_options],state='readonly',width=40);self.provider_box.pack(side='left',padx=5)
        self.ocr_choice=tk.StringVar(value=self.settings.ocr_mode); ttk.Combobox(config,textvariable=self.ocr_choice,values=['printed','handwritten'],state='readonly',width=12).pack(side='left',padx=5)
        self.model_choice=tk.StringVar(value=self.settings.model); ttk.Entry(config,textvariable=self.model_choice,width=20).pack(side='left',padx=5)
        transport=ttk.Frame(self);transport.pack(fill='x',padx=14,pady=4)
        ttk.Label(self,text='课堂文字会发送到所选 LLM；截图须批准后发送。',foreground='#555555').pack(anchor='w',padx=14)
        ttk.Label(transport,text='LLM 调用方式').pack(side='left')
        self.transport_choice=tk.StringVar(value=self.settings.llm_transport)
        ttk.Combobox(transport,textvariable=self.transport_choice,values=['api','codex_cli'],state='readonly',width=15).pack(side='left',padx=8)
        ttk.Label(transport,text='codex_cli 使用本机 CLI；截图仍需批准').pack(side='left')
        options=ttk.Frame(self);options.pack(fill='x',padx=14,pady=4)
        self.compact_choice=tk.BooleanVar(value=self.settings.compact_notes)
        ttk.Checkbutton(options,text='省 token：直接生成课程讲解',variable=self.compact_choice).pack(side='left')
        self.formula_choice=tk.StringVar(value=self.settings.formula_backend)
        ttk.Button(options,text='首次配置 / 环境检查',command=self.configure).pack(side='right')
        ttk.Label(options,text='本地 GPU 公式识别').pack(side='left',padx=10)
        ttk.Combobox(options,textvariable=self.formula_choice,values=['paddle','none'],state='readonly',width=10).pack(side='left')
        self.job=None
        bar=ttk.Frame(self); bar.pack(fill='x',padx=14,pady=10); self.start=ttk.Button(bar,text='开始整理',command=self.start_job); self.start.pack(side='left'); ttk.Button(bar,text='取消',command=self.cancel.set).pack(side='left',padx=8)
        ttk.Button(bar,text='查看并批准截图复核',command=self.review_images).pack(side='left',padx=8)
        ttk.Button(bar,text='重试已批准截图',command=self.process_reviews).pack(side='left',padx=8)
        ttk.Button(bar,text='公式与图形',command=self.process_board).pack(side='left',padx=8)
        self.review_running=False;self.board_running=False
        ttk.Label(self,textvariable=self.status,wraplength=680).pack(anchor='w',padx=14,pady=8)
        self.progress=ttk.Progressbar(self,orient='horizontal',mode='determinate',maximum=100); self.progress.pack(fill='x',padx=14,pady=4)
        self.stage_progress=ttk.Progressbar(self,orient='horizontal',mode='determinate',maximum=100); self.stage_progress.pack(fill='x',padx=14,pady=4)
        self.metrics=tk.StringVar(value='总进度 0% · 尚未开始'); ttk.Label(self,textvariable=self.metrics).pack(anchor='w',padx=14)
        self.running=False; self.started=0; self.duration=1; self.phase=''; self.completed=False
        ttk.Button(self,text='打开已有任务目录',command=self.open_job).pack(anchor='w',padx=14)
        ttk.Button(self,text='打开输出文件夹',command=self.open_output).pack(anchor='w',padx=14,pady=3)
        self.shutdown=tk.BooleanVar(value=False); ttk.Checkbutton(self,text='完成后自动关机（需明确勾选）',variable=self.shutdown).pack(anchor='w',padx=14)
        self.log=tk.Text(self,height=16,state='disabled'); self.log.pack(fill='both',expand=True,padx=14,pady=8)
        self.after(1000,self.poll_progress)
    def _row(self,label,var,browse):
        f=ttk.Frame(self); f.pack(fill='x',padx=14,pady=8); ttk.Label(f,text=label,width=12).pack(side='left'); ttk.Entry(f,textvariable=var).pack(side='left',fill='x',expand=True)
        if browse: ttk.Button(f,text='选择',command=lambda:self.pick(var,False)).pack(side='left',padx=6)
        else: ttk.Button(f,text='选择',command=lambda:self.pick(var,True)).pack(side='left',padx=6)
    def pick(self,var,directory):
        value=filedialog.askdirectory() if directory else filedialog.askopenfilename(filetypes=[('视频','*.mp4 *.mkv *.mov *.avi'),('全部','*.*')]);
        if value: var.set(value)
    def open_output(self):
        import os
        directory=Path(self.output.get());directory.mkdir(parents=True,exist_ok=True)
        os.startfile(directory)
    def start_job(self):
        video=Path(self.video.get());
        if not video.is_file(): messagebox.showerror('输入错误','请选择存在的视频文件。'); return
        if not self.provider_options:
            messagebox.showerror('首次配置','请先在 CC Switch 中配置 LLM，并点击“首次配置 / 环境检查”选择数据库。');return
        self.start.config(state='disabled'); self.cancel.clear(); settings=Settings.load()
        selected=next((p for p in self.provider_options if p.label==self.provider_choice.get()),None)
        if selected: settings.provider=selected.identity
        settings.model=self.model_choice.get(); settings.ocr_mode=self.ocr_choice.get(); settings.llm_transport=self.transport_choice.get()
        settings.compact_notes=self.compact_choice.get();settings.formula_backend=self.formula_choice.get();settings.save()
        self.job=Path(self.output.get())/(video.stem+'_job')
        import json
        if (self.job/'manifest.json').exists():
            manifest=json.loads((self.job/'manifest.json').read_text('utf-8'))
            settings.chunk_seconds=manifest.get('chunk_seconds',settings.chunk_seconds)
            settings.save()
        import cv2,time
        cap=cv2.VideoCapture(str(video)); self.duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/(cap.get(cv2.CAP_PROP_FPS) or 25); cap.release()
        self.running=True; self.completed=False; self.started=time.monotonic(); self.phase='语音识别'
        def notify(stage,msg): self.after(0,lambda:self.update_progress(stage,msg))
        def work():
            succeeded=False
            try:
                target=run_safe(video,Path(self.output.get()),settings,notify,self.cancel); succeeded=True
                self.after(0,lambda:self.write(f'完成：{target}'))
            except Exception as e: self.after(0,lambda message=str(e):self.write(f'失败：{message}'))
            finally: self.after(0,lambda:self.finish_job(succeeded))
        threading.Thread(target=work,daemon=True).start()
    def configure(self):
        from .config import ROOT,providers
        from .diagnostics import checks
        window=tk.Toplevel(self);window.title('首次配置与环境检查');window.geometry('740x470')
        fields={}
        for key,label,directory in [('video_captioner','VideoCaptioner 安装目录',True),('cc_database','CC Switch 数据库',False),('deepread_root','本地 GPU 环境与模型目录',True)]:
            row=ttk.Frame(window);row.pack(fill='x',padx=12,pady=6)
            ttk.Label(row,text=label,width=25).pack(side='left')
            variable=tk.StringVar(value=getattr(self.settings,key));fields[key]=variable
            ttk.Entry(row,textvariable=variable).pack(side='left',fill='x',expand=True)
            def choose(var=variable,is_dir=directory):
                selected=filedialog.askdirectory(parent=window) if is_dir else filedialog.askopenfilename(parent=window)
                if selected:var.set(selected)
            ttk.Button(row,text='浏览',command=choose).pack(side='right')
        result=tk.Text(window,height=12);result.pack(fill='both',expand=True,padx=12,pady=8)
        def refresh():
            result.delete('1.0','end')
            for name,ok,detail in checks(self.settings):result.insert('end',('✓ ' if ok else '✗ ')+name+'：'+detail+'\n')
        def save():
            for key,var in fields.items():setattr(self.settings,key,var.get())
            self.settings.formula_model_dir=str(Path(self.settings.deepread_root)/'models/formula')
            self.settings.save()
            try:self.provider_options=providers(self.settings.cc_database)
            except Exception as error:self.provider_options=[];messagebox.showerror('LLM 配置',str(error),parent=window)
            self.provider_box['values']=[p.label for p in self.provider_options]
            if self.provider_options:self.provider_choice.set(self.provider_options[0].label)
            refresh()
        ttk.Button(window,text='保存并检查',command=save).pack(pady=5)
        ttk.Label(window,text='模型未部署时，请运行软件包中的 setup-gpu.cmd。首次部署需要联网；OCR 推断离线。',wraplength=700).pack(pady=5)
        refresh()
    def write(self,text): self.status.set(text); self.log.config(state='normal'); self.log.insert('end',text+'\n'); self.log.see('end'); self.log.config(state='disabled')
    def update_progress(self,stage,msg):
        import re
        self.write(f'[{stage}] {msg}')
        self.phase=stage
        m=re.search(r'(\d+)\s*/\s*(\d+)',msg)
        if stage=='完成': self.progress['value']=100
    def finish_job(self,succeeded):
        import json,subprocess
        self.running=False; self.completed=succeeded; self.start.config(state='normal')
        pending=[]
        pending_board=[]
        if self.job and (self.job/'review-requests.json').exists():
            records=json.loads((self.job/'review-requests.json').read_text('utf-8'))
            pending=[r for r in records if r['status'] in ('pending','approved')]
            pending_board=[r for r in records if r['status']=='reviewed' and not (self.job/'chunks'/f'{r["id"]}.board.md').is_file()]
        if succeeded: self.progress['value']=100; self.stage_progress['value']=100
        if succeeded and self.shutdown.get() and not self.cancel.is_set() and not pending and not pending_board:
            window=tk.Toplevel(self); window.title('完成后关机倒计时')
            countdown=tk.StringVar(); ttk.Label(window,textvariable=countdown).pack(padx=25,pady=20)
            def abort(): subprocess.run(['shutdown','/a'],creationflags=subprocess.CREATE_NO_WINDOW); window.destroy()
            ttk.Button(window,text='取消关机',command=abort).pack(pady=10)
            subprocess.run(['shutdown','/s','/t','60','/c','课程回放讲义任务完成'],creationflags=subprocess.CREATE_NO_WINDOW)
            def tick(n=60):
                if window.winfo_exists(): countdown.set(f'任务完成，{n} 秒后关机'); window.after(1000,lambda:tick(max(0,n-1)))
            tick()
        elif pending: self.write(f'有 {len(pending)} 项截图请求等待批准，未安排关机。')
        elif pending_board:self.write(f'有 {len(pending_board)} 张已复核截图等待公式与图形处理，未安排关机。')
    def poll_progress(self):
        import json,re,time,math
        if self.running and self.job:
            try:
                phase=self.phase; fraction=0.; overall=0.
                if '语音' in phase:
                    p=self.job/'asr.log'
                    if p.exists():
                        with p.open('rb') as source: source.seek(max(0,p.stat().st_size-12000)); text=source.read().decode('utf-8','replace')
                        stamps=re.findall(r'\[(\d+):(\d+):(\d+(?:\.\d+)?)\s*-->',text)
                        if stamps:
                            h,m,s=stamps[-1]; fraction=min(.99,(int(h)*3600+int(m)*60+float(s))/self.duration)
                    overall=20*fraction
                elif '采样' in phase:
                    fraction=min(1,len(list((self.job/'visuals').glob('*.jpg')))/max(1,math.ceil(self.duration/Settings.load().sample_seconds))); overall=20+10*fraction
                elif phase=='公式 OCR':
                    p=self.job/'formulas.json'; count=len(json.loads(p.read_text('utf-8'))) if p.exists() else 0
                    request=self.job/'formula-request.json'
                    total=len(json.loads(request.read_text('utf-8'))['tasks']) if request.exists() else 0
                    fraction=min(1,count/max(1,total));overall=65+5*fraction
                elif 'OCR' in phase:
                    p=self.job/'ocr.json'; count=len(json.loads(p.read_text('utf-8'))) if p.exists() else 0
                    total=len(json.loads((self.job/'visuals.json').read_text('utf-8'))); fraction=count/max(1,total); overall=30+40*fraction
                elif '整合' in phase:
                    manifest=json.loads((self.job/'manifest.json').read_text('utf-8'))
                    count=len(list((self.job/'chunks').glob('C*.result.json'))); total=math.ceil(self.duration/manifest.get('chunk_seconds',Settings.load().chunk_seconds)); fraction=min(1,count/max(1,total)); overall=70+30*fraction
                self.progress['value']=overall; self.stage_progress['value']=100*fraction
                elapsed=time.monotonic()-self.started
                eta=f'约 {int(elapsed*(100/max(overall,1)-1)//60)} 分钟' if overall>2 else '估算中'
                self.metrics.set(f'总进度 {overall:.1f}% · 当前阶段 {phase} {fraction*100:.1f}% · 已用 {int(elapsed//60)} 分钟 · 剩余 {eta}')
            except (OSError,ValueError,KeyError): pass
        if self.review_running and self.job:
            try:
                records=json.loads((self.job/'review-requests.json').read_text('utf-8'))
                reviewed=sum(r['status']=='reviewed' for r in records)
                pending=sum(r['status']=='pending' for r in records)
                total=len(records)
                if self.board_running:
                    reviewed=sum((self.job/'chunks'/f'{r["id"]}.board.md').exists() for r in records)
                self.stage_progress['value']=100*reviewed/max(1,total)
                label='公式与图形' if self.board_running else '截图复核'
                self.metrics.set(f'{label} {reviewed}/{total} · 等待批准 {pending} · 结果随完成保存')
            except (OSError,ValueError): pass
        self.after(1000,self.poll_progress)

    def review_images(self):
        import json
        from PIL import Image,ImageTk
        from .review import decide,destination,resolve_image,process_approved
        from .pipeline import assemble
        job=self.job
        if not job or not (job/'review-requests.json').exists():
            messagebox.showinfo('截图复核','当前任务尚未生成截图请求。'); return
        settings=Settings.load(); records=json.loads((job/'review-requests.json').read_text('utf-8'))
        pending=[r for r in records if r['status']=='pending']
        if not pending: messagebox.showinfo('截图复核','没有等待批准的截图。'); return
        record=pending[0]; dialog=tk.Toplevel(self); dialog.title('截图上传批准：'+record['id'])
        thumb=Image.open(resolve_image(job,record['image'])); thumb.thumbnail((860,480)); photo=ImageTk.PhotoImage(thumb)
        label=ttk.Label(dialog,image=photo); label.image=photo; label.pack()
        ttk.Label(dialog,text=record['reason']+'\n将把此截图和相关文字证据发往：'+str(destination(settings)),wraplength=850).pack(padx=10,pady=10)
        def choose(yes):
            decide(job,[record['id']],settings,yes); dialog.destroy()
            if not yes: self.review_images(); return
            self.process_reviews()
        ttk.Button(dialog,text='批准上传这张截图',command=lambda:choose(True)).pack(side='left',padx=15,pady=10)
        ttk.Button(dialog,text='拒绝上传',command=lambda:choose(False)).pack(side='right',padx=15,pady=10)
    def process_reviews(self):
        import json
        from .review import process_approved
        from .pipeline import assemble
        if self.review_running: self.write('截图复核正在运行。'); return
        job=self.job
        if not job or not (job/'review-requests.json').exists():
            messagebox.showinfo('截图复核','请先打开已有任务。'); return
        if not self.running: self.cancel.clear()
        self.review_running=True; self.board_running=False;settings=Settings.load()
        def work():
            try:
                process_approved(job,settings,lambda a,b:self.after(0,lambda:self.write(a+' '+b)),self.cancel)
                manifest=json.loads((job/'manifest.json').read_text('utf-8')); assemble(job,Path(manifest['target']))
                def reviewed():
                    self.write('已批准的截图复核完成。')
                    if self.completed: self.finish_job(True)
                self.after(0,reviewed)
            except Exception as e: self.after(0,lambda m=str(e):self.write('复核失败：'+m))
            finally: self.after(0,lambda:setattr(self,'review_running',False))
        threading.Thread(target=work,daemon=True).start()
    def process_board(self):
        import json
        from .board import process
        from .pipeline import assemble
        if self.review_running: self.write('截图处理正在运行。'); return
        job=self.job
        if not job or not (job/'review-requests.json').exists():
            messagebox.showinfo('公式与图形','请先打开任务并批准所需截图。'); return
        if not self.running:self.cancel.clear()
        self.review_running=True;self.board_running=True;settings=Settings.load()
        def work():
            try:
                process(job,settings,lambda a,b:self.after(0,lambda:self.write(a+' '+b)),self.cancel)
                manifest=json.loads((job/'manifest.json').read_text('utf-8'));assemble(job,Path(manifest['target']))
                def finished():
                    self.write('已批准板书的公式与图形整理完成，结果已插入讲义。')
                    if self.completed:self.finish_job(True)
                self.after(0,finished)
            except Exception as error:self.after(0,lambda m=str(error):self.write('板书整理失败：'+m))
            finally:self.after(0,lambda:setattr(self,'review_running',False))
        threading.Thread(target=work,daemon=True).start()
    def open_job(self):
        import json
        path=filedialog.askdirectory(title='选择包含 manifest.json 的任务目录')
        if path:
            self.job=Path(path)
            if not (self.job/'manifest.json').exists(): messagebox.showerror('任务目录','所选目录不包含 manifest.json'); return
            manifest=json.loads((self.job/'manifest.json').read_text('utf-8'))
            self.video.set(manifest['signature']['video']); self.output.set(str(self.job.parent))
            import math
            self.duration=manifest['duration']
            expected=math.ceil(self.duration/manifest.get('chunk_seconds',Settings.load().chunk_seconds))
            self.completed=len(list((self.job/'chunks').glob('C*.result.json')))==expected
            if self.completed: self.progress['value']=100
            self.write('已打开任务：'+path)


def main(): App().mainloop()
