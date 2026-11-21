"""Kaydedilmiş gerçek sonuçtan Türkçe, gömülü fontlu yerel PDF raporu."""
from pathlib import Path
from io import BytesIO
from datetime import datetime,timezone
from xml.sax.saxutils import escape
import threading
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
LOCK=threading.Lock()
def report_bytes(result):
    if not result.get('physical_validation', {}).get('pass'):
        raise ValueError('Fizik kabulü geçmeyen sonuca PDF verilmez.')
    with LOCK:
        font=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
        pdfmetrics.registerFont(TTFont('UygulamaTR',str(font)))
        s=ParagraphStyle('tr',fontName='UygulamaTR',fontSize=10,leading=14,spaceAfter=9)
        h=ParagraphStyle('baslik',parent=s,fontSize=17,leading=22,spaceAfter=15)
        title='ŞebekeKalkan'
        authors='Öğr. Gör. Enise Odabaş · Öğr. Gör. Mert Hızmalı'
        def p(t,style=s):return Paragraph(escape(str(t)),style)
        def f(v):return '—' if v is None else format(float(v),'.3f').replace('.',',')
        body=[p(title+' — hesaplama raporu',h),p(authors),p('Rapor üretimi (UTC): '+datetime.now(timezone.utc).isoformat()),p('Bu rapor kaydedilmiş hesaplama sonucundan üretilmiştir. Tam girdiler ve ham ölçütler aynı deneyin JSON dosyasındadır.')]
        if 'record_id' in result:
            body.append(p('Kayıt kimliği: ' + result['record_id']))
        body.extend([
            p('Girdi SHA-256: ' + result['input_sha256']),
            p('Fiziksel doğrulama: geçti. Model sürümü: ' + result['model_version']),
        ])
        rows = [['Yöntem', 'Hizmet açığı (m³)', 'Ağırlıklı (m³)', 'Son onarım (saat)']]
        for method in result['methods'].values():
            metrics = method['metrics']
            rows.append([method['name'], f(metrics['unmet_demand_volume_m3']),
                         f(metrics['weighted_unmet_volume_m3']), f(metrics['repair_completion_hour'])])
        note='Net3 açık kıyaslama ağıdır. Hizmet açığı kaçak su hacmi değildir. Eşit sonuçlar ve hacim/bitiş ödünleşimi tam JSON kaydında korunur. Genel algoritmik üstünlük veya saha su tasarrufu kanıtlanmamıştır.'
        values=[[p(c) for c in row] for row in rows];table=Table(values,repeatRows=1,colWidths=[500/len(rows[0])]*len(rows[0]))
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eff3')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#b4c4cb')),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        body.extend([Spacer(1, 10), table, Spacer(1, 15)])
        body.extend(p(warning) for warning in result['methods']['proposal']['warnings'])
        body.extend([p('Veri ve yöntem', h), p(note)])
        out=BytesIO();SimpleDocTemplate(out,pagesize=(595.276,841.89),leftMargin=47,rightMargin=47,topMargin=50,bottomMargin=50,title=title+' hesaplama raporu',author=authors).build(body)
        return out.getvalue()
