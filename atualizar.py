"""Compatibility entry point: ZIP or extracted source, using verified CRM-style maintenance."""
import argparse
import sqlite3
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from manutencao import CODE_FILES, update_code

ROOTS = {'Sonifarmacompras', 'SonifarnaCompras-main'} | {
    'SonifarnaCompras-v1.' + str(n) for n in range(7, 13)
}


def update(package, destination, backup_dir=None):
    destination = Path(destination).resolve()
    backup_dir = backup_dir or destination / 'backups'
    with tempfile.TemporaryDirectory() as staging, zipfile.ZipFile(package) as archive:
        root = Path(staging)
        seen = set()
        archive_root = None
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if not parts or parts[0] not in ROOTS or '..' in parts or '\\' in entry.filename:
                raise ValueError('Estrutura de pacote inválida.')
            if archive_root is not None and archive_root != parts[0]:
                raise ValueError('Pacote com mais de uma raiz.')
            archive_root = parts[0]
            name = '/'.join(parts[1:])
            if entry.is_dir() or name not in CODE_FILES:
                continue
            if name in seen:
                raise ValueError('Arquivo duplicado no pacote: ' + name)
            seen.add(name)
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(entry))
        return update_code(destination, root, backup_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pacote', type=Path)
    group.add_argument('--origem', type=Path)
    parser.add_argument('--destino', required=True, type=Path)
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.origem:
            result = update_code(args.destino, args.origem, args.backup_dir or args.destino / 'backups')
        else:
            result = update(args.pacote, args.destino, args.backup_dir)
        print('Código atualizado. Backup verificado:', result[0])
        print('Código anterior:', result[1])
        print('Execute iniciar.bat para iniciar e validar o painel.')
    except (ValueError, OSError, RuntimeError, SyntaxError, sqlite3.Error, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
