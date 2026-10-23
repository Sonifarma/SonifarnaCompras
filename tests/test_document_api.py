import unittest
import test_workflow as workflow
import test_documents as documents
compras=workflow.compras


class DocumentAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):workflow.PurchaseWorkflow.setUpClass.__func__(cls)
    def setUp(self):workflow.PurchaseWorkflow.setUp(self)

    def test_xls_upload_preserves_numeric_price_and_date(self):
        response=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['Synthetic vendor']},files=[('files',('quote.xls',documents.legacy_xls()))])
        self.assertEqual(response.json()['imported'],1)
        with compras.db() as c:
            q=c.execute('SELECT * FROM quotes WHERE process_id=? AND source=?',(self.pid,'quote.xls')).fetchone()
            self.assertEqual(q['unit_cost'],7)
            self.assertEqual(q['base_qty'],5)
            self.assertEqual(q['expiry'],'2028-07-25')

    def test_identical_files_same_supplier_skipped_in_one_batch(self):
        raw=documents.legacy_xls()
        result=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['Vendor','vendor']},files=[('files',('quote.xls',raw)),('files',('copy.xls',raw))]).json()
        self.assertEqual(result['imported'],1)
        self.assertEqual(result['duplicates'],1)
        self.assertEqual(result['results'][1]['status'],'duplicate')

    def test_identical_content_different_suppliers_is_not_skipped(self):
        raw=documents.legacy_xls()
        result=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['Vendor A','Vendor B']},files=[('files',('a.xls',raw)),('files',('b.xls',raw))]).json()
        self.assertEqual(result['imported'],2)
        self.assertEqual(result['duplicates'],0)

    def test_image_requires_manual_review_before_auto_selection(self):
        result=self.client.post(f'/api/import/quotes/{self.pid}',data={'suppliers':['OCR vendor']},files=[('files',('quote.jpg',documents.nutri_image()))]).json()
        self.assertEqual(result['imported'],2)
        with compras.db() as c:
            q=dict(c.execute("SELECT * FROM quotes WHERE process_id=? AND base_unit='KG' AND source='quote.jpg'",(self.pid,)).fetchone())
        compras.add_need(self.pid,['IMG',q['product'],'',5000,'G',.01])
        with compras.db() as c:
            need=c.execute('SELECT MAX(id) FROM needs WHERE process_id=?',(self.pid,)).fetchone()[0]
            c.execute('UPDATE needs SET last_pack_qty=5,last_pack_unit=? WHERE id=?',('KG',need))
        data=self.client.get(f'/api/data/{self.pid}').json()
        self.assertIsNone(next(n for n in data['needs'] if n['id']==need)['choice'])
        payload={'quantity':5,'package_unit':'KG','price':7,'expiry':'2029-01-01','product':q['product']}
        self.assertEqual(self.client.post(f"/api/quotes/{q['id']}/details",data=payload).status_code,409)
        self.client.post(f"/api/quotes/{q['id']}/details",data={**payload,'reviewed':True}).raise_for_status()
        data=self.client.get(f'/api/data/{self.pid}').json()
        self.assertEqual(next(n for n in data['needs'] if n['id']==need)['choice']['quote_id'],q['id'])
