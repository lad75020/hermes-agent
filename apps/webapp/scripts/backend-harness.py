"""In-process integration harness: REAL Hermes ASGI app and bundled basic auth.

Test-only JSON-lines transport for the browser smoke. No listener, model prompts,
production state, or authentication mocks. HERMES_HOME must point inside .scratch.
"""
import contextlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
APP = Path(__file__).resolve().parents[1]
home = Path(os.environ['HERMES_HOME']).resolve()
if not home.is_relative_to(APP / '.scratch'):
    raise SystemExit('Harness requires HERMES_HOME under apps/webapp/.scratch')
home.mkdir(parents=True, exist_ok=True)
if not (home / 'config.yaml').exists():
    (home / 'config.yaml').write_text('model:\n  default: webapp-smoke-model\n  provider: openai\nonboarding:\n  run: false\ntelemetry:\n  shared_metrics:\n    enabled: false\n')
# A home nested below the operator's default root is deliberately recognized as
# part of that root by Hermes. Relocate the platform-default root too, so every
# profile lookup in this TEST process remains inside the isolated fixture.
platform_home = patch('hermes_constants._get_platform_default_hermes_home', return_value=home)
platform_home.start()
# Preserve stdout exclusively for frames; dependency logs go to stderr.
wire = sys.stdout
sys.stdout = sys.stderr
os.environ['HERMES_SERVE_HEADLESS'] = '1'
from fastapi.testclient import TestClient
from hermes_cli import web_server
from hermes_cli.dashboard_auth import clear_providers, register_provider
from plugins.dashboard_auth.basic import BasicAuthProvider, hash_password
from hermes_state import SessionDB

# This checkout's install/update lock belongs to the running operator environment.
# The harness uses the already-installed interpreter and never provisions packages.
# Only package bootstrap is stubbed; auth, routes, dispatcher and persistence are real.
with patch('hermes_cli.venv_sync.prepare_launch', return_value=None), patch('pm.environments.activate_dependencies'), patch('hermes_cli._early_recovery.recover_if_needed'):
    import tui_gateway.server

db = SessionDB(home / 'state.db')
if not db.get_session('webapp-smoke-history'):
    db.create_session('webapp-smoke-history', source='desktop')
    db.set_session_title('webapp-smoke-history', 'Browser smoke history')
if not db.get_session('webapp-smoke-history')['message_count']:
    db.append_message('webapp-smoke-history', role='user', content='Saved test history; no model request was made.')
    db.append_message('webapp-smoke-history', role='assistant', content='Saved fixture reply; no model request was made.')
    db.end_session('webapp-smoke-history', 'completed')
db.close()

clear_providers()
register_provider(BasicAuthProvider(username='webapp-test', password_hash=hash_password('isolated-browser-smoke-only'), secret=os.urandom(32)))
web_server.app.state.auth_required = True
web_server.app.state.bound_host = '127.0.0.1'
web_server.app.state.bound_port = 8642
web_server.app.state.trusted_public_hosts = frozenset({'hermes-webapp.localhost'})
client = TestClient(web_server.app, base_url='http://hermes-webapp.localhost:8080', follow_redirects=False)
lock = threading.Lock()
sockets = {}

def emit(value):
    with lock:
        wire.write(json.dumps(value) + '\n')
        wire.flush()

def reader(key, session):
    try:
        while True:
            payload = session.receive_text()
            emit({'socket': key, 'data': payload})
    except Exception as error:
        emit({'socket': key, 'closed': str(error)})

emit({'ready': True})
for line in sys.stdin:
    try:
        request = json.loads(line)
        key = request['id']
        operation = request.get('op', 'http')
        request_path = request.get('path', '')
        print(operation, request_path if operation == 'http' else request_path.split('?')[0], file=sys.stderr, flush=True)
        if operation == 'http':
            response = client.request(request.get('method', 'GET'), request['path'], headers=request.get('headers', {}), content=request.get('body', '').encode())
            emit({'id': key, 'status': response.status_code, 'headers': list(response.headers.multi_items()), 'body': response.content.decode('utf-8', errors='replace')})
        elif operation == 'ws-open':
            context = client.websocket_connect('ws://hermes-webapp.localhost:8080' + request['path'], headers={'origin': 'http://hermes-webapp.localhost:8080'})
            session = context.__enter__()
            sockets[key] = (context, session)
            emit({'id': key, 'ok': True})
            threading.Thread(target=reader, args=(key, session), daemon=True).start()
        elif operation == 'ws-send':
            sockets[request['socket']][1].send_text(request['data'])
        elif operation == 'ws-close':
            context, session = sockets.pop(request['socket'])
            session.close()
            context.__exit__(None, None, None)
        elif operation == 'stop':
            break
    except Exception as error:
        emit({'id': request.get('id'), 'error': f'{type(error).__name__}: {error} code={getattr(error, "code", None)} reason={getattr(error, "reason", None)}'})
for context, session in sockets.values():
    with contextlib.suppress(Exception):
        session.close()
        context.__exit__(None, None, None)
client.close()
