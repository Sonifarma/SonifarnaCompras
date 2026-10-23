import io
import uuid
from unittest.mock import patch
import unittest
from openpyxl import Workbook
import fitz
import test_workflow as workflow
compras=workflow.compras


def workbook_bytes(rows, title='Planilha'):
    workbook=Workbook();workbook.active.title=title
    for row in rows:workbook.active.append(row)
    output=io.BytesIO();workbook.save(output)
    return output.getvalue()


def needs_file(product='Importado'):
    return workbook_bytes([['Código','Produto','Fornecedor','Quantidade','Unidade','Custo','Embalagem anterior qtd','Embalagem anterior unidade'],['X',product,'Anterior',100,'G',1,1,'KG']])


def quotes_file(product='Cotado'):
    return workbook_bytes([['Produto','Embalagem','Total'],[product,'5 KG',100]])


class BatchImports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):workflow.PurchaseWorkflow.setUpClass.__func__(cls)

    def setUp(self):workflow.PurchaseWorkflow.setUp(self)

    def count(self,table):
        with compras.db() as c:return c.execute('SELECT COUNT(*) FROM '+table+' WHERE process_id=?',(self.pid,)).fetchone()[0]

    def test_needs_mixed_files_and_history(self):
        response=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('one.xlsx',needs_file('Primeiro'))),('files',('bad.xlsx',b'broken')),('files',('two.xlsx',needs_file('Segundo')))])
        self.assertEqual(response.status_code,200)
        result=response.json()
        self.assertEqual((result['imported'],result['successful'],result['failed']),(2,2,1))
        self.assertEqual([row['status'] for row in result['results']],['success','error','success'])
        self.assertEqual(self.count('needs'),3)
        with compras.db() as c:
            n=c.execute('SELECT * FROM needs WHERE process_id=? AND name=?',(self.pid,'Primeiro')).fetchone()
            self.assertEqual(n['last_pack_qty'],1)
            self.assertEqual(n['last_pack_unit'],'KG')

    def test_quotes_keep_supplier_per_file_and_pdf_can_mix(self):
        document=fitz.open();page=document.new_page();page.insert_text((50,50),'Documento sem tabela reconhecida')
        pdf=document.tobytes();document.close()
        response=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['Fornecedor A','Fornecedor B','Fornecedor C']},files=[('files',('a.xlsx',quotes_file('Produto A'))),('files',('b.xlsx',quotes_file('Produto B'))),('files',('c.pdf',pdf))])
        result=response.json()
        self.assertEqual((result['imported'],result['successful'],result['empty']),(2,2,1))
        self.assertEqual(result['results'][0]['suppliers'],['Fornecedor A'])
        self.assertEqual(result['results'][1]['suppliers'],['Fornecedor B'])
        with compras.db() as c:
            records=[tuple(row) for row in c.execute('SELECT supplier,source FROM quotes WHERE process_id=? AND source IN (?,?) ORDER BY source',(self.pid,'a.xlsx','b.xlsx'))]
        self.assertEqual(records,[('Fornecedor A','a.xlsx'),('Fornecedor B','b.xlsx')])

    def test_supplier_validation_happens_before_any_write(self):
        response=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['Fornecedor A',' ']},files=[('files',('a.xlsx',quotes_file())),('files',('b.xlsx',quotes_file()))])
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.count('quotes'),1)

    def test_one_file_rolls_back_without_blocking_next(self):
        with compras.db() as c:
            c.execute("CREATE TRIGGER reject_import_name BEFORE INSERT ON needs WHEN NEW.name='REJECT' BEGIN SELECT RAISE(ABORT,'rejected'); END")
        try:
            bad=workbook_bytes([['Código','Produto','Fornecedor','Quantidade','Unidade','Custo'],['A','Will roll back','',1,'G',1],['B','REJECT','',1,'G',1]])
            response=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('atomic.xlsx',bad)),('files',('valid.xlsx',needs_file()))])
            self.assertEqual(response.json()['imported'],1)
            self.assertEqual(response.json()['failed'],1)
            self.assertEqual(self.count('needs'),2)
            with compras.db() as c:
                self.assertFalse(c.execute('SELECT 1 FROM needs WHERE process_id=? AND name=?',(self.pid,'Will roll back')).fetchone())
        finally:
            with compras.db() as c:c.execute('DROP TRIGGER reject_import_name')

    def test_retry_keys_do_not_duplicate_and_cannot_change_payload(self):
        key=str(uuid.uuid4());raw=needs_file()
        def submit(payload):return self.client.post(f'/api/import/needs/{self.pid}',data={'keys':[key]},files=[('files',('retry.xlsx',payload))])
        self.assertEqual(submit(raw).json()['imported'],1)
        again=submit(raw).json()
        self.assertEqual(again['imported'],0)
        self.assertTrue(again['results'][0]['already_imported'])
        self.assertEqual(again['results'][0]['previously_imported'],1)
        self.assertEqual(self.count('needs'),2)
        changed=submit(needs_file('Changed')).json()
        self.assertEqual(changed['failed'],1)
        self.assertEqual(self.count('needs'),2)

    def test_limits_and_unsupported_types(self):
        files=[('files',(f'{i}.xlsx',b'bad')) for i in range(31)]
        self.assertEqual(self.client.post(f'/api/import/needs/{self.pid}',files=files).status_code,400)
        with patch.object(compras,'MAX_IMPORT_BYTES',4):
            result=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('big.xlsx',b'12345'))]).json()
            self.assertEqual(result['failed'],1)
        result=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('wrong.txt',b'not spreadsheet')),('files',('empty.xlsx',b''))]).json()
        self.assertEqual(result['failed'],2)
        self.assertEqual(self.count('needs'),1)

    def test_empty_spreadsheet_is_not_reported_as_success(self):
        raw=workbook_bytes([['Unknown layout'],['Value']])
        result=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('empty.xlsx',raw))]).json()
        self.assertEqual((result['successful'],result['empty'],result['imported']),(0,1,0))

    def test_batch_total_limit_and_receipt_audit(self):
        first=needs_file('First');second=needs_file('Second')
        with patch.object(compras,'MAX_BATCH_BYTES',len(first)):
            result=self.client.post(f'/api/import/needs/{self.pid}',files=[('files',('first.xlsx',first)),('files',('second.xlsx',second))]).json()
        self.assertEqual(result['imported'],1)
        self.assertEqual(result['failed'],1)
        events=self.client.get(f'/api/audit/{self.pid}').json()
        self.assertEqual(events[0]['action'],'IMPORTAR_NECESSIDADES')
