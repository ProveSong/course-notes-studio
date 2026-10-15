"""Authenticated loopback status and cancellation for long desktop runs."""
import json,os,secrets,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .config import ROOT


def serve(app):
    token=secrets.token_urlsafe(32)
    state={'pid':os.getpid(),'running':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,code,payload):
            body=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def authorized(self):return secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_GET(self):
            if not self.authorized():return self.respond(401,{'error':'unauthorized'})
            if self.path!='/status':return self.respond(404,{'error':'unknown endpoint'})
            self.respond(200,dict(state))
        def do_POST(self):
            if not self.authorized():return self.respond(401,{'error':'unauthorized'})
            if self.path!='/cancel':return self.respond(404,{'error':'unknown endpoint'})
            app.cancel.set();self.respond(200,{'cancel_requested':True})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    pointer={'pid':os.getpid(),'url':f'http://127.0.0.1:{server.server_port}','token':token}
    path=ROOT/'control.json';path.write_text(json.dumps(pointer),'utf-8')
    def snapshot():
        import time
        state.update(updated=time.time(),running=app.running,review_running=app.review_running,
            status=app.status.get(),metrics=app.metrics.get(),job=str(app.job) if app.job else None,
            queue=list(app.video_queue),index=app.batch_index,total=app.batch_total,
            progress=float(app.progress['value']),auto_images=app.auto_images.get(),shutdown=app.shutdown.get(),
            completed=app.completed,results=list(app.batch_results),log=app.log.get('1.0','end')[-14000:])
        app.after(1000,snapshot)
    app.after(0,snapshot)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    app._control_server=server
    return pointer
