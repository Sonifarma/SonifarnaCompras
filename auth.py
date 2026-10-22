"""Local authentication: salted password hashes and revocable SQLite sessions."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

COOKIE = 'sonifarma_compras_session'
TTL = 12 * 60 * 60


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000)
    return salt + '$' + digest.hex()


def verify_password(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split('$')[0]), stored)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def install_auth(app, db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS app_users (
          username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
          must_change INTEGER NOT NULL DEFAULT 1, failures INTEGER NOT NULL DEFAULT 0,
          locked_until REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS app_sessions (
          token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM app_users WHERE username=?', ('admin',)).fetchone():
            c.execute('INSERT INTO app_users(username,password_hash) VALUES (?,?)',
                      ('admin', password_hash('123456')))

    def current_user(request):
        token = request.cookies.get(COOKIE, '')
        if not token:
            return None
        with db() as c:
            return c.execute('''SELECT u.* FROM app_users u JOIN app_sessions s
              ON s.username=u.username WHERE s.token_hash=? AND s.expires>?''',
                             (token_hash(token), time.time())).fetchone()

    @app.middleware('http')
    async def authenticate(request: Request, call_next):
        path = request.url.path
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            expected = urlsplit(str(request.url))
            if origin and origin != f'{expected.scheme}://{expected.netloc}':
                return JSONResponse({'detail': 'Origem da solicitação não permitida'}, status_code=403)
            if request.headers.get('x-sonifarma-request') != '1':
                return JSONResponse({'detail': 'Cabeçalho de proteção ausente'}, status_code=403)
        if path == '/' or path.startswith('/api/'):
            public = {'/api/auth/login', '/api/auth/status'}
            if path not in public:
                user = current_user(request)
                if user is None:
                    if path == '/':
                        return RedirectResponse('/login', status_code=303)
                    return JSONResponse({'detail': 'Entre para continuar'}, status_code=401)
                if user['must_change'] and path not in {'/api/auth/password', '/api/auth/logout'}:
                    if path == '/':
                        return RedirectResponse('/login', status_code=303)
                    return JSONResponse({'detail': 'Altere a senha inicial para continuar'}, status_code=403)
        response = await call_next(request)
        if path == '/' or path == '/login' or path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/api/auth/status')
    def status(request: Request):
        user = current_user(request)
        return {'authenticated': user is not None,
                'username': user['username'] if user else None,
                'must_change': bool(user['must_change']) if user else False}

    @app.post('/api/auth/login')
    def login(username: str = Form(...), password: str = Form(...)):
        with db() as c:
            user = c.execute('SELECT * FROM app_users WHERE username=?', (username,)).fetchone()
            if user and user['locked_until'] > time.time():
                raise HTTPException(429, 'Muitas tentativas. Aguarde 5 minutos e tente novamente.')
            if not user or len(password) > 1024 or not verify_password(password, user['password_hash']):
                if user:
                    failures = user['failures'] + 1
                    c.execute('UPDATE app_users SET failures=?,locked_until=? WHERE username=?',
                              (failures if failures < 5 else 0, time.time() + 300 if failures >= 5 else 0, username))
                    c.commit()
                raise HTTPException(401, 'Usuário ou senha inválidos')
            c.execute('UPDATE app_users SET failures=0,locked_until=0 WHERE username=?', (username,))
            c.execute('DELETE FROM app_sessions WHERE expires<=?', (time.time(),))
            token = secrets.token_urlsafe(32)
            c.execute('INSERT INTO app_sessions VALUES (?,?,?)', (token_hash(token), username, time.time() + TTL))
        response = JSONResponse({'ok': True, 'must_change': bool(user['must_change'])})
        response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite='strict',
                            secure=os.environ.get('SONIFARMA_COOKIE_SECURE') == '1')
        return response

    @app.post('/api/auth/password')
    def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...)):
        user = current_user(request)
        if not 8 <= len(new_password) <= 128:
            raise HTTPException(400, 'Use uma nova senha de 8 a 128 caracteres')
        if not verify_password(current_password, user['password_hash']):
            raise HTTPException(400, 'Senha atual incorreta')
        if new_password == current_password:
            raise HTTPException(400, 'A nova senha deve ser diferente da senha atual')
        with db() as c:
            c.execute('UPDATE app_users SET password_hash=?,must_change=0 WHERE username=?',
                      (password_hash(new_password), user['username']))
            c.execute('DELETE FROM app_sessions WHERE username=?', (user['username'],))
        response = JSONResponse({'ok': True, 'message': 'Senha alterada. Entre novamente.'})
        response.delete_cookie(COOKIE)
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request):
        with db() as c:
            c.execute('DELETE FROM app_sessions WHERE token_hash=?',
                      (token_hash(request.cookies.get(COOKIE, '')),))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response
