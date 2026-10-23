"""Atualiza o código a partir do ZIP, preservando dados e criando backup."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
import shutil
import socket
import sqlite3
import tempfile
import zipfile


def update(package, destination):
    destination = Path(destination).resolve()
    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(('127.0.0.1', 8766)) == 0:
            raise SystemExit('Feche o Sonifarma Compras (porta 8766) antes de atualizar.')
    with zipfile.ZipFile(package) as archive, tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        selected = []
        allowed_files = {'app.py', 'auth.py', 'procurement.py', 'atualizar.py', 'iniciar.bat', 'requirements.txt', 'requirements-dev.txt', 'README.md', 'LEIA-ME.txt', 'ATUALIZAR.md', 'AGENTS.md', '.gitignore', 'atualizar-github.ps1'}
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if not parts or parts[0] not in {'Sonifarmacompras', 'SonifarnaCompras-main', 'SonifarnaCompras-v1.7', 'SonifarnaCompras-v1.8', 'SonifarnaCompras-v1.9'} or '..' in parts or '\\' in entry.filename:
                raise SystemExit('Estrutura de pacote inválida.')
            relative = Path(*parts[1:])
            if entry.is_dir() or not relative.parts:
                continue
            # Never overwrite databases, account sessions, local config or sample data.
            if str(relative) not in allowed_files and relative.parts[0] not in {'static', 'templates', 'tests'}:
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
            selected.append(relative)
        if not all((root / name).is_file() for name in ['app.py', 'auth.py', 'templates/login.html']):
            raise SystemExit('Pacote incompleto. Nada foi alterado.')
        for relative in selected:
            if relative.suffix == '.py':
                try:
                    compile((root / relative).read_bytes(), str(relative), 'exec')
                except (SyntaxError, ValueError) as error:
                    raise SystemExit(f'Python inválido em {relative}: {error}. Nada foi alterado.')
        if b'from procurement import' in (root / 'app.py').read_bytes() and not (root / 'procurement.py').is_file():
            raise SystemExit('Pacote incompleto: procurement.py ausente. Nada foi alterado.')
        database = destination / 'compras.sqlite3'
        if not database.is_file():
            raise SystemExit('Banco compras.sqlite3 não encontrado no destino. Confira a pasta da instalação existente.')
        for relative in selected:
            target = destination / relative
            if target.is_symlink() or not target.resolve().is_relative_to(destination):
                raise SystemExit('Destino com link externo não permitido. Nada foi alterado.')
        backup = destination.parent / ('SonifarmaCompras-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir()
        for relative in selected:
            existing = destination / relative
            if existing.is_file():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing, saved)
        with sqlite3.connect(database) as source, sqlite3.connect(backup / 'compras.sqlite3') as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise SystemExit('Falha ao verificar backup. Atualização cancelada.')
        manifest = {str(path.relative_to(backup)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in backup.rglob('*') if path.is_file()}
        (backup / 'manifesto-sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        attempted = []
        try:
            for relative in selected:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                attempted.append(relative)
                shutil.copy2(root / relative, target)
        except OSError as error:
            failures = []
            for relative in reversed(attempted):
                target = destination / relative
                saved = backup / relative
                try:
                    if saved.is_file():
                        shutil.copy2(saved, target)
                    else:
                        target.unlink(missing_ok=True)
                except OSError:
                    failures.append(str(relative))
            detail = ('Falha ao restaurar: ' + ', '.join(failures)) if failures else 'Código anterior restaurado.'
            raise SystemExit(f'Falha ao atualizar: {error}. {detail} Banco preservado. Backup: {backup}')
        print('Atualização concluída. Banco e usuários preservados.')
        print('Backup:', backup)
        print('Execute iniciar.bat para atualizar as dependências e iniciar.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pacote', type=Path)
    group.add_argument('--origem', type=Path, help='Checkout baixado do GitHub')
    parser.add_argument('--destino', required=True, type=Path)
    options = parser.parse_args()
    if options.origem:
        origin = options.origem.resolve()
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'codigo.zip'
            with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
                for item in origin.rglob('*'):
                    relative = item.relative_to(origin)
                    if any(part in {'.git', '.venv', '__pycache__'} for part in relative.parts):
                        continue
                    if item.is_symlink():
                        raise SystemExit('Origem contém link simbólico não permitido.')
                    if item.is_file():
                        archive.write(item, Path('Sonifarmacompras') / relative)
            update(package, options.destino)
    else:
        update(options.pacote, options.destino)
