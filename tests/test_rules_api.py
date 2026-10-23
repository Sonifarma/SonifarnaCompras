import io
import unittest
from openpyxl import load_workbook
import test_workflow as workflow
compras=workflow.compras


class RulesAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow.PurchaseWorkflow.setUpClass.__func__(cls)

    def setUp(self):
        workflow.PurchaseWorkflow.setUp(self)
        with compras.db() as c:c.execute('DELETE FROM supplier_terms')

    def test_large_package_not_auto_selected_and_requires_justification(self):
        with compras.db() as c:
            c.execute('UPDATE needs SET qty=5000,last_pack_qty=5,last_pack_unit=? WHERE id=?',('KG',self.need))
            c.execute('UPDATE quotes SET base_qty=25,base_unit=?,unit_cost=8 WHERE id=?',('KG',self.quote))
        result=self.client.get(f'/api/data/{self.pid}').json()
        self.assertEqual(result['summary']['selected'],0)
        self.assertEqual(result['needs'][0]['lowest_unit']['id'],self.quote)
        self.assertIsNone(result['needs'][0]['recommended'])
        payload={'need_id':self.need,'quote_id':self.quote}
        self.assertEqual(self.client.post('/api/choose',data=payload).status_code,409)
        self.assertEqual(self.client.post('/api/choose',data={**payload,'override':True,'reason':'ok'}).status_code,409)
        self.client.post('/api/choose',data={**payload,'override':True,'reason':'Exceção autorizada para análise de estoque'}).raise_for_status()
        result=self.client.get(f'/api/data/{self.pid}').json()
        self.assertEqual(result['summary']['review'],1)
        self.assertEqual(result['summary']['selected_total'],200)
        self.assertIn('EXCEÇÃO APROVADA',result['needs'][0]['choice']['reason'])

    def test_missing_expiry_stays_pending(self):
        with compras.db() as c:c.execute('UPDATE quotes SET expiry=? WHERE id=?',('',self.quote))
        self.assertEqual(self.client.get(f'/api/data/{self.pid}').json()['summary']['selected'],0)
        self.client.post(f'/api/quotes/{self.quote}/details',data={'quantity':10,'package_unit':'G','price':2,'expiry':'2099-01-01'}).raise_for_status()
        self.assertEqual(self.client.get(f'/api/data/{self.pid}').json()['summary']['selected'],1)

    def test_manual_choice_preserved_when_delivery_changes(self):
        self.client.get(f'/api/data/{self.pid}').raise_for_status()
        self.client.post(f'/api/processes/{self.pid}/delivery',data={'delivery':'2099-01-01'}).raise_for_status()
        result=self.client.get(f'/api/data/{self.pid}').json()
        self.assertEqual(result['summary']['selected'],1)
        self.assertEqual(result['summary']['review'],1)

    def test_supplier_defaults_confirmed_terms_and_exports(self):
        self.client.get(f'/api/data/{self.pid}').raise_for_status()
        rows=self.client.get(f'/api/suppliers/{self.pid}').json()
        self.assertEqual(rows[0]['minimum_order'],700)
        self.assertFalse(rows[0]['confirmed'])
        self.client.post('/api/suppliers/conditions',data={'supplier':'Fornecedor teste','minimum_order':10,'free_shipping_from':100,'freight':15,'confirmed':True}).raise_for_status()
        basket=self.client.get(f'/api/drafts/{self.pid}').json()['suppliers'][0]['commercial']
        self.assertEqual(basket['landed_total'],35)
        self.assertTrue(basket['ready'])
        raw=self.client.get(f'/api/drafts/{self.pid}/xlsx').content
        workbook=load_workbook(io.BytesIO(raw))
        self.assertIn('CONDIÇÕES COMERCIAIS',[row[0].value for row in workbook.active])
        self.assertTrue(self.client.get(f'/api/export/{self.pid}').content.startswith(b'%PDF'))

    def test_history_edit_is_validated_and_audited(self):
        self.assertEqual(self.client.post(f'/api/needs/{self.need}/package',data={'quantity':-1,'package_unit':'G'}).status_code,422)
        self.assertEqual(self.client.post(f'/api/needs/{self.need}/package',data={'quantity':1,'package_unit':'L'}).status_code,400)
        self.client.post(f'/api/needs/{self.need}/package',data={'quantity':1,'package_unit':'KG'}).raise_for_status()
        audit=self.client.get(f'/api/audit/{self.pid}').json()
        self.assertEqual(audit[0]['action'],'EMBALAGEM_ANTERIOR')

    def test_basket_transfer_never_adds_stock_or_breaks_source_minimum(self):
        # Existing source basket 800 (200 transferable + 600 retained), target 1850.
        with compras.db() as c:
            c.execute('UPDATE quotes SET unit_cost=20 WHERE id=?',(self.quote,))
        compras.add_need(self.pid,['T2','Produto mantido','',10,'G',70])
        compras.add_need(self.pid,['T3','Produto destino','',10,'G',200])
        compras.add_quote(self.pid,'Fornecedor teste','Produto mantido','10 G',10,'G',600,60,'2099-01-01','teste')
        compras.add_quote(self.pid,'Destino','Produto destino','10 G',10,'G',1850,185,'2099-01-01','teste')
        compras.add_quote(self.pid,'Destino','Produto teste','10 G',10,'G',200,20,'2099-01-01','teste')
        with compras.db() as c:
            c.execute('UPDATE needs SET last_pack_qty=10,last_pack_unit=? WHERE process_id=?',('G',self.pid))
            quote=c.execute('SELECT id FROM quotes WHERE process_id=? AND supplier=? AND product=?',(self.pid,'Destino','Produto teste')).fetchone()[0]
            c.execute('INSERT INTO matches VALUES (?,?,1)',(self.need,quote))
        # Manually pin current allocation before evaluating transfer.
        self.client.post('/api/choose',data={'need_id':self.need,'quote_id':self.quote}).raise_for_status()
        self.client.get(f'/api/data/{self.pid}').raise_for_status()
        for supplier in ['Fornecedor teste','Destino']:
            self.client.post('/api/suppliers/conditions',data={'supplier':supplier,'minimum_order':500,'free_shipping_from':2000,'freight':50,'confirmed':True}).raise_for_status()
        result=self.client.get(f'/api/drafts/{self.pid}').json()
        suggestion=next(x for x in result['suggestions'] if x['need_id']==self.need)
        self.assertEqual(suggestion['target_subtotal'],2050)
        self.assertEqual(suggestion['source_subtotal'],600)
        self.assertEqual(suggestion['landed_delta'],-50)
        self.assertTrue(suggestion['reaches_free_shipping'])
        self.assertEqual(next(n for n in self.client.get(f'/api/data/{self.pid}').json()['needs'] if n['id']==self.need)['choice']['quote_id'],self.quote)
        self.client.post('/api/suppliers/conditions',data={'supplier':'Fornecedor teste','minimum_order':700,'free_shipping_from':2000,'freight':50,'confirmed':True}).raise_for_status()
        self.assertFalse(any(x['need_id']==self.need for x in self.client.get(f'/api/drafts/{self.pid}').json()['suggestions']))
