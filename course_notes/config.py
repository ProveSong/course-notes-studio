from __future__ import annotations

import json
import os
import sqlite3
import tomllib
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

LOCAL = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
ROOT = Path(os.environ.get('COURSE_NOTES_HOME', str(LOCAL/'CourseNotesStudio'))).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
RESOURCES = Path(__file__).resolve().parents[1]
if not (RESOURCES/'skills').is_dir() and (Path(sys.prefix)/'skills').is_dir():
    RESOURCES=Path(sys.prefix)


@dataclass
class Settings:
    video_captioner: str = str(LOCAL / 'VideoCaptioner')
    cc_database: str = str(Path.home() / '.cc-switch/cc-switch.db')
    provider: str = ''
    model: str = ''
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-flash'
    deepseek_protocol: str = 'messages'
    deepseek_reasoning_effort: str = 'off'
    vision_provider: str = ''
    vision_model: str = ''
    vision_transport: str = 'api'
    conversation_file: str = ''
    conversation_video: str = ''
    language: str = 'zh'
    whisper_model: str = 'large-v3-turbo'
    cleanup_cache_on_success: bool = False
    device: str = 'cuda'
    sample_seconds: float = 5.0
    max_gap_seconds: float = 30.0
    change_threshold: float = 0.015
    chunk_seconds: int = 180
    llm_workers: int = 1
    llm_transport: str = 'api'
    codex_executable: str = ''
    codex_timeout_seconds: int = 1200
    compact_notes: bool = True
    llm_max_output_tokens: int = 10000
    formula_backend: str = 'paddle'
    formula_model_dir: str = str(ROOT / 'DeepRead/models/formula')
    ocr_mode: str = 'printed'
    deepread_root: str = str(ROOT / 'DeepRead')
    deepread_python: str = ''
    ocr_language: str = 'ch'
    roi: str = ''
    visual_review: bool = False
    output_root: str = str(Path.home() / 'Documents/Course Notes')

    @classmethod
    def load(cls):
        path = ROOT / 'settings.json'
        result = cls(**{k:v for k,v in json.loads(path.read_text('utf-8')).items() if k in cls.__dataclass_fields__}) if path.exists() else cls()
        if not path.exists():
            source = Path(result.video_captioner) / 'AppData/settings.json'
            if source.exists():
                s = json.loads(source.read_text('utf-8')).get('FasterWhisper', {})
                result.whisper_model = s.get('Model', result.whisper_model)
                result.device = s.get('Device', result.device)
        return result

    def save(self):
        data=asdict(self);data.pop('conversation_file',None);data.pop('conversation_video',None)
        (ROOT / 'settings.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')


@dataclass
class Provider:
    identity: str
    name: str
    app: str
    base_url: str
    key: str
    model: str
    wire_api: str
    current: bool
    notes: str = ''

    @property
    def label(self):
        return f'{self.name}' + (f'（备注：{self.notes}）' if self.notes else '') + f' / {self.app} / {self.model or "需指定模型"}' + ('（当前）' if self.current else '')


def providers(database: str) -> list[Provider]:
    """Read credentials on demand; never copy them into settings or job manifests."""
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'CC Switch 数据库不存在：{path}')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM providers ORDER BY is_current DESC, sort_index, name').fetchall()
    result = []
    for row in rows:
        s = json.loads(row['settings_config'])
        app = row['app_type']
        env = s.get('env', {})
        if app == 'codex' and isinstance(s.get('config'), str):
            t = tomllib.loads(s['config'])
            backend = t.get('model_providers', {}).get(t.get('model_provider', ''), {})
            auth = s.get('auth', {})
            key = auth.get('OPENAI_API_KEY', '')
            url = backend.get('base_url', '')
            model = t.get('model', '')
            wire = backend.get('wire_api', 'responses')
        elif app == 'claude':
            key = env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY', '')
            url = env.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
            model = env.get('ANTHROPIC_MODEL', '')
            wire = 'anthropic'
        else:
            continue
        if key and url:
            result.append(Provider(f'{app}:{row["id"]}', row['name'], app, url.rstrip('/'), key, model, wire, bool(row['is_current']),row['notes'] or ''))
    return result


def available_providers(settings):
    try:items=providers(settings.cc_database)
    except (OSError,ValueError,sqlite3.Error):items=[]
    return items+[Provider('deepseek:direct','DeepSeek API','deepseek',settings.deepseek_base_url,'',settings.deepseek_model,'chat_completions',False)]


def visual_settings(settings):
    from dataclasses import replace
    if settings.provider!='deepseek:direct':return settings
    if not settings.vision_provider or settings.vision_provider=='deepseek:direct':
        model=settings.vision_model or settings.model or settings.deepseek_model
        if settings.deepseek_protocol=='messages' and model=='deepseek-flash':
            return replace(settings,model=model,llm_transport='api')
        raise ValueError('DeepSeek 截图复核请选择 Messages 接口和 deepseek-flash，或另选视觉模型。')
    return replace(settings,provider=settings.vision_provider,model=settings.vision_model,llm_transport=settings.vision_transport)


def selected_provider(settings: Settings):
    if settings.provider=='deepseek:direct':
        from .credential_store import deepseek_key
        from urllib.parse import urlsplit
        key=deepseek_key()
        if not key:raise ValueError('请在首次配置中填写 DeepSeek API Key，或设置 DEEPSEEK_API_KEY。')
        url=settings.deepseek_base_url.rstrip('/')
        if urlsplit(url).scheme!='https' or not urlsplit(url).netloc:raise ValueError('DeepSeek API 地址必须是有效 HTTPS 地址。')
        if urlsplit(url).username or urlsplit(url).password or urlsplit(url).query or urlsplit(url).fragment:
            raise ValueError('DeepSeek API 地址不能包含凭据、查询参数或片段。')
        protocol=settings.deepseek_protocol
        if protocol not in ('messages','chat_completions'):raise ValueError('未知 DeepSeek 接口。')
        if protocol=='messages' and url in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
            url='https://api.deepseek.com/anthropic'
        return Provider('deepseek:direct','DeepSeek API','deepseek',url,key,settings.model.strip() or settings.deepseek_model,'deepseek_messages' if protocol=='messages' else 'chat_completions',False)
    items = providers(settings.cc_database)
    if settings.provider:
        items = [p for p in items if p.identity == settings.provider]
    if not items:
        raise ValueError('CC Switch 中没有可用的 API Key 配置，请在配置页面选择供应商。')
    p = items[0]
    p.model = settings.model.strip() or p.model
    if not p.model:
        raise ValueError('此供应商未设置模型，请在模型栏填写模型名称。')
    return p
