from datetime import date
import unittest
from procurement import evaluate, commercial


class BuyingRules(unittest.TestCase):
    def setUp(self):
        self.need = dict(name='Amido', qty=5000, unit='G', last_pack_qty=5, last_pack_unit='KG')
        self.quote = dict(product='Amido', base_qty=5, base_unit='KG', unit_cost=10, expiry='2028-10-24')
        self.delivery = '2026-10-23'

    def assess(self):
        return evaluate(self.need,self.quote,self.delivery)

    def test_kg_converts_to_grams(self):
        a=self.assess()
        self.assertTrue(a['eligible'])
        self.assertEqual(a['unit'],'g')
        self.assertEqual(a['unit_price'],.01)
        self.assertEqual(a['purchase_total'],50)

    def test_cheapest_25kg_requires_approval(self):
        self.quote.update(base_qty=25,unit_cost=8)
        a=self.assess()
        self.assertFalse(a['eligible'])
        self.assertEqual(a['package_ratio'],5)
        self.assertEqual(a['purchase_total'],200)
        self.assertEqual(a['surplus_qty'],20000)

    def test_capsules_to_milheiros(self):
        self.need.update(name='Cápsulas 0',qty=2000,unit='UN',last_pack_qty=1,last_pack_unit='MILHEIRO')
        self.quote.update(product='Cápsulas 0',base_qty=1000,base_unit='UN',unit_cost=.04)
        a=self.assess()
        self.assertTrue(a['eligible'])
        self.assertEqual(a['unit'],'milheiro')
        self.assertEqual(a['quantity'],2)
        self.assertEqual(a['unit_price'],40)
        self.assertEqual(a['packages'],2)
        self.assertEqual(a['purchase_total'],80)

    def test_expiry_strictly_more_than_year(self):
        for expiry in ['', '2027-10-22', '2027-10-23']:
            self.quote['expiry']=expiry
            self.assertFalse(self.assess()['eligible'])
        self.quote['expiry']='24/10/2027'
        self.assertTrue(self.assess()['eligible'])
        self.assertFalse(evaluate(self.need,self.quote,'2027-01-01')['eligible'])

    def test_leap_year_boundary(self):
        self.quote['expiry']='2025-02-28'
        self.assertFalse(evaluate(self.need,self.quote,'2024-02-29')['eligible'])
        self.quote['expiry']='2025-03-01'
        self.assertTrue(evaluate(self.need,self.quote,'2024-02-29')['eligible'])

    def test_unknown_history_is_not_current_need(self):
        self.need['last_pack_qty']=None
        self.assertFalse(self.assess()['eligible'])
        self.assertIsNone(self.assess()['last_package_qty'])

    def test_round_up_full_packages(self):
        self.need['qty']=6000
        a=self.assess()
        self.assertEqual(a['packages'],2)
        self.assertEqual(a['purchase_total'],100)
        self.assertEqual(a['surplus_qty'],4000)

    def test_unsupported_units_do_not_compare(self):
        self.quote['base_unit']='L'
        self.assertIsNone(self.assess()['purchase_total'])
        self.assertFalse(self.assess()['eligible'])

    def test_commercial_minimum_and_unknown_freight(self):
        c=commercial(580,dict(confirmed=False))
        self.assertEqual(c['missing_minimum'],120)
        self.assertFalse(c['ready'])
        self.assertIsNone(c['landed_total'])
        c=commercial(1850,dict(confirmed=True,freight=60))
        self.assertEqual(c['missing_free_shipping'],150)
        self.assertEqual(c['landed_total'],1910)
        c=commercial(2000,dict(confirmed=True,freight=None))
        self.assertEqual(c['landed_total'],2000)
        self.assertTrue(c['ready'])
        self.assertFalse(commercial(2000,dict(confirmed=True),1)['ready'])
