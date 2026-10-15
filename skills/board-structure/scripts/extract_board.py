"""Render structured board JSON locally; use --help for explicit input paths."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from course_notes.board_assets import materialize

def main():
    ap=argparse.ArgumentParser(description='本地板书去背景、公式原图裁剪与 Markdown 输出')
    ap.add_argument('--job',type=Path,required=True);ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--analysis',type=Path,required=True);ap.add_argument('--id',required=True)
    args=ap.parse_args();text=materialize(args.job.resolve(),args.id,args.image.resolve(),json.loads(args.analysis.read_text('utf-8')))
    out=args.job/'chunks'/f'{args.id}.board.md';out.parent.mkdir(exist_ok=True);out.write_text(text,'utf-8');print(out)

if __name__=='__main__':main()
