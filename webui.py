#!/usr/bin/env python3
"""Local UI around the original CLI. Python 3.10+, standard library only."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
APP = json.loads((ROOT / 'ui/app.json').read_text())
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
JOB = None
PROVIDERS = {
    'groq': ('https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
    'openrouter': ('https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY'),
}

def load_env(path):
    """Read literal dotenv assignments. Never execute shell text."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        name, sep, value = line.partition('=')
        if sep and re.fullmatch(r'(?:LLM_[A-Z_]+|GROQ_API_KEY|OPENROUTER_API_KEY|OPENAI_API_KEY)', name.strip()):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(name.strip(), value)

def provider_key(provider):
    base, name = PROVIDERS[provider]
    if os.environ.get(name, '').strip():
        return os.environ[name].strip()
    if os.environ.get('LLM_BASE_URL', '').rstrip('/') == base:
        return os.environ.get('LLM_API_KEY', '').strip()
    return ''

def run_folder(name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name) or name.startswith('.'):
        raise ValueError('Invalid run name.')
    path = ROOT / 'runs' / name
    if path.is_symlink() or not path.resolve().is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('Invalid run folder.')
    return path

def runs():
    output = []
    try: notes=json.loads((ROOT/'run-notes.json').read_text())
    except (OSError,ValueError): notes={}
    for path in sorted((ROOT / 'runs').iterdir(), reverse=True):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            manifest = json.loads((path / 'manifest.json').read_text())
            result = json.loads((path / 'ui-result.json').read_text()) if (path / 'ui-result.json').exists() else {}
            complete = manifest.get('status') in ('complete', 'completed') and (path / 'report.html').is_file()
            status = 'completed' if complete else result.get('status', 'failed' if manifest.get('status')=='failed' else 'incomplete')
            with LOCK:
                if JOB and JOB['id'] == path.name and JOB['status'] == 'running':
                    status = 'running'
            output.append({'id': path.name, 'status': status, 'mode': manifest.get('mode', 'unknown'),
                           'ticker': manifest.get('ticker', ''), 'version': manifest.get('version', ''),
                           'as_of': manifest.get('as_of', ''), 'review_note': notes.get(path.name,''), 'error': result.get('error', manifest.get('error', '')),
                           'progress': json.loads((path/'progress.json').read_text()) if (path/'progress.json').exists() else {},
                           'accepted': sum(s.get('status') == 'accepted' for s in manifest.get('stages', [])),
                           'report': complete, 'seconds': result.get('seconds')})
        except (OSError, ValueError, TypeError):
            continue
    return output

def prepare_job(data):
    provider = data.get('provider')
    if provider not in PROVIDERS:
        raise ValueError('Choose Groq or OpenRouter.')
    key = data.get('key', '').strip() or provider_key(provider)
    if not key:
        raise ValueError('Add the selected provider’s key, or configure it in .env.')
    model = str(data.get('model', '')).strip()
    if not model or len(model) > 150 or re.search(r'\s', model):
        raise ValueError('Enter an exact model ID.')
    ticker = str(data.get('ticker', '')).strip().upper()
    if not re.fullmatch(r'[A-Z0-9&_.-]{1,30}', ticker):
        raise ValueError('Enter a valid ticker.')
    date = str(data.get('date', ''))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('Use YYYY-MM-DD for the research date.')
    dt.date.fromisoformat(date)
    version = data.get('version')
    if version not in ('v1', 'v2', 'v3', 'v4'):
        raise ValueError('Choose v1, v2, v3 or v4.')
    files = data.get('files', [])
    if not isinstance(files, list) or len(files) > 32:
        raise ValueError('Upload at most 32 documents.')
    total, checked = 0, []
    names = set()
    for file in files:
        name, content = file.get('name', ''), file.get('content', '')
        if not isinstance(content, str) or not re.fullmatch(r'[A-Za-z0-9_. -]{1,100}', name) or name.startswith('.') or Path(name).suffix.lower() not in ('.md', '.txt') or name.lower() == 'readme.md':
            raise ValueError('Use .md/.txt filenames without folders; README.md is excluded.')
        if name.casefold() in names:
            raise ValueError('Document filenames must be unique.')
        names.add(name.casefold())
        size = len(content.encode('utf-8')); total += size
        if size > 1024*1024 or total > 4*1024*1024:
            raise ValueError('Maximum: 1 MiB per document and 4 MiB total.')
        checked.append((name, content))
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'ui-{stamp}-{secrets.token_hex(3)}'
    docs = ROOT / 'research_pack'
    if checked:
        docs = ROOT / '.ui-uploads' / name
        docs.mkdir(parents=True)
        for filename, content in checked:
            (docs / filename).write_text(content, encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if not k.startswith('LLM_') and k not in ('GROQ_API_KEY', 'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'TYPESAFE_API_KEY')}
    env.update(LLM_API_KEY=key, LLM_BASE_URL=PROVIDERS[provider][0], LLM_MODEL=model,
               LLM_AUTH_MODE='bearer', LLM_JSON_MODE='json_object', LLM_TIMEOUT_SECONDS='120',
               LLM_MAX_TOKENS='6000' if provider == 'groq' else '16384',
               LLM_TOKEN_PARAMETER='max_completion_tokens' if provider == 'groq' else 'max_tokens')
    if provider == 'groq' and model == 'qwen/qwen3.8-27b':
        env['LLM_REASONING_EFFORT'] = 'none'
    cmd = [sys.executable, '-u', str(ROOT / 'briefcheck.py')] if APP['name'] == 'BriefCheck' else ['node', str(ROOT / 'src/cli.ts')]
    cmd += ['run', '--ticker', ticker, '--docs', str(docs), '--as-of', date, '--version', version,
            '--run' if APP['name'] == 'BriefCheck' else '--out', str(ROOT / 'runs' / name)]
    if version == 'v4':
        cmd = [sys.executable, '-u', str(ROOT/'v4.py'), 'run', '--ticker', ticker, '--docs', str(docs), '--as-of', date, '--out', str(ROOT/'runs'/name)]
        env['V4_MAX_OUTPUT_TOKENS'] = '8000' if provider == 'openrouter' and model == 'dots-studio/dots-3-note-preview:free' else '4000' if provider == 'openrouter' or model in ('openai/gpt-oss-20b','openai/gpt-oss-120b') else '900'
    return name, cmd, env, key

def worker(name, cmd, env, key):
    global JOB
    start = time.monotonic()
    try:
        process = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1800)
        success = process.returncode == 0 and (ROOT / 'runs' / name / 'report.html').is_file()
        error = '' if success else (process.stderr.strip() or process.stdout.strip() or 'No completed report was produced.')[-1600:]
    except subprocess.TimeoutExpired:
        success, error = False, 'Stopped after 30 minutes. The incomplete run is preserved.'
    except OSError:
        success, error = False, 'Could not start the CLI. Check the required Python/Node installation.'
    result = {'id': name, 'status': 'completed' if success else 'failed', 'seconds': round(time.monotonic()-start,1), 'error': error.replace(key, '[redacted]')}
    path = ROOT / 'runs' / name
    path.mkdir(parents=True, exist_ok=True)
    (path / 'ui-result.json').write_text(json.dumps(result, indent=2)+'\n')
    with LOCK:
        JOB = result

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, content, kind='application/json; charset=utf-8'):
        body = json.dumps(content).encode() if isinstance(content, (dict, list)) else content
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(body)

    def local(self):
        port = self.server.server_port
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.local():
            return self.send(403, {'error': 'Open the loopback URL printed by the server.'})
        url = urlsplit(self.path)
        if url.path == '/api/state':
            with LOCK:
                job = JOB.copy() if JOB else None
            return self.send(200, {'app': APP, 'token': TOKEN, 'keys': {p: bool(provider_key(p)) for p in PROVIDERS}, 'runs': runs(), 'job': job})
        if url.path in ('/', '/app.js', '/style.css'):
            name = {'/':'index.html', '/app.js':'app.js', '/style.css':'style.css'}[url.path]
            kind = {'index.html':'text/html', 'app.js':'text/javascript', 'style.css':'text/css'}[name]
            return self.send(200, (ROOT/'ui'/name).read_bytes(), kind+'; charset=utf-8')
        if url.path == '/artifact':
            params = parse_qs(url.query)
            try:
                name = params.get('file', [''])[0]
                if name not in ('report.html', 'brief.md'):
                    raise ValueError()
                path = run_folder(params.get('run',[''])[0]) / name
                if path.is_symlink():
                    raise ValueError()
                return self.send(200, path.read_bytes(), ('text/html' if name.endswith('.html') else 'text/plain')+'; charset=utf-8')
            except (ValueError, OSError):
                return self.send(404, {'error':'Report not found.'})
        self.send(404, {'error':'Not found.'})

    def do_POST(self):
        global JOB
        if not self.local() or self.headers.get('Origin') != 'http://'+self.headers.get('Host','') or self.headers.get('X-UI-Token') != TOKEN:
            return self.send(403, {'error':'Refresh this local page before generating.'})
        if self.path != '/api/generate':
            return self.send(404, {'error':'Not found.'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 6*1024*1024:
                raise ValueError('Request too large or empty.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            with LOCK:
                if JOB and JOB['status'] == 'running':
                    return self.send(409, {'error':'A generation is already running.'})
                name, cmd, env, key = prepare_job(data)
                JOB = {'id': name, 'status':'running', 'error':''}
            threading.Thread(target=worker, args=(name,cmd,env,key), daemon=True).start()
            self.send(202, {'id':name})
        except (ValueError, TypeError, AttributeError) as error:
            self.send(400, {'error':str(error)[:300]})

def main():
    parser = argparse.ArgumentParser(description='Local report viewer and generator')
    parser.add_argument('--port', type=int, default=APP['port'])
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    args = parser.parse_args()
    load_env(args.env_file)
    server = ThreadingHTTPServer(('127.0.0.1',args.port), Handler)
    print(f"{APP['name']}: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
