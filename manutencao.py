"""Verified SQLite backups and code-only updates for Sonifarma Compras."""
import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
import urllib.request
import zipfile

DATABASE = 'compras.sqlite3'
CODE_FILES = (
    'app.py', 'auth.py', 'procurement.py', 'iniciar_servidor.py', 'manutencao.py',
    'atualizar.py', 'SONIFARMA_CONTROLE.ps1', 'atualizar-github.ps1',
    'iniciar.bat', 'START_SONIFARMA.bat', 'STOP_SONIFARMA.bat',
    'RESTART_SONIFARMA.bat', 'STATUS_SONIFARMA.bat', 'ATUALIZAR_SONIFARMA.bat',
    'requirements.txt', 'requirements-dev.txt', 'README.md', 'ATUALIZAR.md',
    'LEIA-ME.txt', 'AGENTS.md', '.gitignore', '.gitattributes',
    'templates/index.html', 'templates/login.html', 'static/app.js',
    'static/auth.js', 'static/style.css', 'static/sonifarma-logo.png',
    'tests/test_workflow.py', 'tests/test_update.py', 'tests/test_procurement.py',
    'tests/test_rules_api.py', 'tests/test_migration.py', 'tests/test_maintenance.py', 'tests/test_import_batch.py',
    'tests/test_controle.ps1', 'tests/test_atualizador.ps1',
)
REQUIRED_FILES = ('app.py', 'auth.py', 'procurement.py', 'iniciar_servidor.py',
                  'manutencao.py', 'atualizar.py', 'SONIFARMA_CONTROLE.ps1',
                  'templates/index.html', 'templates/login.html', 'static/app.js',
                  'static/auth.js', 'static/style.css', 'requirements.txt')


def _check_database(base):
    database = base / DATABASE
    override = os.environ.get('SONIFARMA_COMPRAS_DB')
    if override and Path(override).resolve() != database.resolve():
        raise ValueError('SONIFARMA_COMPRAS_DB aponta para outro banco. Manutenção cancelada para não copiar o banco errado.')
    if not database.is_file() or database.is_symlink():
        raise ValueError('Banco compras.sqlite3 não encontrado ou é um link simbólico.')
    return database


def verify_backup(archive):
    with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read('manifest.json'))
        files = manifest.get('files', {})
        if set(files) != {DATABASE}:
            raise ValueError('Backup sem o banco esperado')
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != {DATABASE, 'manifest.json'}:
            raise ValueError('Conteúdo inesperado no backup')
        data = z.read(DATABASE)
        if hashlib.sha256(data).hexdigest() != files[DATABASE]:
            raise ValueError('Checksum inválido do banco')
        restored = Path(work) / DATABASE
        restored.write_bytes(data)
        with closing(sqlite3.connect(restored.resolve().as_uri() + '?mode=ro', uri=True)) as c:
            if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Banco restaurado inválido')
    return [DATABASE]


def create_backup(base, destination):
    base, destination = Path(base).resolve(), Path(destination).resolve()
    database = _check_database(base)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ('compras_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.zip')
    with tempfile.TemporaryDirectory(dir=destination) as work:
        work = Path(work)
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(work / DATABASE)) as copied:
                source.backup(copied)
        digest = hashlib.sha256((work / DATABASE).read_bytes()).hexdigest()
        pending = work / 'backup.zip'
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(work / DATABASE, DATABASE)
            z.writestr('manifest.json', json.dumps({'version': 1, 'files': {DATABASE: digest}}))
        verify_backup(pending)
        pending.replace(target)
    return target


def require_stopped():
    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(('127.0.0.1', 8766)) == 0:
            raise ValueError('Porta 8766 ocupada. Pare o Compras antes de atualizar. Nenhum processo foi encerrado automaticamente.')


def update_code(base, source, backup_dir):
    base, source, backup_dir = map(lambda p: Path(p).resolve(), (base, source, backup_dir))
    if base == source or source.is_relative_to(base) or base.is_relative_to(source):
        raise ValueError('Origem e instalação devem ser pastas separadas, sem sobreposição.')
    _check_database(base)
    require_stopped()
    for name in REQUIRED_FILES:
        if not (source / name).is_file():
            raise ValueError('Pacote incompleto: ' + name)
    selected = []
    for name in CODE_FILES:
        path, target = source / name, base / name
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('Origem contém link externo: ' + name)
        if target.is_symlink() or not target.resolve().is_relative_to(base):
            raise ValueError('Destino contém link externo: ' + name)
        if not path.is_file():
            continue
        if path.suffix == '.py':
            compile(path.read_bytes(), name, 'exec')
        selected.append(name)
    backup = create_backup(base, backup_dir)
    rollback = backup_dir / ('codigo_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    rollback.mkdir()
    existing = set()
    for name in selected:
        path = base / name
        if path.is_file():
            saved = rollback / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
            existing.add(name)
    manifest = {name: hashlib.sha256((rollback / name).read_bytes()).hexdigest() for name in existing}
    (rollback / 'manifesto-sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    attempted = []
    try:
        for name in selected:
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            attempted.append(name)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                pending = Path(handle.name)
            try:
                shutil.copyfile(source / name, pending)
                pending.replace(target)
            finally:
                pending.unlink(missing_ok=True)
    except Exception as error:
        failures = []
        for name in reversed(attempted):
            try:
                if name in existing:
                    shutil.copy2(rollback / name, base / name)
                else:
                    (base / name).unlink(missing_ok=True)
            except OSError:
                failures.append(name)
        detail = 'Falha ao restaurar: ' + ', '.join(failures) if failures else 'Código anterior restaurado.'
        raise RuntimeError(f'Falha ao atualizar: {error}. {detail} Banco preservado. Código: {rollback}; backup: {backup}') from error
    return backup, rollback


def health(url):
    # urllib preserves normal TLS verification when an HTTPS address is supplied.
    with urllib.request.urlopen(url.rstrip('/') + '/api/auth/status', timeout=5) as response:
        status = json.load(response)
        if response.status != 200 or not all(isinstance(status.get(k), bool) for k in ('authenticated', 'must_change')):
            raise ValueError('Resposta de saúde inesperada')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'verify', 'update', 'health'))
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--url')
    args = parser.parse_args()
    try:
        if args.action == 'backup':
            print('Backup verificado:', create_backup(args.base, args.destination or args.base / 'backups'))
        elif args.action == 'verify':
            if not args.archive:
                parser.error('verify exige --archive')
            print('Restauração temporária e integridade verificadas:', ', '.join(verify_backup(args.archive)))
        elif args.action == 'update':
            if not args.source or not args.destination:
                parser.error('update exige --source e --destination')
            backup, rollback = update_code(args.base, args.source, args.destination)
            print('Código atualizado. Backup verificado:', backup)
            print('Código anterior:', rollback)
            print('Inicie e valide o painel. Banco e senhas preservados.')
        else:
            if not args.url:
                parser.error('health exige --url')
            health(args.url)
            print('Compras respondeu corretamente.')
    except (ValueError, OSError, RuntimeError, SyntaxError, sqlite3.Error, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
