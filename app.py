import os,re,sqlite3,unicodedata,math,io
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.responses import HTMLResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
import fitz
from difflib import SequenceMatcher

ROOT=Path(__file__).parent; DB=Path(os.environ.get('SONIFARMA_COMPRAS_DB', ROOT/'compras.sqlite3'))
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,title='Sonifarma | Inteligência de Compras V1.7')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS processes(id INTEGER PRIMARY KEY,name TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS needs(id INTEGER PRIMARY KEY,process_id INTEGER,code TEXT,name TEXT,qty REAL,unit TEXT,last_cost REAL,previous_supplier TEXT);
 CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY,process_id INTEGER,supplier TEXT,product TEXT,pack TEXT,base_qty REAL,base_unit TEXT,total REAL,unit_cost REAL,expiry TEXT,source TEXT,quote_date TEXT);
 CREATE TABLE IF NOT EXISTS matches(need_id INTEGER,quote_id INTEGER,approved INTEGER DEFAULT 0,PRIMARY KEY(need_id,quote_id));
 CREATE TABLE IF NOT EXISTS choices(need_id INTEGER PRIMARY KEY,quote_id INTEGER,reason TEXT,changed TEXT);
 CREATE TABLE IF NOT EXISTS purchase_audit(id INTEGER PRIMARY KEY,process_id INTEGER,need_id INTEGER,quote_id INTEGER,action TEXT,reason TEXT,created TEXT);''')
init()
from auth import install_auth
install_auth(app, db)

@app.get('/login',response_class=HTMLResponse)
def login_page():return (ROOT/'templates'/'login.html').read_text(encoding='utf-8')

def norm(s):
 s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().upper()
 return re.sub(r'[^A-Z0-9]+',' ',s).strip()
def num(v):
 if isinstance(v,(float,int)):return float(v) if math.isfinite(v) else None
 s=str(v or '').replace('R$','').strip().replace(' ','')
 if ',' in s:s=s.replace('.','').replace(',','.')
 try:
  value=float(s)
  return value if math.isfinite(value) else None
 except:return None

def rows_xlsx(raw):
 try:w=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
 except Exception:raise HTTPException(400,'Planilha XLSX inválida ou corrompida')
 try:
  out=[]
  for sheet in w.worksheets:
   rr=[]
   for row in sheet.iter_rows(max_row=1500,max_col=17,values_only=True):
    if any(x is not None for x in row):rr.append(list(row))
   out.append((sheet.title,rr))
  return out
 finally:w.close()

def create_process(name):
 name=name.strip()
 if not name or len(name)>160:raise HTTPException(400,'Informe um nome de processo entre 1 e 160 caracteres')
 with db() as c:
  cur=c.execute('INSERT INTO processes(name,created) VALUES (?,?)',(name,datetime.now().isoformat(timespec='seconds')))
  return cur.lastrowid

def add_need(pid,r):
 code,name,previous,qty,unit,cost=(list(r)+[None]*6)[:6]
 if not name:return
 with db() as c:c.execute('INSERT INTO needs(process_id,code,name,qty,unit,last_cost,previous_supplier) VALUES (?,?,?,?,?,?,?)',(pid,str(code or ''),str(name).strip(),num(qty),str(unit or ''),num(cost),str(previous or '')))

def add_quote(pid,supplier,product,pack,base_qty,base_unit,total,unit_cost,expiry,source,date=''):
 if not product or not supplier:return
 with db() as c:c.execute('INSERT INTO quotes(process_id,supplier,product,pack,base_qty,base_unit,total,unit_cost,expiry,source,quote_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(pid,str(supplier),str(product).strip(),str(pack or ''),num(base_qty),str(base_unit or ''),num(total),num(unit_cost),str(expiry or ''),str(source),str(date)))

def seed():
 with db() as c:
  if c.execute('SELECT COUNT(*) FROM processes').fetchone()[0]:return
 source=ROOT/'amostras'/'comparativo_inicial.xlsx'
 if not source.is_file():
  create_process('Novo processo de compras')
  return
 pid=create_process('Outubro 2026 — Dados reais importados')
 data=rows_xlsx(source.read_bytes())
 for sheet,rr in data:
  if sheet=='Necessidade original':
   for r in rr[1:]:add_need(pid,r)
  if sheet=='Todas as cotações':
   for r in rr[1:]:add_quote(pid,r[0],r[1],r[2],r[3],r[4],r[5],r[7],r[8],r[9])
seed()

@app.get('/',response_class=HTMLResponse)
def home():return (ROOT/'templates'/'index.html').read_text(encoding='utf-8')
def require_process(pid):
 with db() as c:
  if not c.execute('SELECT 1 FROM processes WHERE id=?',(pid,)).fetchone():raise HTTPException(404,'Processo não encontrado')

@app.get('/api/processes')
def processes():
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM processes ORDER BY id DESC')]
@app.post('/api/processes')
def new_process(name:str=Form(...)):return {'id':create_process(name)}
def select_champions_automatically(pid):
 """Select safe lowest-cost options on read/import, without overwriting user choices.
 A quote is eligible only when unit matches and link is approved or name is exact.
 """
 with db() as c:
  needs=c.execute('SELECT * FROM needs WHERE process_id=?',(pid,)).fetchall()
  quotes=c.execute('SELECT * FROM quotes WHERE process_id=? AND unit_cost IS NOT NULL AND unit_cost>=0',(pid,)).fetchall()
  approved={(r['need_id'],r['quote_id']) for r in c.execute('SELECT need_id,quote_id FROM matches WHERE approved=1')}
  for n in needs:
   if c.execute('SELECT 1 FROM choices WHERE need_id=?',(n['id'],)).fetchone():continue
   # A buyer's explicit removal persists across refreshes and imports.
   if c.execute("SELECT 1 FROM purchase_audit WHERE need_id=? AND action='REMOVER' LIMIT 1",(n['id'],)).fetchone():continue
   unit=norm(n['unit']);name=norm(n['name'])
   if not unit or not name:continue
   eligible=[]
   for q in quotes:
    if norm(q['base_unit'])!=unit:continue
    if (n['id'],q['id']) in approved:eligible.append((0,q))
    elif norm(q['product'])==name:eligible.append((1,q))
   if not eligible:continue
   # Only verified links, when available, take precedence over unverified exact-name quotes.
   priority=min(rank for rank,_ in eligible)
   best=min((q for rank,q in eligible if rank==priority),key=lambda q:(q['unit_cost'],q['supplier'],q['id']))
   reason='Campeão automático: vínculo aprovado' if priority==0 else 'Campeão automático: nome exato e unidade igual (conferir)'
   now=datetime.now().isoformat(timespec='seconds')
   c.execute('INSERT OR IGNORE INTO choices VALUES (?,?,?,?)',(n['id'],best['id'],reason,now))
   c.execute('INSERT INTO purchase_audit(process_id,need_id,quote_id,action,reason,created) VALUES (?,?,?,?,?,?)',(pid,n['id'],best['id'],'CAMPEAO_AUTOMATICO',reason,now))

@app.get('/api/data/{pid}')
def data(pid:int):
 require_process(pid)
 select_champions_automatically(pid)
 with db() as c:
  needs=[dict(r) for r in c.execute('SELECT * FROM needs WHERE process_id=? ORDER BY name',(pid,))]
  quotes=[dict(r) for r in c.execute('SELECT * FROM quotes WHERE process_id=? ORDER BY supplier,product',(pid,))]
  choices={r['need_id']:dict(r) for r in c.execute('SELECT * FROM choices')}
  matches={}
  for r in c.execute('SELECT * FROM matches WHERE approved=1'):matches.setdefault(r['need_id'],set()).add(r['quote_id'])
  selected_total=0.0; indicative_saving=0.0; comparable_count=0; pending=0; champion_count=0
  for n in needs:
   candidates=[]
   for q in quotes:
    score=SequenceMatcher(None,norm(n['name']),norm(q['product'])).ratio()
    verified=q['id'] in matches.get(n['id'],set())
    if verified or score>=0.78:
     candidates.append({**q,'score':round(score*100),'verified':verified})
   # Only approved links count as verified equivalences; unapproved name similarity is a suggestion.
   candidates.sort(key=lambda x:(not x['verified'],-x['score'],x['unit_cost'] if x['unit_cost'] is not None else 1e30))
   n['candidates']=candidates[:25];n['choice']=choices.get(n['id'])
   chosen=next((q for q in quotes if n['choice'] and q['id']==n['choice']['quote_id']),None)
   verified_quotes=[q for q in candidates if q['verified'] and q['unit_cost'] is not None and q['unit_cost']>=0 and norm(q['base_unit']) and norm(q['base_unit'])==norm(n['unit'])]
   champion=min(verified_quotes,key=lambda q:q['unit_cost']) if verified_quotes else None
   n['champion']={'id':champion['id'],'supplier':champion['supplier'],'unit_cost':champion['unit_cost']} if champion else None
   if champion:champion_count+=1
   n['comparison_status']='Sem seleção'
   n['selected_total']=None;n['saving']=None;n['delta_pct']=None
   if chosen:
    if n['qty'] is not None and n['qty']>0 and chosen['unit_cost'] is not None and chosen['unit_cost']>=0 and norm(chosen['base_unit'])==norm(n['unit']) and norm(n['unit']):
     n['selected_total']=round(n['qty']*chosen['unit_cost'],2)
     selected_total+=n['selected_total']
     n['comparison_status']='Custo estimado (unidade compatível)'
     if n['last_cost'] is not None and n['last_cost']>=0:
      n['saving']=round((n['last_cost']-chosen['unit_cost'])*n['qty'],2)
      indicative_saving+=n['saving'];comparable_count+=1
      if n['last_cost']>0:n['delta_pct']=round((chosen['unit_cost']/n['last_cost']-1)*100,2)
      n['comparison_status']='Comparação indicativa: confirmar base do último custo'
    else:n['comparison_status']='Sem unidade/quantidade compatível para calcular'
   else:pending+=1
  return {'needs':needs,'quotes':quotes,'summary':{'needs':len(needs),'quotes':len(quotes),'suppliers':len(set(q['supplier'] for q in quotes)),'selected':sum(bool(n['choice']) for n in needs),'pending':pending,'champions':champion_count,'selected_total':round(selected_total,2),'indicative_saving':round(indicative_saving,2),'comparable_count':comparable_count}}
@app.post('/api/auto-champions/{pid}')
def auto_champions(pid:int):
 """Only auto-pick previously approved matches with comparable unit costs.
 Existing buyer choices are never overwritten.
 """
 with db() as c:
  needs=c.execute('SELECT * FROM needs WHERE process_id=?',(pid,)).fetchall()
  created=0;skipped=0
  for n in needs:
   if c.execute('SELECT 1 FROM choices WHERE need_id=?',(n['id'],)).fetchone():continue
   if not norm(n['unit']):skipped+=1;continue
   quotes=c.execute("""SELECT q.* FROM quotes q JOIN matches m ON m.quote_id=q.id
      WHERE m.need_id=? AND m.approved=1 AND q.process_id=? AND q.unit_cost IS NOT NULL AND q.unit_cost>=0""",(n['id'],pid)).fetchall()
   valid=[q for q in quotes if norm(q['base_unit'])==norm(n['unit']) and norm(q['base_unit'])]
   if not valid:skipped+=1;continue
   best=min(valid,key=lambda q:(q['unit_cost'],q['supplier']))
   now=datetime.now().isoformat(timespec='seconds')
   c.execute('INSERT INTO choices VALUES (?,?,?,?)',(n['id'],best['id'],'Campeão automático entre vínculos aprovados',now))
   c.execute('INSERT INTO purchase_audit(process_id,need_id,quote_id,action,reason,created) VALUES (?,?,?,?,?,?)',(pid,n['id'],best['id'],'CAMPEAO_AUTOMATICO','Menor custo unitário entre vínculos aprovados com unidade igual',now))
   created+=1
 return {'selected':created,'pending':skipped,'warning':'Somente vínculos previamente aprovados, com unidade base idêntica. Confira embalagens, preços e condições antes de fechar.'}

@app.post('/api/choose')
def choose(need_id:int=Form(...),quote_id:int=Form(...),reason:str=Form('Escolha manual')):
 with db() as c:
  n=c.execute('SELECT process_id FROM needs WHERE id=?',(need_id,)).fetchone()
  q=c.execute('SELECT process_id FROM quotes WHERE id=?',(quote_id,)).fetchone()
  if not n or not q or n[0]!=q[0]:raise HTTPException(400,'Produto e cotação incompatíveis')
  c.execute('INSERT OR REPLACE INTO choices VALUES (?,?,?,?)',(need_id,quote_id,reason,datetime.now().isoformat(timespec='seconds')))
  c.execute('INSERT INTO purchase_audit(process_id,need_id,quote_id,action,reason,created) VALUES (?,?,?,?,?,?)',(n[0],need_id,quote_id,'SELECIONAR',reason,datetime.now().isoformat(timespec='seconds')))
 return {'ok':True}
@app.post('/api/match')
def match(need_id:int=Form(...),quote_id:int=Form(...)):
 with db() as c:
  n=c.execute('SELECT process_id FROM needs WHERE id=?',(need_id,)).fetchone()
  q=c.execute('SELECT process_id FROM quotes WHERE id=?',(quote_id,)).fetchone()
  if not n or not q or n[0]!=q[0]:raise HTTPException(400,'Processos diferentes')
  c.execute('INSERT OR REPLACE INTO matches VALUES (?,?,1)',(need_id,quote_id))
  c.execute('INSERT INTO purchase_audit(process_id,need_id,quote_id,action,reason,created) VALUES (?,?,?,?,?,?)',(n[0],need_id,quote_id,'VALIDAR_VINCULO','Equivalência aprovada pelo comprador',datetime.now().isoformat(timespec='seconds')))
 return {'ok':True}
@app.post('/api/needs/{pid}')
async def upload_needs(pid:int,file:UploadFile=File(...)):
 require_process(pid)
 raw=await file.read()
 if not (file.filename or '').lower().endswith('.xlsx'):raise HTTPException(400,'Necessidade deve ser XLSX')
 try:sheets=rows_xlsx(raw)
 except Exception:raise HTTPException(400,'Planilha XLSX inválida ou corrompida')
 count=0
 for _,rr in sheets:
  for i,r in enumerate(rr):
   if len(r)>1 and norm(r[0])=='CODIGO' and 'PRODUTO' in norm(r[1]):
    for item in rr[i+1:]:
     if item[1]:add_need(pid,item);count+=1
    break
 return {'imported':count}
@app.post('/api/quotes/{pid}')
async def upload_quotes(pid:int,supplier:str=Form(...),file:UploadFile=File(...)):
 require_process(pid)
 if not supplier.strip():raise HTTPException(400,'Informe o fornecedor')
 raw=await file.read();fn=(file.filename or '').lower();count=0
 if fn.endswith('.xlsx'):
  for sheet,rr in rows_xlsx(raw):
   if sheet.lower()=='todas as cotações':
    for r in rr[1:]:
     if r[1]:add_quote(pid,r[0] or supplier,r[1],r[2],r[3],r[4],r[5],r[7],r[8],file.filename);count+=1
   else:
    for i,r in enumerate(rr):
     headers=[norm(v) for v in r]
     if any('PRODUTO' in h or 'DESCRICAO' in h for h in headers):
      def idx(keys):return next((j for j,h in enumerate(headers) if any(k in h for k in keys)),None)
      pi=idx(['PRODUTO','DESCRICAO']);price=idx(['TOTAL','VALOR ITEM']);pack=idx(['EMBALAGEM','UNIDADE']);
      for x in rr[i+1:]:
       if pi is not None and x[pi] and price is not None and num(x[price]) is not None:
        add_quote(pid,supplier,x[pi],x[pack] if pack is not None else '',None,'',x[price],None,'',file.filename);count+=1
      break
 elif fn.endswith('.pdf'):
  try:
   with fitz.open(stream=raw,filetype='pdf') as doc:lines='\n'.join(p.get_text() for p in doc).splitlines()
  except Exception:raise HTTPException(400,'Documento PDF inválido ou corrompido')
  # Conservative extraction: only well-structured lines; avoid fabricated associations.
  pattern=re.compile(r'^\s*(.+?)\s{2,}(\d+[\.,]\d{2})\s{2,}(\d+[\.,]\d{2})\s*$')
  for line in lines:
   m=pattern.match(line)
   if m and len(m[1])>4:
    add_quote(pid,supplier,m[1],'',None,'',num(m[3]),None,'',file.filename);count+=1
 else:raise HTTPException(400,'Formato aceito: PDF ou XLSX')
 return {'imported':count,'warning':'Extração de PDF é preliminar. Confira os itens antes de aprovar. PDFs com layouts complexos podem não ser reconhecidos.'}
@app.get('/api/export/{pid}')
def export(pid:int):
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4,landscape
 buffer=io.BytesIO();doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),leftMargin=30,rightMargin=30)
 styles=getSampleStyleSheet();story=[Paragraph('SONIFARMA | RESUMO DE COMPRAS — SELEÇÕES MANUAIS',styles['Title']),Spacer(1,14)]
 with db() as c:
  rr=c.execute('''SELECT n.code,n.name,n.qty,n.unit,q.supplier,q.pack,q.total,q.unit_cost FROM choices ch JOIN needs n ON n.id=ch.need_id JOIN quotes q ON q.id=ch.quote_id WHERE n.process_id=? ORDER BY q.supplier,n.name''',(pid,)).fetchall()
 data=[['Código','Insumo','Necessidade','Fornecedor','Embalagem','Cotação R$','R$/un. base']]
 for r in rr:data.append([str(r[0] or ''),str(r[1])[:44],f'{r[2] or "?"} {r[3] or ""}',r[4],r[5],f'{r[6]:.2f}' if r[6] is not None else '-',f'{r[7]:.4f}' if r[7] is not None else '-'])
 if len(data)==1:story.append(Paragraph('Nenhum fornecedor foi selecionado neste processo.',styles['Normal']))
 else:
  t=Table(data,repeatRows=1,colWidths=[65,235,95,105,95,75,70]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#126b52')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTSIZE',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eef5f2')]),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.append(t)
 story.extend([Spacer(1,16),Paragraph('Relatório preliminar. Validar equivalência, embalagens, impostos, frete e validade antes de emitir pedidos.',styles['Normal'])]);doc.build(story);buffer.seek(0)
 return StreamingResponse(buffer,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="sonifarma_resumo_{pid}.pdf"'})


@app.post('/api/unchoose')
def unchoose(need_id:int=Form(...)):
 with db() as c:
  n=c.execute('SELECT process_id FROM needs WHERE id=?',(need_id,)).fetchone()
  if not n:raise HTTPException(404,'Insumo não encontrado')
  c.execute('DELETE FROM choices WHERE need_id=?',(need_id,))
  c.execute('INSERT INTO purchase_audit(process_id,need_id,action,created) VALUES (?,?,?,?)',(n[0],need_id,'REMOVER',datetime.now().isoformat(timespec='seconds')))
 return {'ok':True}

def draft_rows(pid):
 with db() as c:
  return [dict(r) for r in c.execute('''SELECT n.id AS need_id,n.code,n.name,n.qty,n.unit,n.last_cost,q.id AS quote_id,q.supplier,q.product,q.pack,q.base_unit,q.base_qty,q.total,q.unit_cost,ch.reason,ch.changed
  FROM choices ch JOIN needs n ON n.id=ch.need_id JOIN quotes q ON q.id=ch.quote_id WHERE n.process_id=? ORDER BY q.supplier,n.name''',(pid,))]

def prepare_draft(pid):
 rows=draft_rows(pid);groups={}
 for r in rows:
  valid=(r['qty'] is not None and r['qty']>0 and r['unit_cost'] is not None and r['unit_cost']>=0 and norm(r['unit']) and norm(r['unit'])==norm(r['base_unit']))
  r['estimated_cost']=round(r['qty']*r['unit_cost'],2) if valid else None
  r['status']='Estimativa por unidade compatível' if valid else 'PENDENTE: conferir unidade, quantidade e preço base'
  groups.setdefault(r['supplier'],[]).append(r)
 return groups

@app.get('/api/drafts/{pid}')
def drafts(pid:int):
 groups=prepare_draft(pid)
 return {'suppliers':[{'supplier':k,'items':v,'total_estimated':round(sum(x['estimated_cost'] or 0 for x in v),2),'pending':sum(x['estimated_cost'] is None for x in v)} for k,v in groups.items()]}

@app.get('/api/audit/{pid}')
def audit(pid:int):
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM purchase_audit WHERE process_id=? ORDER BY id DESC LIMIT 300',(pid,))]

@app.get('/api/drafts/{pid}/xlsx')
def drafts_xlsx(pid:int):
 from openpyxl import Workbook
 from openpyxl.styles import Font,PatternFill,Alignment
 from openpyxl.utils import get_column_letter
 w=Workbook();w.remove(w.active)
 groups=prepare_draft(pid)
 if not groups:groups={'Sem escolhas':[]}
 for i,(supplier,rows) in enumerate(groups.items()):
  title=re.sub(r'[\\/*?:\[\]]','',supplier).strip()[:27] or 'Fornecedor'
  title=f'{i+1:02d} {title}'[:31]
  sh=w.create_sheet(title)
  sh.append(['SONIFARMA - RASCUNHO DE COMPRAS | NÃO É PEDIDO ENVIADO'])
  sh.append(['Fornecedor:',supplier]);sh.append(['Processo:',str(pid)])
  sh.append(['Código','Insumo necessário','Qtd. necessária','Unidade','Produto cotado','Embalagem','Preço cotado R$','Preço base R$','Total estimado R$','Conferência','Motivo da escolha'])
  for r in rows:sh.append([r['code'],r['name'],r['qty'],r['unit'],r['product'],r['pack'],r['total'],r['unit_cost'],r['estimated_cost'],r['status'],r['reason']])
  sh.freeze_panes='A5';sh.auto_filter.ref=f'A4:K{max(4,sh.max_row)}'
  for cell in sh[4]:cell.fill=PatternFill('solid',fgColor='126B52');cell.font=Font(bold=True,color='FFFFFF');cell.alignment=Alignment(wrap_text=True)
  for col,width in enumerate([16,42,18,14,42,23,20,20,22,52,30],1):sh.column_dimensions[get_column_letter(col)].width=width
  for row in sh.iter_rows(min_row=5):
   for idx in [7,8,9]:row[idx-1].number_format='R$ #,##0.00'
   for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
 buffer=io.BytesIO();w.save(buffer);buffer.seek(0)
 return StreamingResponse(buffer,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="sonifarma_rascunhos_{pid}.xlsx"'})

@app.get('/api/drafts/{pid}/pdf')
def drafts_pdf(pid:int):
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,KeepTogether
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import landscape,A4
 from xml.sax.saxutils import escape
 buffer=io.BytesIO();doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=25,bottomMargin=25)
 st=getSampleStyleSheet();story=[];groups=prepare_draft(pid)
 for i,(supplier,rows) in enumerate(groups.items()):
  if i:story.append(PageBreak())
  story.append(Paragraph('SONIFARMA | RASCUNHO DE COMPRAS',st['Title']))
  story.append(Paragraph('Fornecedor: '+escape(supplier)+' | Processo: '+str(pid),st['Heading2']))
  story.append(Paragraph('DOCUMENTO PARA CONFERÊNCIA — NÃO REPRESENTA PEDIDO ENVIADO',st['Normal']))
  story.append(Spacer(1,12))
  data=[['Código','Insumo','Necessidade','Produto cotado','Preço base','Total estimado','Situação']]
  for r in rows:data.append([escape(str(r['code'] or '')),Paragraph(escape(str(r['name'] or '')),st['BodyText']),f"{r['qty'] or '?'} {r['unit'] or ''}",Paragraph(escape(str(r['product'] or '')),st['BodyText']),f"R$ {r['unit_cost']:.4f}" if r['unit_cost'] is not None else '-',f"R$ {r['estimated_cost']:.2f}" if r['estimated_cost'] is not None else '-',Paragraph(escape(r['status']),st['BodyText'])])
  t=Table(data,repeatRows=1,colWidths=[65,155,80,170,75,85,155],hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#126b52')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eef5f2')]),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t)
  total=sum(r['estimated_cost'] or 0 for r in rows);pending=sum(r['estimated_cost'] is None for r in rows)
  story.append(Spacer(1,12));story.append(Paragraph(f'Total estimado dos itens comparáveis: R$ {total:.2f} | Itens pendentes de conferência: {pending}',st['Heading3']))
  story.append(Paragraph('Conferir equivalência técnica, unidade base, embalagem, pedido mínimo, frete, tributos, validade e disponibilidade antes de aprovar.',st['Normal']))
 if not story:story.append(Paragraph('Nenhuma escolha registrada neste processo.',st['Normal']))
 doc.build(story);buffer.seek(0)
 return StreamingResponse(buffer,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="sonifarma_rascunhos_{pid}.pdf"'})
