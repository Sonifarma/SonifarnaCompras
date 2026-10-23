import io
import unittest
import fitz
from PIL import Image,ImageDraw,ImageFont
from document_import import (extract_document,number,package,pn_row,pharma_row,shared_row,
                             spreadsheet_rows,spreadsheet_quote_rows,nutri_lines,ocr_i9_lines)
from procurement import evaluate,unit


def table_pdf(headers,rows,cuts,continuation=None):
    document=fitz.open()
    for index,data in enumerate([rows]+([continuation] if continuation else [])):
        page=document.new_page(width=842,height=595)
        content=([headers] if index==0 else [])+data
        y=100;step=35
        for j in range(len(content)+1):page.draw_line((cuts[0],y+j*step),(cuts[-1],y+j*step))
        for x in cuts:page.draw_line((x,y),(x,y+len(content)*step))
        for i,row in enumerate(content):
            for j,value in enumerate(row):
                page.insert_textbox(fitz.Rect(cuts[j]+2,y+i*step+3,cuts[j+1]-2,y+(i+1)*step-2),str(value),fontsize=7)
    raw=document.tobytes();document.close();return raw


def nutri_image():
    image=Image.new('RGB',(1680,500),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=20);small=ImageFont.load_default(size=16)
    draw.text((20,20),'Nutrifarm - Cotacao de Venda',font=font,fill='black')
    positions=[20,470,630,800,940,1110,1300,1480]
    for x,label in zip(positions,['Produto','Fabricacao','Validade','Procedencia','Embalagem','Qtde. Cotada','Preco kg/l','Valor Item']):draw.text((x,90),label,font=small,fill='black')
    values=[['AMIDO','01/01/2026','01/01/2029','Brasil','5,00 kg','5,00 kg','7,00','35,00'],['CAPS OMEGA','01/05/2026','01/05/2028','Brasil','1.000 Cap','1.000 Cap','280,00','280,00']]
    for i,row in enumerate(values):
        for x,value in zip(positions,row):draw.text((x,140+i*65),value,font=font,fill='black')
    data=io.BytesIO();image.save(data,format='JPEG',quality=95);return data.getvalue()


def legacy_xls():
    import base64,zlib
    return zlib.decompress(base64.b64decode('eJztWE9IFFEY/71x110Xd901FTSQRcjKBIkuXXS0LIlY08DKCGp0h1jUnVjWQx3Ksj0GQaeii2CHLlaX/tAf6tYhMOoQBIJbhw6dgoIO6vR9386YWoJ70DDmN7xvvj/vfe+b97335s28nY7NTjyoy2MF2lCCBbsMpUt0ikqZK0RBdttm1r0HqdgeNhXKgpTIUj+eht8EOIec7zw03Pe9Igp8onIK59Btpc34BmKfxGAojqGVqMJt0kRQK1FVCh0UukXoPan5TGi7aK4JbaW6s+okpvXupr3OLD6hNYgtAvb7SNp8FM1uVOM1z+JL11Whrh8dmZQxvMkM9b5yTIIS2mWmzQzLFbiDENDZ2ZJItPQTZlFFyZ7EDzsOfHdX9cu4p99YvQLpfy7XB1bRBymJK/U3NB8wBvuMLJIcKqD72BLAfitrDBrWHPp4JrilJ2MlR7NWGOjNJuPmyIAxbJw1R8jSl04ljaQZ4TrmFys+mk5l85mURdv6MWNYbH6gI3Go8witlcNdNJ1Q2D6iy7aPsCyrcqJJiob5mCyuKMU/d/fbu8RAj35aNGPyyii8WLbxc8DGZW5BjSNi0YRSt2gSfpfQK+J1q/B1QquoDt0be6od5uC41Lkq1kbqZ4/gvb59Cb+D+NzX3sf1uc/6TuKnuvIXqqY+6BNooBddktrzNY5m1axu3WQ80d27cjahGaG1f2xIQS3qxG4XUqUqMM9LkBATWpB4dNSipDljVZBKSCpZlHwk+RzP6i+elXjmsbqohSTyGGqc1ko8c3aeU9xKPNeDN9IXMxp5bdMq8VAGux2/EYIHDx48ePDgwYOH/wx8aORzHx8z+XDJx0c+JvJpnv/rzFNZ+Nc/KTysG47CoitLH5UHkKZ7BueLmj818CvXl1pjG/d/IeM49Z7BEAYkjqGi+mbQR5ha+jxrbhgtuqvVUHT/C8XEuc79/wLroOX0'))


class DocumentReaders(unittest.TestCase):
    def test_explicit_locales_do_not_confuse_thousands(self):
        self.assertEqual(number('3,950.00','en'),3950)
        self.assertEqual(number('3.950,00'),3950)
        self.assertEqual(number('247,631'),247.631)
        self.assertEqual(number('R$440.000,\n00'),440000)
        self.assertEqual(number('5.000','en'),5)
        self.assertEqual(package('1.000 Cap'),(1000,'CAPSULAS'))

    def test_shared_pdf_continuation_page_keeps_all_rows(self):
        headers=['Descricao','Origem','Validade','Qtde','Unid. Medida','Valor KG','Valor Unit.','Total do Item','% IPI','% ST','Total com Impostos']
        row=['AMIDO','Brasil','25/07/2028','1,00','5 KG','R$7,00','R$35,00','R$35,00','0,00','0,00','R$35,00']
        next_row=['AMIDO','Brasil','25/07/2028','1,00','25 KG','R$5,50','R$137,50','R$137,50','0,00','0,00','R$137,50']
        raw=table_pdf(headers,[row],[20,200,264,332,382,432,503,581,645,694,737,822],[next_row])
        result=extract_document(raw,'supplier.pdf')
        self.assertEqual(len(result.rows),2)
        self.assertEqual([q['base_qty'] for q in result.rows],[5,25])
        self.assertAlmostEqual(result.rows[1]['unit_cost'],5.5)
        self.assertEqual(result.rows[0]['expiry'],'2028-07-25')

    def test_pn_pack_is_not_total_quoted_quantity(self):
        value=pn_row(['Caps.00 Br/Br','BRASIL','30,000','MIL','5,000','08/2031','29,00','','870,00'])
        self.assertEqual(value['base_qty'],5)
        self.assertEqual(value['base_unit'],'MILHEIRO')
        self.assertEqual(value['unit_cost'],29)
        self.assertEqual(value['total'],145)
        self.assertEqual(value['expiry'],'2031-08-01')

    def test_pharma_description_pack_and_missing_expiry(self):
        value=pharma_row(['02','PRODUTO ATIVO 50 G','1,00','UN','234,598','6,50','','234,600'])
        self.assertEqual(value['base_qty'],50)
        self.assertAlmostEqual(value['unit_cost'],234.598/50)
        self.assertEqual(value['expiry'],'')
        self.assertIn('IPI',value['import_warning'])
        liquid=pharma_row(['04','OLEO 500 ML','1,00','UN','97,749','0,00','01/04/2027','97,750'])
        self.assertEqual(liquid['base_unit'],'ML')
        self.assertEqual(unit('ML','OLEO'),(None,None))

    def test_wrapped_currency_and_tax_warning(self):
        value=shared_row(['ATIVO','Brasil','01/07/2028','1,00','5 G','R$440.000,\n00','R$2.200,00','R$2.200,0\n0','0,00','0,00','R$2.200,00'])
        self.assertEqual(value['unit_cost'],440)
        taxed=shared_row(['ATIVO','Brasil','01/07/2028','1,00','1 KG','R$100,00','R$100,00','R$100,00','8,00','0,00','R$108,00'])
        self.assertIn('IPI',taxed['import_warning'])

    def test_nutrifarm_capsules_and_liquids(self):
        values=nutri_lines(['CAPS OLEO OMEGA 01/05/2026 01/05/2028 Brasil 1.000 Cap 1.000 Cap 280,00 280,00','OLEO 01/05/2026 01/05/2028 Brasil 1,00 L 1,00 L 95,00 95,00'])
        self.assertEqual(len(values),2)
        self.assertEqual(values[0]['base_qty'],1000)
        self.assertEqual(values[0]['unit_cost'],.28)
        self.assertEqual(unit(values[0]['base_unit'],values[0]['product']),('milheiro',.001))
        self.assertEqual(values[1]['base_unit'],'L')

    def test_jpg_ocr_is_read_and_never_auto_approved(self):
        result=extract_document(nutri_image(),'quote.jpg')
        self.assertEqual(len(result.rows),2)
        self.assertIn('OCR local',result.methods)
        self.assertTrue(all('OCR' in q['import_warning'] for q in result.rows))
        value=next(q for q in result.rows if q['base_unit']=='KG')
        need={'name':value['product'],'qty':5000,'unit':'G','last_pack_qty':5,'last_pack_unit':'KG'}
        self.assertFalse(evaluate(need,value,'2026-10-23')['eligible'])

    def test_scanned_pdf_uses_ocr(self):
        document=fitz.open();page=document.new_page(width=840,height=250)
        page.insert_image(page.rect,stream=nutri_image())
        raw=document.tobytes();document.close()
        result=extract_document(raw,'scan.pdf')
        self.assertEqual(len(result.rows),2)
        self.assertIn('OCR local',result.methods)

    def test_corrupt_and_unknown_images_do_not_invent_items(self):
        with self.assertRaises(ValueError):extract_document(b'broken','quote.jpg')
        image=Image.new('RGB',(500,200),'white');output=io.BytesIO();image.save(output,format='PNG')
        result=extract_document(output.getvalue(),'unknown.png')
        self.assertEqual(result.rows,[])
        self.assertTrue(result.warnings)

    def test_legacy_xls_numeric_cells_and_dates(self):
        import base64,zlib
        raw=legacy_xls()
        sheets=spreadsheet_rows(raw,'quote.xls')
        result=spreadsheet_quote_rows(sheets)
        self.assertEqual(len(result.rows),1)
        self.assertEqual(result.rows[0]['base_qty'],5)
        self.assertEqual(result.rows[0]['unit_cost'],7)
        self.assertEqual(result.rows[0]['expiry'],'2028-07-25')

    def test_i9_english_decimals_and_capsule_unit(self):
        document=fitz.open();page=document.new_page(width=612,height=792)
        page.insert_text((20,30),'Un. Embalagem Valor de Venda Quantidade Preco Total Validade Status',fontsize=8)
        for y,code,name,base,size,price,qty,total,expiry in [(100,'CODE1','CAP GEL 0','Mh','5.000','20.00','5.00','100.00','12/04/2031'),(140,'CODE2','ATIVO TESTE','Kg','1.000','3,950.00','1.00','3,950.00','09/12/2028')]:
            for x,value in [(50,code),(110,name),(304,base),(338,size),(368,price),(427,qty),(452,total),(489,expiry),(537,'Ativo')]:page.insert_text((x,y),value,fontsize=6)
        raw=document.tobytes();document.close()
        result=extract_document(raw,'vendor.pdf')
        self.assertEqual(len(result.rows),2)
        self.assertEqual(result.rows[0]['base_qty'],5)
        self.assertEqual(result.rows[0]['base_unit'],'MILHEIRO')
        self.assertEqual(result.rows[1]['unit_cost'],3950)
        self.assertEqual(result.rows[1]['expiry'],'2028-12-09')

    def test_galena_reference_quantity_remains_pending(self):
        document=fitz.open();page=document.new_page(width=595,height=842)
        page.insert_text((20,30),'GALENA Valor Unit. Valor Item',fontsize=8)
        for x,value in [(40,'01'),(60,'ATIVO TESTE'),(295,'566,99'),(328,'KG'),(357,'2,0000'),(393,'1.133,98'),(426,'09/01/2029'),(470,'BRASIL')]:page.insert_text((x,100),value,fontsize=6)
        raw=document.tobytes();document.close()
        result=extract_document(raw,'vendor.pdf')
        self.assertEqual(len(result.rows),1)
        self.assertEqual(result.rows[0]['unit_cost'],566.99)
        self.assertEqual(result.rows[0]['expiry'],'2029-01-09')
        self.assertIn('confirme a embalagem',result.rows[0]['import_warning'])

    def test_unknown_pdf_does_not_turn_addresses_into_products(self):
        document=fitz.open();page=document.new_page()
        page.insert_text((30,30),'Texto normal sem tabela de itens, quantidades ou valores reconheciveis.',fontsize=10)
        raw=document.tobytes();document.close()
        result=extract_document(raw,'unknown.pdf')
        self.assertEqual(result.rows,[])
        self.assertTrue(result.warnings)

    def test_ocr_i9_merged_code_and_total_date(self):
        result=ocr_i9_lines(['CODE1234ICAPGEL 0 BRANCO Mh 5.000 20.00 5.00 100.0012/04/2031 Ativo'])
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]['product'].startswith('CAPGEL'))
        self.assertEqual(result[0]['unit_cost'],20)
        self.assertEqual(result[0]['expiry'],'2031-04-12')
