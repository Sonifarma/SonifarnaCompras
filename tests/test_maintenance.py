from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from manutencao import create_backup, verify_backup, update_code, REQUIRED_FILES, health


class Maintenance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.base=self.root/'installed'
        self.source=self.root/'new'
        self.backups=self.root/'backups'
        self.base.mkdir();self.source.mkdir()
        self.database=self.base/'compras.sqlite3'
        self.environment=patch.dict(os.environ,{'SONIFARMA_COMPRAS_DB':str(self.database)})
        self.environment.start();self.addCleanup(self.environment.stop)
        with closing(sqlite3.connect(self.database)) as c:
            c.execute('CREATE TABLE data(value TEXT)')
            c.execute('INSERT INTO data VALUES(?)',('preserved',));c.commit()
        (self.base/'app.py').write_text('# previous')
        for name in REQUIRED_FILES:
            target=self.source/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('# new' if name.endswith('.py') else 'new')

    def test_wal_backup_includes_committed_transactions(self):
        with closing(sqlite3.connect(self.database)) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('INSERT INTO data VALUES(?)',('committed in WAL',));c.commit()
            archive=create_backup(self.base,self.backups)
            self.assertEqual(verify_backup(archive),['compras.sqlite3'])
            with zipfile.ZipFile(archive) as z:
                restored=self.root/'restored.sqlite3';restored.write_bytes(z.read('compras.sqlite3'))
            with closing(sqlite3.connect(restored)) as restored:
                self.assertEqual(restored.execute('SELECT COUNT(*) FROM data').fetchone()[0],2)

    def test_tampered_backup_rejected(self):
        original=create_backup(self.base,self.backups)
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(original) as src,zipfile.ZipFile(bad,'w') as dst:
            dst.writestr('manifest.json',src.read('manifest.json'))
            dst.writestr('compras.sqlite3',b'tampered')
        with self.assertRaises(ValueError):verify_backup(bad)

    def test_bad_database_rejected_even_with_valid_hash(self):
        bad=self.root/'bad.zip';data=b'not sqlite'
        with zipfile.ZipFile(bad,'w') as z:
            z.writestr('compras.sqlite3',data)
            z.writestr('manifest.json',json.dumps({'files':{'compras.sqlite3':hashlib.sha256(data).hexdigest()}}))
        with self.assertRaises(sqlite3.DatabaseError):verify_backup(bad)

    def test_duplicate_backup_entries_rejected(self):
        import warnings
        original=create_backup(self.base,self.backups)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(original,'a') as z:z.writestr('compras.sqlite3',b'duplicate')
        with self.assertRaises(ValueError):verify_backup(original)

    def test_python_validation_before_backup(self):
        (self.source/'app.py').write_text('def invalid(')
        with patch('manutencao.require_stopped'),self.assertRaises(SyntaxError):
            update_code(self.base,self.source,self.backups)
        self.assertFalse(self.backups.exists())
        self.assertEqual((self.base/'app.py').read_text(),'# previous')

    def test_incomplete_package_before_backup(self):
        (self.source/'auth.py').unlink()
        with patch('manutencao.require_stopped'),self.assertRaises(ValueError):
            update_code(self.base,self.source,self.backups)
        self.assertFalse(self.backups.exists())

    def test_atomic_copy_failure_rolls_back_without_touching_database(self):
        before=self.database.read_bytes()
        original=shutil.copyfile
        def fail(source,destination,*args,**kwargs):
            if Path(source)==self.source/'auth.py':raise PermissionError('simulated copy failure')
            return original(source,destination,*args,**kwargs)
        with patch('manutencao.require_stopped'),patch('shutil.copyfile',side_effect=fail),self.assertRaises(RuntimeError) as error:
            update_code(self.base,self.source,self.backups)
        self.assertIn('Código anterior restaurado',str(error.exception))
        self.assertEqual((self.base/'app.py').read_text(),'# previous')
        self.assertFalse((self.base/'auth.py').exists())
        self.assertEqual(self.database.read_bytes(),before)
        verify_backup(next(self.backups.glob('*.zip')))
        self.assertFalse(list(self.base.glob('tmp*')))

    def test_update_only_explicit_code_files(self):
        (self.source/'compras.sqlite3').write_text('do not copy')
        (self.source/'.env').write_text('do not copy')
        (self.source/'static').mkdir(exist_ok=True)
        (self.source/'static'/'local-config.json').write_text('do not copy')
        with patch('manutencao.require_stopped'):
            backup,code=update_code(self.base,self.source,self.backups)
        verify_backup(backup)
        self.assertTrue((code/'app.py').is_file())
        self.assertFalse((self.base/'.env').exists())
        self.assertFalse((self.base/'static'/'local-config.json').exists())
        manifest=json.loads((code/'manifesto-sha256.json').read_text())
        for name,digest in manifest.items():self.assertEqual(hashlib.sha256((code/name).read_bytes()).hexdigest(),digest)

    def test_external_database_override_blocks_maintenance(self):
        with patch.dict(os.environ,{'SONIFARMA_COMPRAS_DB':str(self.root/'other.sqlite3')}),self.assertRaises(ValueError):
            create_backup(self.base,self.backups)

    def test_health_checks_response_shape(self):
        class Response(io.BytesIO):status=200
        with patch('urllib.request.urlopen',return_value=Response(b'{"authenticated":false,"must_change":false}')):
            self.assertTrue(health('http://127.0.0.1:8766'))
        with patch('urllib.request.urlopen',return_value=Response(b'{"ok":true}')),self.assertRaises(ValueError):
            health('http://127.0.0.1:8766')
