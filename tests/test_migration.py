import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest


class AdditiveMigration(unittest.TestCase):
    def test_old_database_preserves_purchases_and_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            database=Path(tmp)/'old.sqlite3'
            with sqlite3.connect(database) as c:
                c.executescript('''CREATE TABLE processes(id INTEGER PRIMARY KEY,name TEXT,created TEXT);
                INSERT INTO processes VALUES(10,'Existing purchase','2026-01-01');
                CREATE TABLE needs(id INTEGER PRIMARY KEY,process_id INTEGER,code TEXT,name TEXT,qty REAL,unit TEXT,last_cost REAL,previous_supplier TEXT);
                INSERT INTO needs VALUES(20,10,'A','Amido',5000,'G',0.01,'Previous');
                CREATE TABLE app_users(username TEXT PRIMARY KEY,password_hash TEXT NOT NULL,must_change INTEGER NOT NULL DEFAULT 1,failures INTEGER NOT NULL DEFAULT 0,locked_until REAL NOT NULL DEFAULT 0);
                INSERT INTO app_users VALUES('admin','preserve-existing-hash',0,0,0);''')
            check="""import app
with app.db() as c:
 assert c.execute('SELECT password_hash FROM app_users WHERE username=?',('admin',)).fetchone()[0]=='preserve-existing-hash'
 assert c.execute('SELECT qty FROM needs WHERE id=20').fetchone()[0]==5000
 assert c.execute('SELECT last_pack_qty FROM needs WHERE id=20').fetchone()[0] is None
 assert c.execute('SELECT delivery_date FROM processes WHERE id=10').fetchone()[0] is None
 assert c.execute('SELECT COUNT(*) FROM supplier_terms').fetchone()[0]==0
"""
            subprocess.run(['python','-c',check],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'SONIFARMA_COMPRAS_DB':str(database)},check=True,capture_output=True)
