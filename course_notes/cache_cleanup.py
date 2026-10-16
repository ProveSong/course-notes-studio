"""Remove only reproducible audio intermediates after a fully successful batch.

Evidence, screenshots, formulas, conversations, model files and handouts remain.
"""
import json
from pathlib import Path


def cleanup_batch(report, output):
    root = Path(output).resolve()
    if not report or any(row.get('status') != 'success' for row in report):
        return []
    jobs = []
    for row in report:
        job = Path(row['job'])
        if job.is_symlink() or job.resolve().parent != root:
            raise ValueError('缓存目录不在本批输出目录内')
        target = Path(row['target'])
        if not target.is_file() or not (job/'speech.json').is_file():
            raise ValueError('讲义或原始转录缺失，拒绝清理缓存')
        requests = job/'review-requests.json'
        if requests.exists():
            for item in json.loads(requests.read_text('utf-8')):
                if item['status'] not in ('reviewed', 'denied'):
                    raise ValueError('截图复核尚未完成，拒绝清理缓存')
                if item['status'] == 'reviewed' and not (job/'chunks'/f"{item['id']}.board.md").is_file():
                    raise ValueError('截图图形处理尚未完成，拒绝清理缓存')
        jobs.append(job)
    removed = []
    for job in jobs:
        path = job/'audio.wav'
        if path.is_file() and not path.is_symlink():
            size = path.stat().st_size
            path.unlink()
            removed.append({'file': str(path), 'bytes': size})
    (root/'cache-cleanup.json').write_text(json.dumps(removed, ensure_ascii=False, indent=2), 'utf-8')
    return removed
