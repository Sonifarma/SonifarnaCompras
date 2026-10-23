from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from atualizar import update
from manutencao import REQUIRED_FILES, verify_backup


class UpdateWorkflow(unittest.TestCase):
    def setUp(self):
        import os
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.destination=self.root/'installed'
        self.destination.mkdir()
        self.database=self.destination/'compras.sqlite3'
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE preserved(value TEXT)')
            c.execute('INSERT INTO preserved VALUES(?)',('existing account and data',))
        (self.destination/'app.py').write_text('# previous version')
        self.environment=patch.dict(os.environ,{'SONIFARMA_COMPRAS_DB':str(self.database)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def package(self,root):
        path=self.root/'package.zip'
        with zipfile.ZipFile(path,'w') as archive:
            for name in REQUIRED_FILES:
                archive.writestr(root+'/'+name,'# new version' if name.endswith('.py') else 'new version')
            archive.writestr(root+'/compras.sqlite3','must never overwrite')
            archive.writestr(root+'/.env','must never copy')
        return path

    def test_github_archive_preserves_database_and_backs_up(self):
        with patch('manutencao.require_stopped'):
            backup,code=update(self.package('SonifarnaCompras-main'),self.destination)
        self.assertEqual(verify_backup(backup),['compras.sqlite3'])
        self.assertEqual((code/'app.py').read_text(),'# previous version')
        with sqlite3.connect(self.database) as c:
            self.assertEqual(c.execute('SELECT value FROM preserved').fetchone()[0],'existing account and data')
        self.assertFalse((self.destination/'.env').exists())
        self.assertEqual((self.destination/'app.py').read_text(),'# new version')

    def test_running_application_blocks_update(self):
        with patch('socket.socket.connect_ex',return_value=0),self.assertRaises(ValueError):
            update(self.package('Sonifarmacompras'),self.destination)
        self.assertEqual((self.destination/'app.py').read_text(),'# previous version')

    def test_path_traversal_blocks_update(self):
        path=self.package('SonifarnaCompras-main')
        with zipfile.ZipFile(path,'a') as archive:archive.writestr('SonifarnaCompras-main/../app.py','invalid')
        with self.assertRaises(ValueError):update(path,self.destination)
        self.assertEqual((self.destination/'app.py').read_text(),'# previous version')

    def test_duplicate_code_blocked(self):
        path=self.package('SonifarnaCompras-main')
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(path,'a') as archive:archive.writestr('SonifarnaCompras-main/app.py','# duplicate')
        with self.assertRaises(ValueError):update(path,self.destination)

    def test_mixed_archive_roots_blocked(self):
        path=self.package('SonifarnaCompras-main')
        with zipfile.ZipFile(path,'a') as archive:archive.writestr('Sonifarmacompras/auth.py','# other root')
        with self.assertRaises(ValueError):update(path,self.destination)
