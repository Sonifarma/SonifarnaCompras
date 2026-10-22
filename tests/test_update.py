import hashlib
import json
import shutil
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from atualizar import update


class UpdateWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.destination = self.root / 'installed'
        self.destination.mkdir()
        self.database = self.destination / 'compras.sqlite3'
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE preserved (value TEXT)')
            c.execute('INSERT INTO preserved VALUES (?)', ('existing account and data',))
        self.original = hashlib.sha256(self.database.read_bytes()).digest()
        (self.destination / 'app.py').write_text('previous version')

    def package(self, root):
        path = self.root / 'package.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name in ['app.py', 'auth.py', 'templates/login.html']:
                archive.writestr(root + '/' + name, '# new version')
            archive.writestr(root + '/compras.sqlite3', 'must never overwrite database')
        return path

    def test_github_archive_preserves_database_and_backs_up(self):
        with patch('socket.socket.connect_ex', return_value=1):
            update(self.package('SonifarnaCompras-main'), self.destination)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).digest(), self.original)
        self.assertEqual((self.destination / 'app.py').read_text(), '# new version')
        backup = next(self.root.glob('SonifarmaCompras-backup-*'))
        self.assertEqual((backup / 'app.py').read_text(), 'previous version')
        with sqlite3.connect(backup / 'compras.sqlite3') as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('SELECT value FROM preserved').fetchone()[0], 'existing account and data')

    def test_running_application_blocks_update(self):
        with patch('socket.socket.connect_ex', return_value=0), self.assertRaises(SystemExit):
            update(self.package('Sonifarmacompras'), self.destination)
        self.assertEqual((self.destination / 'app.py').read_text(), 'previous version')

    def test_path_traversal_blocks_update(self):
        path = self.package('SonifarnaCompras-main')
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr('SonifarnaCompras-main/../app.py', 'invalid')
        with patch('socket.socket.connect_ex', return_value=1), self.assertRaises(SystemExit):
            update(path, self.destination)
        self.assertEqual((self.destination / 'app.py').read_text(), 'previous version')

    def test_invalid_python_blocks_update_before_backup(self):
        path = self.root / 'invalid.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('SonifarnaCompras-main/app.py', 'def invalid(')
            archive.writestr('SonifarnaCompras-main/auth.py', '# valid')
            archive.writestr('SonifarnaCompras-main/templates/login.html', '<html></html>')
        with patch('socket.socket.connect_ex', return_value=1), self.assertRaises(SystemExit):
            update(path, self.destination)
        self.assertEqual((self.destination / 'app.py').read_text(), 'previous version')
        self.assertFalse(list(self.root.glob('SonifarmaCompras-backup-*')))

    def test_copy_failure_restores_previous_code(self):
        original_copy = shutil.copy2
        failed = False

        def fail_once(source, destination, *args, **kwargs):
            nonlocal failed
            if Path(destination) == self.destination / 'auth.py' and not failed:
                failed = True
                raise PermissionError('Simulated copy failure')
            return original_copy(source, destination, *args, **kwargs)

        with patch('socket.socket.connect_ex', return_value=1), patch('shutil.copy2', side_effect=fail_once), self.assertRaises(SystemExit) as result:
            update(self.package('SonifarnaCompras-main'), self.destination)
        self.assertIn('Código anterior restaurado', str(result.exception))
        self.assertEqual((self.destination / 'app.py').read_text(), 'previous version')
        self.assertFalse((self.destination / 'auth.py').exists())
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).digest(), self.original)
        backup = next(self.root.glob('SonifarmaCompras-backup-*'))
        manifest = json.loads((backup / 'manifesto-sha256.json').read_text())
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((backup / name).read_bytes()).hexdigest(), digest)
