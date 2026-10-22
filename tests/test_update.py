import hashlib
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
                archive.writestr(root + '/' + name, 'new version')
            archive.writestr(root + '/compras.sqlite3', 'must never overwrite database')
        return path

    def test_github_archive_preserves_database_and_backs_up(self):
        with patch('socket.socket.connect_ex', return_value=1):
            update(self.package('SonifarnaCompras-main'), self.destination)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).digest(), self.original)
        self.assertEqual((self.destination / 'app.py').read_text(), 'new version')
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
