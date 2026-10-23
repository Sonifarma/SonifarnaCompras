"""Supplier quote tables, images and scanned PDFs. No remote document service."""
from dataclasses import dataclass, field
from functools import lru_cache
import io
import math
import re
from threading import Lock
import fitz
from procurement import normalize, parse_date, is_capsule


@dataclass
class DocumentResult:
    rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    methods: set = field(default_factory=set)


def number(value, locale='pt'):
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text=re.sub(r'\s+|R\$', '', str(value or ''))
    if not re.fullmatch(r'-?[\d.,]+',text):return None
    text=text.replace(',','') if locale=='en' else text.replace('.','').replace(',','.')
    try:
        value=float(text)
        return value if math.isfinite(value) else None
    except ValueError:return None


def text(value):return ' '.join(str(value or '').split())


def base_unit(value):
    value=normalize(value)
    return {'MI':'MILHEIRO','MH':'MILHEIRO','MIL':'MILHEIRO','MILH':'MILHEIRO','MILHEIROS':'MILHEIRO',
            'GR':'G','GRAMAS':'G','GRAMA':'G','CAP':'CAPSULAS','CAPS':'CAPSULAS','CAPSULA':'CAPSULAS','CAPSULAS':'CAPSULAS','UND':'UN','UNID':'UN'}.get(value,value)


AMOUNT=r'\d+(?:[.,]\d+)*'
PACK=re.compile(r'('+AMOUNT+r')\s*(MILHEIROS?|MILH|MIL|MI|MH|KG|MG|GR|G|ML|L|CAPS?|UN(?:ID)?)(?![A-Z])',re.I)


def package(value,locale='pt',suffix=False):
    cleaned=text(value)
    matches=list(PACK.finditer(cleaned))
    match=matches[-1] if suffix and matches else (matches[0] if len(matches)==1 else None)
    if not match:return None,None
    if suffix and cleaned[match.end():].strip(' .'):return None,None
    quantity=number(match[1],locale)
    return (quantity,base_unit(match[2])) if quantity is not None and quantity>0 else (None,None)


def quote(product,quantity,base,price,expiry='',warnings=None):
    if not product or price is None or not math.isfinite(price) or price<0:return None
    warnings=list(warnings or [])
    if quantity is None or quantity<=0 or not base:
        quantity=None;base=base or '';warnings.append('Embalagem não identificada com segurança')
    expiry_date=parse_date(expiry)
    if expiry and expiry_date is None:warnings.append('Validade não reconhecida: '+text(expiry))
    return dict(product=text(product),pack=f'{quantity:g} {base}' if quantity else '',base_qty=quantity,
                base_unit=base or '',unit_cost=price,total=round(price*quantity,4) if quantity else None,
                expiry=expiry_date.isoformat() if expiry_date else '',import_warning='; '.join(dict.fromkeys(warnings)))


def shared_row(row):
    if len(row)!=11:return None
    product=text(row[0]);quantity,base=package(row[4]);pack_price=number(row[6]);count=number(row[3])
    if not quantity or pack_price is None or not product or count is None or count<=0:return None
    warnings=[]
    line_total=number(row[7]);tax_total=number(row[10])
    if line_total is not None and abs(line_total-count*pack_price)>max(.03,abs(line_total)*.005):warnings.append('Total da linha diverge da quantidade e do preço da embalagem')
    if (number(row[8]) or 0)>0 or (number(row[9]) or 0)>0 or (tax_total is not None and line_total is not None and tax_total>line_total+.02):
        warnings.append('Preço extraído antes de IPI/ST; confira os impostos')
    return quote(product,quantity,base,pack_price/quantity,row[2],warnings)


def pn_row(row):
    if len(row)!=9:return None
    quantity=number(row[4]);price=number(row[6]);count=number(row[2]);base=base_unit(row[3])
    if not quantity or price is None or count is None or not text(row[0]):return None
    warnings=[];total=number(row[8])
    if total is not None and abs(count*price-total)>max(.03,abs(total)*.005):warnings.append('Preço e total cotados precisam de conferência')
    if (number(row[7]) or 0)>0:warnings.append('Confira IPI/ST da cotação')
    return quote(row[0],quantity,base,price,row[5],warnings)


def pharma_row(row):
    if len(row)!=8 or not re.fullmatch(r'\d{1,4}',text(row[0])):return None
    product=text(row[1]);quantity,base=package(product,suffix=True)
    price=number(row[4]);count=number(row[2])
    if price is None or count is None or count<=0:return None
    warnings=[]
    total=number(row[7])
    if total is not None and abs(count*price-total)>max(.03,abs(total)*.005):warnings.append('Total da linha diverge do preço e da quantidade')
    if (number(row[5]) or 0)>0:warnings.append('Preço extraído antes de IPI; confira os impostos')
    if quantity is None:return quote(product,None,'',price,row[6],warnings)
    return quote(product,quantity,base,price/quantity,row[6],warnings)


def active_row(row):
    if len(row)!=17 or not re.fullmatch(r'[0-9]+-[0-9]+',re.sub(r'\s+','',str(row[1] or ''))):return None
    product=text(row[4]);size=number(row[7]);pack_price=number(row[8]);rate=number(row[9])
    if not product or not size or size<=0 or pack_price is None or rate is None:return None
    base=base_unit(row[14]);warnings=[]
    # This template explicitly prices capsules per mlh, although UMB says Unid.
    if is_capsule(product):
        base='MILHEIRO'
        warnings.append('Cápsulas: fracionamento interpretado em milheiros pelo cabeçalho g/mlh, embora UMB indique unidades; confirme com o fornecedor')
    elif base not in {'G','KG','MG','ML','L'}:
        base='';warnings.append('Unidade do fracionamento não reconhecida')
    if abs(size*rate-pack_price)>max(.03,size*.0005+.005):
        warnings.append('Preço da embalagem diverge do preço g/mlh; confira os valores')
    if text(row[5]):warnings.append('Informações adicionais: '+text(row[5]))
    return quote(product,size,base,pack_price/size,row[11],warnings)


def embrafarma_row(row):
    if len(row)!=12 or not re.fullmatch(r'\d{1,4}',text(row[0])):return None
    product=text(row[1]);count=number(row[2]);base=base_unit(row[3]);price=number(row[4])
    if not product or count is None or count<=0 or price is None:return None
    size,pack_base=package(product,suffix=True);warnings=[]
    factors={'G':('mass',1),'KG':('mass',1000),'MG':('mass',.001),
             'L':('volume',1000),'ML':('volume',1),'MILHEIRO':('count',1000),'CAPSULAS':('count',1),'UN':('count',1)}
    if size is None:
        size=count;warnings.append('Quantidade cotada usada como referência de embalagem; confirme a embalagem mínima')
    elif pack_base!=base:
        source=factors.get(pack_base);target=factors.get(base)
        if source and target and source[0]==target[0]:size=size*source[1]/target[1]
        else:size=None;warnings.append('Unidade da embalagem diverge da unidade do preço; confirme com o fornecedor')
    total=number(row[7])
    # The unit price has two decimal places; tolerate only its rounding error.
    if total is not None and abs(count*price-total)>max(.02,count*.005+.01):
        warnings.append('Total da linha diverge da quantidade e do preço unitário; confira o valor comercial')
    if (number(row[5]) or 0)>0 or (number(str(row[6] or '').replace('%','')) or 0)>0:
        warnings.append('Confira ST/IPI e a base dos valores antes de aprovar')
    return quote(product,size,base,price,row[8],warnings)


def native_tables(page,result,default_parser=None):
    found=0
    for table in page.find_tables().tables:
        parser=default_parser
        for row in table.extract():
            labels=[normalize(cell) for cell in row]
            if len(row)==11 and labels[0]=='DESCRICAO' and 'VALOR UNIT' in labels[6]:parser=shared_row;continue
            if len(row)==9 and labels[0]=='PRODUTO' and labels[4]=='EMBALAGEM':parser=pn_row;continue
            if len(row)==8 and labels[0]=='ITENS' and 'DESCRICAO' in labels[1]:parser=pharma_row;continue
            if len(row)==17 and labels[4]=='INSUMO' and labels[9]=='PRECO G MLH':parser=active_row;continue
            if len(row)==12 and labels[:4]==['ITEM','PRODUTO','QTDE','UN'] and labels[4]=='VALOR UNITARIO':parser=embrafarma_row;continue
            if parser:
                record=parser(row)
                if record:result.rows.append(record);found+=1
    if found:result.methods.add('tabela PDF')
    return found


def shared_page(page,result,cuts):
    words=page.get_text('words')
    spans={}
    for table in page.find_tables().tables:
        for row in table.rows:
            y0,y1=row.bbox[1],row.bbox[3]
            key=round(y1,2)
            spans[key]=(min(y0,spans[key][0]) if key in spans else y0,y1)
    found=0
    for y0,y1 in sorted(spans.values()):
        values=[[] for _ in range(11)]
        for word in words:
            x=(word[0]+word[2])/2;y=(word[1]+word[3])/2
            if not y0<=y<y1:continue
            index=next((j for j in range(11) if cuts[j]<=x<cuts[j+1]),None)
            if index is not None:values[index].append(word)
        row=[' '.join(w[4] for w in sorted(cell,key=lambda w:(round(w[1]/3)*3,w[0]))) for cell in values]
        record=shared_row(row)
        if record:result.rows.append(record);found+=1
    if found:result.methods.add('tabela PDF')
    return found


def word_rows(words,anchors):
    anchors=sorted(anchors)
    for i,y in enumerate(anchors):
        lo=(anchors[i-1]+y)/2 if i else y-8
        hi=(y+anchors[i+1])/2 if i+1<len(anchors) else y+8
        yield [w for w in words if lo<=w[1]<hi]


def cell(words,lo,hi):
    # Sort by baseline then x so wrapped names remain in reading order.
    selected=[w for w in words if lo<=w[0]<hi]
    selected.sort(key=lambda w:(round(w[1]/3)*3,w[0]))
    return ' '.join(w[4] for w in selected)


def i9_page(page,result):
    scale=612/page.rect.width
    words=[(w[0]*scale,w[1],w[2]*scale,w[3],w[4]) for w in page.get_text('words')]
    anchors={w[1] for w in words if 300<=w[0]<330 and base_unit(w[4]) in {'KG','G','MG','MILHEIRO'}}
    found=0
    for row in word_rows(words,anchors):
        name=cell(row,105,300);base=base_unit(cell(row,300,330));quantity=number(cell(row,330,365),'en')
        price=number(cell(row,365,410),'en');count=number(cell(row,410,450),'en');total=number(cell(row,450,486),'en')
        if not name or quantity is None or quantity<=0 or count is None or price is None:continue
        warnings=[]
        if total is not None and abs(count*price-total)>max(.03,abs(total)*.005):warnings.append('Total I9 não confere com quantidade e preço')
        record=quote(name,quantity,base,price,cell(row,486,535),warnings)
        if record:result.rows.append(record);found+=1
    if found:result.methods.add('colunas I9')
    return found


def galena_page(page,result):
    scale=595/page.rect.width
    words=[(w[0]*scale,w[1],w[2]*scale,w[3],w[4]) for w in page.get_text('words')]
    anchors={w[1] for w in words if 325<=w[0]<350 and base_unit(w[4]) in {'KG','G','MG','MILHEIRO'}}
    found=0
    for row in word_rows(words,anchors):
        name=cell(row,58,282);price=number(cell(row,282,325));base=base_unit(cell(row,325,350))
        quantity=number(cell(row,350,389));total=number(cell(row,389,423))
        if not name or quantity is None or quantity<=0 or price is None:continue
        warnings=['Quantidade cotada usada como referência de embalagem; confirme a embalagem mínima']
        if total is not None and abs(quantity*price-total)>max(.03,abs(total)*.005):warnings.append('Total Galena precisa de conferência')
        if (number(cell(row,515,535),'en') or 0)>0:warnings.append('Confira os impostos da cotação')
        record=quote(name,quantity,base,price,cell(row,423,468),warnings)
        if record:result.rows.append(record);found+=1
    if found:result.methods.add('colunas Galena')
    return found


_OCR_LOCK=Lock()


@lru_cache(maxsize=1)
def ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,use_cls=False)
    except ImportError as error:
        raise ValueError('OCR não instalado. Atualize as dependências com iniciar.bat.') from error


def ocr_words(image):
    import numpy as np
    with _OCR_LOCK:
        data,_=ocr_engine()(np.asarray(image.convert('RGB'))[:,:,::-1].copy())
    words=[]
    for box,value,confidence in data or []:
        xs=[point[0] for point in box];ys=[point[1] for point in box]
        if confidence>=.55:words.append((min(xs),min(ys),max(xs),max(ys),value,float(confidence)))
    return words


def grouped_lines(words):
    groups=[]
    for word in sorted(words,key=lambda w:((w[1]+w[3])/2,w[0])):
        center=(word[1]+word[3])/2
        if groups and abs(center-groups[-1][0])<max(4,(word[3]-word[1])*.6):groups[-1][1].append(word)
        else:groups.append([center,[word]])
    return ['   '.join(w[4] for w in sorted(group,key=lambda w:w[0])) for _,group in groups]


def nutri_lines(lines):
    rows=[]
    date_pattern=re.compile(r'\d{2}/\d{2}/\d{4}')
    for line in lines:
        dates=list(date_pattern.finditer(line))
        if len(dates)!=2:continue
        product=line[:dates[0].start()].strip();tail=line[dates[1].end():]
        packs=list(PACK.finditer(tail))
        if not product or len(packs)<2:continue
        size,base=package(packs[0][0]);quantity,qbase=package(packs[1][0])
        amounts=re.findall(r'\d[\d.,]*[.,]\d{2,3}',tail[packs[1].end():])
        if size is None or quantity is None or len(amounts)!=2:continue
        total=number(amounts[-1]);price=number(amounts[0])
        if total is None or base!=qbase:continue
        derived=total/quantity
        warnings=[]
        # Price KG/L is per thousand for countable capsule rows, not per capsule.
        expected=derived*1000 if base in {'UN','CAPSULAS'} else derived
        if price is not None and abs(expected-price)>max(.03,abs(price)*.01):warnings.append('Preço por kg/l/milheiro precisa de conferência')
        record=quote(product,size,base,derived,dates[1][0],warnings)
        if record:rows.append(record)
    return rows


class OCRPage:
    def __init__(self,words,width):
        self.words=words
        self.rect=type('PageSize',(),{'width':width})()
    def get_text(self,kind):return self.words


def ocr_i9_lines(lines):
    rows=[]
    decimal=r'[0-9,]+\.[0-9]+'
    pattern=re.compile(r'^(.*?)\s+(MH|KG|G|MG)\s*('+decimal+r')\s+('+decimal+r')\s+('+decimal+r')\s+([0-9,]+\.[0-9]{2})\s*(\d{2}/\d{2}/\d{4})',re.I)
    for line in lines:
        m=pattern.search(line)
        if not m:continue
        name=re.sub(r'^[A-Z0-9-]*\d[A-Z0-9-]*?(?=(?:CAP|VCAP|DRCAP|TAPIO))','',m[1],flags=re.I)
        first=name.split()[0] if name.split() else ''
        if len(first)>=7 and re.search(r'\d',first) and not normalize(first).startswith(('CAP','VCAP','DRCAP','TAPIO')):
            name=name[len(first):].strip()
        size=number(m[3],'en');price=number(m[4],'en');quantity=number(m[5],'en');total=number(m[6],'en')
        if not size or price is None or quantity is None:continue
        warnings=[]
        if total is not None and abs(quantity*price-total)>max(.03,abs(total)*.005):warnings.append('Total OCR não confere com preço e quantidade')
        row=quote(name,size,base_unit(m[2]),price,m[7],warnings)
        if row:rows.append(row)
    return rows


def ocr_galena_lines(lines):
    rows=[]
    money=r'(?:R\$\s*)?[0-9.]+,[0-9]{2}'
    pattern=re.compile(r'^(.*?)\s+('+money+r')\s*(KG|MG|G|MI|MIL)\s*([0-9.]+,[0-9]{4})\s+('+money+r')\s*(\d{2}/\d{2}/\d{4})',re.I)
    for line in lines:
        m=pattern.search(line)
        if not m:continue
        name=re.sub(r'^\d{1,3}\s+','',m[1]).strip()
        quantity=number(m[4]);price=number(m[2]);total=number(m[5])
        if len(name)<3 or not quantity or price is None:continue
        warnings=['Quantidade cotada usada como referência de embalagem; confirme a embalagem mínima']
        if total is not None and abs(quantity*price-total)>max(.03,abs(total)*.005):warnings.append('Total OCR não confere com quantidade e preço')
        record=quote(name,quantity,base_unit(m[3]),price,m[6],warnings)
        if record:rows.append(record)
    return rows


def ocr_other_layouts(words,width,signature):
    temporary=DocumentResult();compact=signature.replace(' ','')
    facade=OCRPage(words,width)
    if 'VALORDEVENDA' in compact and 'PRECOTOTAL' in compact:
        temporary.rows=ocr_i9_lines(grouped_lines(words))
        if not temporary.rows:i9_page(facade,temporary)
    elif ('GALENA' in compact and 'VALOR' in compact) or ('ICMS' in compact and 'QTD' in compact and 'VALOR' in compact):
        temporary.rows=ocr_galena_lines(grouped_lines(words))
        if not temporary.rows:galena_page(facade,temporary)
    else:
        pn='PRODUTO' in compact and 'QTDE' in compact and 'EMBALAGEM' in compact and 'PRECO' in compact
        pharma='QTDA' in compact and 'VLRUNIT' in compact and 'ITENS' in compact
        if not (pn or pharma):return []
        canonical=842 if pn else 595
        scaled=[(w[0]*canonical/width,w[1],w[2]*canonical/width,w[3],w[4]) for w in words]
        if pn:
            anchors={w[1] for w in scaled if 425<=w[0]<465 and base_unit(w[4]) in {'KG','G','MG','MILHEIRO','UN'}}
            cuts=[0,300,365,425,465,540,615,700,750,842]
        else:
            anchors={w[1] for w in scaled if 20<=w[0]<55 and re.fullmatch(r'\d{1,3}',text(w[4]))}
            cuts=[20,55,285,325,355,410,445,515,580]
        for group in word_rows(scaled,anchors):
            values=[cell(group,cuts[i],cuts[i+1]) for i in range(len(cuts)-1)]
            row=pn_row(values) if pn else pharma_row(values)
            if row:temporary.rows.append(row)
    return temporary.rows


def ocr_page(image,result):
    words=ocr_words(image);lines=grouped_lines(words)
    joined=normalize(' '.join(lines));rows=[]
    if ('FABRICACAO' in joined or 'PROCEDENCIA' in joined) and 'COTADA' in joined:
        rows=nutri_lines(lines)
    if not rows:rows=ocr_other_layouts(words,image.width,joined)
    # Shared Brazilian quote template; the fixed columns are used only after matching its headers.
    if not rows and 'VALORKG' in joined.replace(' ','') and ('VALORUNIT' in joined.replace(' ','') or 'TOTALCOM' in joined.replace(' ','')):
        width=image.width
        origin=next((w for w in words if normalize(w[4])=='ORIGEM'),None)
        # Florien's header has wider description/origin columns than the other shared suppliers.
        florien=origin is not None and (origin[0]+origin[2])/2/width>.29
        cuts=([0,.261,.348,.418,.468,.527,.603,.690,.785,.829,.871,1] if florien else
              [0,.239,.309,.397,.453,.512,.588,.681,.769,.827,.888,1])
        dates=[w for w in words if re.fullmatch(r'\d{2}/\d{2}/\d{4}',text(w[4])) and cuts[2]<=((w[0]+w[2])/2/width)<cuts[3]]
        anchors=sorted((w[1]+w[3])/2 for w in dates)
        for i,anchor in enumerate(anchors):
            lo=(anchors[i-1]+anchor)/2 if i else anchor-15
            hi=(anchor+anchors[i+1])/2 if i+1<len(anchors) else anchor+15
            cells=[[] for _ in range(11)]
            for w in words:
                center=(w[1]+w[3])/2;x=(w[0]+w[2])/2/width
                if not lo<=center<hi:continue
                index=next((j for j in range(11) if cuts[j]<=x<cuts[j+1]),None)
                if index is not None:cells[index].append(w)
            row=[' '.join(w[4] for w in sorted(values,key=lambda w:(w[1],w[0]))) for values in cells]
            record=shared_row(row)
            if record:rows.append(record)
    for record in rows:
        record['import_warning']='; '.join(filter(None,[record['import_warning'],'Leitura por OCR: confira descrição, embalagem, preço e validade antes de aprovar']))
    result.rows.extend(rows);result.methods.add('OCR local')
    if rows:result.warnings.append('OCR pode omitir ou interpretar incorretamente linhas; confira a tabela completa no original.')
    if not rows:result.warnings.append('OCR executado, mas o layout da tabela não foi reconhecido. Envie uma imagem nítida e completa da tabela.')


def extract_document(raw,filename):
    result=DocumentResult()
    if filename.lower().endswith(('.jpg','.jpeg','.png')):
        from PIL import Image,ImageOps
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.width*source.height>30_000_000:raise ValueError('Imagem muito grande; reduza para até 30 megapixels')
                image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((2400,3000))
        except (OSError,Image.DecompressionBombError) as error:raise ValueError('Imagem inválida ou corrompida') from error
        ocr_page(image,result)
        return result
    try:document=fitz.open(stream=raw,filetype='pdf')
    except Exception as error:raise ValueError('Documento PDF inválido ou corrompido') from error
    with document:
        if document.needs_pass:raise ValueError('PDF protegido por senha. Envie uma cópia desbloqueada.')
        if len(document)>50:raise ValueError('PDF com mais de 50 páginas; divida o documento')
        full_text=' '.join(page.get_text() for page in document)
        signature=normalize(full_text)
        is_i9='VALOR DE VENDA' in signature and 'PRECO TOTAL' in signature and 'EMBALAGEM' in signature
        is_galena='GALENA' in signature and 'VALOR UNIT' in signature and 'VALOR ITEM' in signature
        compact=signature.replace(' ','')
        layout_parser=active_row if 'PRECOGMLH' in compact and 'FRACIONAMENTO' in compact and 'INSUMO' in compact else (embrafarma_row if 'VALORDAST' in compact and 'VALORUNITARIO' in compact and 'DCB' in compact and 'QTDE' in compact else None)
        shared_cuts=None
        if not is_i9 and not is_galena:
            for table in document[0].find_tables().tables if len(document) else []:
                rows=table.extract()
                if rows and len(rows[0])==11 and normalize(rows[0][0])=='DESCRICAO':
                    cells=table.rows[0].cells
                    if all(cells):shared_cuts=[cell[0] for cell in cells]+[cells[-1][2]]
        scanned=0
        for page in document:
            native=page.get_text()
            if len(native.strip())<40:
                scanned+=1
                if scanned>10:raise ValueError('Mais de 10 páginas exigem OCR; divida o documento')
                from PIL import Image
                pixmap=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                image=Image.frombytes('RGB',[pixmap.width,pixmap.height],pixmap.samples)
                ocr_page(image,result);continue
            if is_i9:
                i9_page(page,result);continue
            if is_galena:
                galena_page(page,result);continue
            if shared_cuts:
                shared_page(page,result,shared_cuts);continue
            if native_tables(page,result,layout_parser):continue
            nutri=nutri_lines(native.splitlines())
            if nutri:result.rows.extend(nutri);result.methods.add('tabela Nutrifarm')
        if not result.rows:result.warnings.append('Nenhuma tabela de cotação reconhecida neste layout.')
    return result


def spreadsheet_rows(raw,filename):
    """Read legacy XLS without converting formulas or guessing dates."""
    if not filename.lower().endswith('.xls'):raise ValueError('Formato de planilha não suportado')
    try:
        import xlrd
        workbook=xlrd.open_workbook(file_contents=raw,on_demand=True)
        sheets=[]
        try:
            for sheet in workbook.sheets():
                rows=[]
                for i in range(min(sheet.nrows,1500)):
                    values=[]
                    for j in range(min(sheet.ncols,17)):
                        cell=sheet.cell(i,j)
                        value=cell.value
                        if cell.ctype==xlrd.XL_CELL_DATE:
                            value=xlrd.xldate_as_datetime(value,workbook.datemode).date().isoformat()
                        values.append(value)
                    values += [None]*(17-len(values))
                    if any(value not in (None,'') for value in values):rows.append(values)
                sheets.append((sheet.name,rows))
        finally:workbook.release_resources()
        return sheets
    except ImportError as error:raise ValueError('Leitor XLS não instalado. Atualize as dependências.') from error
    except Exception as error:raise ValueError('Planilha XLS inválida ou corrompida') from error


def spreadsheet_quote_rows(sheets):
    result=DocumentResult()
    for _,rows in sheets:
        for i,header in enumerate(rows):
            labels=[normalize(value) for value in header]
            def col(*keys):return next((j for j,value in enumerate(labels) if value in keys),None)
            product=col('PRODUTO','DESCRICAO','DESCRICAO DO PRODUTO','NOME DO PRODUTO')
            if product is None:continue
            pack=col('EMBALAGEM','APRESENTACAO');qty=col('QTD EMBALAGEM','QUANTIDADE EMBALAGEM','QUANTIDADE BASE','BASE QTY')
            unit_col=col('UNIDADE','UNIDADE BASE','UN','BASE UNIT')
            price=col('PRECO UNITARIO','VALOR UNITARIO','PRECO BASE','CUSTO UNITARIO','UNIT COST')
            total=col('TOTAL','VALOR TOTAL','VALOR ITEM','PRECO EMBALAGEM')
            expiry=col('VALIDADE','DATA VALIDADE','DATA DE VALIDADE','VENCIMENTO')
            if price is None and total is None:break
            for row in rows[i+1:]:
                if not row[product]:continue
                quantity,base=package(row[pack]) if pack is not None else (None,None)
                if qty is not None and unit_col is not None:
                    quantity=number(row[qty]);base=base_unit(row[unit_col])
                unit_price=number(row[price]) if price is not None else None
                pack_total=number(row[total]) if total is not None else None
                warning=[]
                if unit_price is None and pack_total is not None and quantity:
                    unit_price=pack_total/quantity
                    warning.append('Total da planilha tratado como valor de uma embalagem; confira a quantidade cotada')
                if unit_price is None:continue
                if quantity and pack_total is not None and abs(quantity*unit_price-pack_total)>max(.03,abs(pack_total)*.005):warning.append('Total da planilha diverge do preço e da embalagem; confira a base dos valores')
                value=quote(row[product],quantity,base,unit_price,row[expiry] if expiry is not None else '',warning)
                if value:result.rows.append(value)
            break
    result.methods.add('planilha')
    return result
