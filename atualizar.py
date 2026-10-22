"""Atualiza o código a partir do ZIP, preservando dados e criando backup."""
import argparse
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
        allowed_files = {'app.py', 'auth.py', 'atualizar.py', 'iniciar.bat', 'requirements.txt', 'requirements-dev.txt', 'README.md', 'LEIA-ME.txt', 'ATUALIZAR.md', 'AGENTS.md', '.gitignore', 'atualizar-github.ps1'}
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if not parts or parts[0] not in {'Sonifarmacompras', 'SonifarnaCompras-main', 'SonifarnaCompras-v1.7'} or '..' in parts or '\\' in entry.filename:
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
        for relative in selected:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
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
