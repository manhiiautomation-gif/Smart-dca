#!/usr/bin/env python3
'''Generate Phoenix v5.1 Bug Fix Plan PDF (Thai)'''

import os
import sys
import hashlib

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, HRFlowable, Preformatted
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus import SimpleDocTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ── Fonts ──
FONT_DIR = '/usr/share/fonts'

# Primary font (Latin + Thai + CJK coverage)
pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerifBold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerifBold')

# Sans-serif for code labels
pdfmetrics.registerFont(TTFont('FreeSans', f'{FONT_DIR}/truetype/freefont/FreeSans.ttf'))

# Code font (monospace)
pdfmetrics.registerFont(TTFont('SarasaMono', f'{FONT_DIR}/truetype/chinese/SarasaMonoSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('SarasaMonoBold', f'{FONT_DIR}/truetype/chinese/SarasaMonoSC-Bold.ttf'))
registerFontFamily('SarasaMono', normal='SarasaMono', bold='SarasaMonoBold')

# ━━ Cascade Palette ━━
PAGE_BG       = colors.HexColor('#f5f5f4')
SECTION_BG    = colors.HexColor('#f2f1f0')
CARD_BG       = colors.HexColor('#ebeae8')
TABLE_STRIPE  = colors.HexColor('#ededeb')
HEADER_FILL   = colors.HexColor('#4e4732')
COVER_BLOCK   = colors.HexColor('#746c56')
BORDER        = colors.HexColor('#c5bfac')
ICON          = colors.HexColor('#a48e4b')
ACCENT        = colors.HexColor('#92761f')
ACCENT_2      = colors.HexColor('#3aa0c2')
TEXT_PRIMARY   = colors.HexColor('#151513')
TEXT_MUTED     = colors.HexColor('#7e7c74')
SEM_SUCCESS   = colors.HexColor('#529067')
SEM_WARNING   = colors.HexColor('#8c7443')
SEM_ERROR     = colors.HexColor('#a25b54')
SEM_INFO      = colors.HexColor('#507aa4')

FONT_BODY = 'FreeSerif'
FONT_HEADING = 'FreeSerifBold'
FONT_CODE = 'SarasaMono'

# ── Styles ──
styles = getSampleStyleSheet()

s_h1 = ParagraphStyle(
    'H1Thai', parent=styles['Heading1'],
    fontName=FONT_HEADING, fontSize=18, leading=26,
    textColor=HEADER_FILL, spaceBefore=6*mm, spaceAfter=3.5*mm,
    borderPadding=(0, 0, 1.5*mm, 0),
)

s_h2 = ParagraphStyle(
    'H2Thai', parent=styles['Heading2'],
    fontName=FONT_HEADING, fontSize=14, leading=20,
    textColor=ACCENT, spaceBefore=5*mm, spaceAfter=2*mm,
)

s_body = ParagraphStyle(
    'BodyThai', parent=styles['Normal'],
    fontName=FONT_BODY, fontSize=10.5, leading=18,
    textColor=TEXT_PRIMARY, alignment=TA_JUSTIFY,
    spaceBefore=1*mm, spaceAfter=2*mm,
)

s_body_indent = ParagraphStyle(
    'BodyIndent', parent=s_body,
    leftIndent=6*mm,
)

s_code = ParagraphStyle(
    'CodeBlock', parent=styles['Code'],
    fontName=FONT_CODE, fontSize=8, leading=12,
    textColor=TEXT_PRIMARY, backColor=CARD_BG,
    borderPadding=(2.5*mm, 2.5*mm, 2.5*mm, 2.5*mm),
    leftIndent=4*mm, rightIndent=4*mm,
    spaceBefore=1.5*mm, spaceAfter=2.5*mm,
)

s_caption = ParagraphStyle(
    'Caption', parent=s_body,
    fontSize=9, leading=13,
    textColor=TEXT_MUTED, alignment=TA_LEFT,
    spaceBefore=1*mm, spaceAfter=1.5*mm,
)

s_callout = ParagraphStyle(
    'Callout', parent=s_body,
    fontName=FONT_BODY, fontSize=10, leading=16,
    textColor=SEM_ERROR, backColor=colors.HexColor('#fdf2f2'),
    borderColor=SEM_ERROR, borderWidth=1, borderPadding=(2.5*mm, 3*mm, 2.5*mm, 3*mm),
    leftIndent=4*mm, rightIndent=4*mm,
    spaceBefore=2*mm, spaceAfter=2.5*mm,
)

s_success = ParagraphStyle(
    'Success', parent=s_body,
    fontName=FONT_BODY, fontSize=10, leading=16,
    textColor=SEM_SUCCESS, backColor=colors.HexColor('#f0fdf4'),
    borderColor=SEM_SUCCESS, borderWidth=1, borderPadding=(2.5*mm, 3*mm, 2.5*mm, 3*mm),
    leftIndent=4*mm, rightIndent=4*mm,
    spaceBefore=2*mm, spaceAfter=2.5*mm,
)

s_info = ParagraphStyle(
    'Info', parent=s_body,
    fontName=FONT_BODY, fontSize=10, leading=16,
    textColor=SEM_INFO, backColor=colors.HexColor('#eff6ff'),
    borderColor=SEM_INFO, borderWidth=1, borderPadding=(2.5*mm, 3*mm, 2.5*mm, 3*mm),
    leftIndent=4*mm, rightIndent=4*mm,
    spaceBefore=2*mm, spaceAfter=2.5*mm,
)

# ── TOC styles ──
toc_level0 = ParagraphStyle(
    'TOC0', fontName=FONT_HEADING, fontSize=12, leading=20,
    textColor=HEADER_FILL, leftIndent=0,
)
toc_level1 = ParagraphStyle(
    'TOC1', fontName=FONT_BODY, fontSize=10, leading=16,
    textColor=TEXT_PRIMARY, leftIndent=20,
)

# ── Custom DocTemplate for TOC ──
class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

# ── Helpers ──
def h1(text, level=0):
    key = f'h_{hashlib.md5(text.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{key}"/>{text}', s_h1)
    p.bookmark_name = key
    p.bookmark_level = level
    p.bookmark_text = text
    p.bookmark_key = key
    return p

def h2(text, level=1):
    key = f'h_{hashlib.md5(text.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{key}"/>{text}', s_h2)
    p.bookmark_name = key
    p.bookmark_level = level
    p.bookmark_text = text
    p.bookmark_key = key
    return p

def body(text):
    return Paragraph(text, s_body)

def body_i(text):
    return Paragraph(text, s_body_indent)

def code(text):
    safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return Paragraph(safe, s_code)

def callout(text):
    return Paragraph(text, s_callout)

def success(text):
    return Paragraph(text, s_success)

def info(text):
    return Paragraph(text, s_info)

def hr():
    return HRFlowable(width='100%', thickness=0.5, color=BORDER, spaceBefore=6, spaceAfter=6)

def make_table(headers, rows, col_widths=None):
    """Create styled table with header row."""
    pw = A4[0] - 60*mm  # available width
    if col_widths is None:
        n = len(headers)
        col_widths = [pw / n] * n
    
    header_cells = [Paragraph(h, ParagraphStyle('th', fontName=FONT_HEADING, fontSize=9, leading=13, textColor=colors.white, alignment=TA_CENTER)) for h in headers]
    data = [header_cells]
    for row in rows:
        cells = [Paragraph(str(c), ParagraphStyle('td', fontName=FONT_BODY, fontSize=9, leading=13, textColor=TEXT_PRIMARY)) for c in row]
        data.append(cells)
    
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_STRIPE))
    t.setStyle(TableStyle(style_cmds))
    return t

# ── Build Story ──
OUTPUT = '/home/z/my-project/download/phoenix_v5.1_bug_fix_plan.pdf'
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

doc = TocDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=25*mm, rightMargin=25*mm,
    topMargin=20*mm, bottomMargin=20*mm,
    title='Phoenix v5.1 Bug Fix Plan',
    author='Z.ai',
    subject='Phoenix v5.1 DCA Bot - Bug Fix Plan',
)

story = []

# ═══════════════════════════════════════════════════════════════
# CHAPTER 1: Executive Summary
# ═══════════════════════════════════════════════════════════════
story.append(h1('1. Executive Summary'))
story.append(body(
    'เอกสารฉบับนี้รวบรวมแผนการแก้ไขปัญหาที่พบจากการทดสอบระบบ Phoenix v5.1 DCA Bot ในโหมด Demo Portfolio Simulation ' +
    'ผ่าน GitHub Actions จำนวน 62 รอบ การวิเคราะห์เปิดเผยบัคที่ส่งผลกระทบรุนแรง 3 ประการ ได้แก่ ปัญหาหน่วยเงินไม่ตรงกับ Exchange (THB vs USDT) ' +
    'การใช้เงินทุนสำรองผิดแหล่งที่มา และการตรวจสอบ Buy-the-Dip injection logic ที่ไม่ครบถ้วน ' +
    'นอกจากนี้ยังพบจุดที่ต้องปรับปรุงเพิ่มเติมอีก 4 ประเด็น รวมทั้งการแจ้งเตือนสถานะการซื้อขาย การเตือนยอดเงินต่ำ การแยกบัญชีเงิน DCA กับเงินสำรอง ' +
    'และระบบ Config ที่ยืดหยุ่นสำหรับการปรับค่าในอนาคต'
))
story.append(Spacer(1, 6))

# Priority matrix table
story.append(h2('1.1 Priority Matrix'))
story.append(make_table(
    ['No.', 'Issue', 'Severity', 'Files Affected', 'Phase'],
    [
        ['1', 'Currency unit mismatch (THB/USDT)', 'CRITICAL', 'strategy.py, config.py', '1'],
        ['2', 'Reserve source validation', 'CRITICAL', 'engine.py, demo_portfolio.py', '1'],
        ['3', 'Buy-the-dip injection audit', 'HIGH', 'strategy.py', '1'],
        ['4', 'Buy/sell status reporting', 'MEDIUM', 'engine.py, notifier.py', '2'],
        ['5', 'Low balance + days remaining', 'MEDIUM', 'engine.py, notifier.py', '2'],
        ['6', 'DCA vs Reserve fund separation', 'HIGH', 'state.py, engine.py, strategy.py', '2'],
        ['7', 'Config system for future tuning', 'MEDIUM', 'config.py, dca-demo.yml', '3'],
    ],
    col_widths=[25, 130, 55, 120, 35],
))
story.append(Spacer(1, 6))
story.append(body(
    'จากตารางด้านบน ประเด็นที่ 1-3 ถือเป็น Critical ที่ต้องแก้ไขก่อนเริ่มรัน Demo รอบใหม่ เนื่องจากส่งผลให้ผลลัพธ์การทดสอบ ' +
    'ไม่น่าเชื่อถือ (corrupted data) ประเด็นที่ 4-6 เป็นฟีเจอร์ที่ควรมีเพื่อความปลอดภัยในการใช้งานจริง และประเด็นที่ 7 ' +
    'เป็นการเตรียมพร้อมสำหรับการปรับค่า Parameters ต่างๆ ในอนาคตโดยไม่ต้องแก้ไข code'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 2: System Overview & Root Cause
# ═══════════════════════════════════════════════════════════════
story.append(h1('2. Architecture Overview and Root Cause Analysis'))

story.append(h2('2.1 System Architecture'))
story.append(body(
    'Phoenix v5.1 ประกอบด้วยโมดูลหลัก 5 โมดูล ที่ทำงานร่วมกันในลักษณะ Pipeline การทำงานเริ่มจาก main.py ที่ทำหน้าที่ ' +
    'เป็น Entry Point รับพารามิเตอร์จาก Command Line และ Environment Variables จากนั้นส่งต่อไปยัง engine.py ซึ่งเป็น Orchestrator ' +
    'หลัก มีหน้าที่ดึงข้อมูลราคาจาก Exchange API คำนวณ Technical Indicators และเรียกใช้ strategy.py เพื่อตัดสินใจซื้อ-ขาย ' +
    'จากนั้น demo_portfolio.py จะจำลองการซื้อขายพร้อม Slippage และบันทึกผลลัพธ์ โดย config.py ทำหน้าที่เก็บ ' +
    'ค่า Configuration ทั้งหมด และ dca-demo.yml คือ GitHub Actions Workflow ที่กำหนดเวลารันอัตโนมัติ'
))

story.append(make_table(
    ['Module', 'Responsibility', 'Key Functions'],
    [
        ['main.py', 'Entry point, CLI parsing, exchange init', 'main(), arg parsing'],
        ['config.py', 'Environment-based configuration', 'DAILY_BUDGET_THB, EXCHANGE, currency mapping'],
        ['engine.py', 'Orchestrate fetch-indicate-decide-execute', 'run_daily(), run_demo()'],
        ['strategy.py', 'Phoenix v5.1 decision logic', 'phoenix_v5_1_decision(), reserve deployment'],
        ['demo_portfolio.py', 'Paper trading, slippage, validation', 'process_demo_trade(), generate_validation_report()'],
        ['binance_client.py', 'Price/klines with fallback chain', 'get_price(), get_klines(), 4 fallback APIs'],
        ['dca-demo.yml', 'GitHub Actions workflow, cron/manual', 'Hourly demo runs, auto-commit'],
    ],
    col_widths=[80, 175, 130],
))
story.append(Spacer(1, 6))

story.append(h2('2.2 Data Flow (Run Cycle)'))
story.append(body(
    'ในแต่ละรอบของการทำงาน (ทั้ง Demo และ Live) ระบบจะดำเนินการตามลำดับดังนี้: ' +
    'เริ่มจากการตรวจสอบ Kill Switch แล้วดึงราคาปัจจุบันจาก Exchange ผ่าน binance_client.py (พร้อม Fallback Chain ' +
    'Kraken - KuCoin - CoinCap - CoinGecko ในกรณีที่ Binance ถูก Block ด้วย HTTP 451) ' +
    'จากนั้นคำนวณ Technical Indicators (SMA-200, RSI-14, MACD, MVRV, SOPR, NUPL) ' +
    'แปลงงบประมาณจาก THB เป็นสกุลเงินของ Exchange (ถ้า USDT ให้หารด้วย USD_THB_RATE) ' +
    'ส่งต่อไปยัง strategy.py เพื่อคำนวณ buy_amount, sell_amount, reserve_injection ' +
    'และสุดท้าย demo_portfolio.py จะจำลองการ execute trade พร้อม slippage และ fee บันทึกลง demo_state.json'
))

story.append(h2('2.3 Root Cause Analysis'))
story.append(body(
    'จากการวิเคราะห์ demo_state.json ที่มี 62 รอบ พบว่าปัญหาหลักเกิดจากกลไก 3 จุดที่ทำงานร่วมกัน: ' +
    'ประการแรก ค่า hardcoded ใน strategy.py (200, 900, 1200) ถูกออกแบบมาสำหรับ THB แต่ถูกใช้กับ USDT โดยตรง ' +
    'ทำให้ reserve injection มีมูลค่าสูงเกินจริง 33 เท่า (900 USDT = ~30,000 THB) ' +
    'ประการที่สอง ระบบไม่มีการแยกแยะระหว่างเงินทุน DCA (เงินที่เติมไว้รอซื้อทีละนิด) กับเงินทุนสำรอง ' +
    '(เงินที่ได้จากการขาย BTC กำไร) ทำให้ reserve deployment ใช้เงินทุนเริ่มต้นได้โดยไม่มีเงื่อนไข ' +
    'ประการที่สาม การรันทุกชั่วโมง (hourly cron) ทำให้ระบบซื้อซ้ำบ่อยเกินไป โดยเฉพาะเมื่อ MVRV < 1.5 ' +
    'ซึ่งเป็นช่วงที่ strategy กำหนดให้ deploy reserve ทุกรอบ ทำให้เงิน 10,000 USDT หมดภายใน 62 รอบ'
))

story.append(callout(
    '<b>CRITICAL:</b> Run 62 ของ Demo มีราคา BTC แทะ 2,133,416 USDT (ควรเป็น ~65,000) เกิดจาก Fallback API ' +
    'ส่งค่าผิดปกติ ทำให้ portfolio_value พุ่งขึ้นเทียม 240,053 USDT และ ROI แสดงผลเป็น +2,300% ซึ่งเป็นข้อมูลเสีย'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 3: Currency Unit Bug
# ═══════════════════════════════════════════════════════════════
story.append(h1('3. Issue #1: Currency Unit Mismatch (THB/USDT)'))

story.append(h2('3.1 Problem Description'))
story.append(body(
    'ปัญหานี้เป็นจุดเริ่มต้นของทุกอย่าง เมื่อเลือก Exchange เป็น Binance ระบบจะใช้สกุลเงิน USDT ซึ่งมีอัตราแลกเปลี่ยน ' +
    'ต่างจาก THB ประมาณ 33 เท่า (1 USDT = ~33 THB) อย่างไรก็ตาม ค่า reserve deployment caps ใน strategy.py ' +
    'lines 138-155 ถูก hardcoded ไว้เป็นตัวเลขคงที่ 200, 900, 1200 โดยไม่มีการปรับตามสกุลเงิน ' +
    'เมื่อใช้กับ USDT ค่า 900 USDT มีมูลค่าเท่ากับ ~30,000 THB ทำให้ระบบซื้อ BTC เกินงบประมาณมาก'
))

story.append(h2('3.2 Current Code (Buggy)'))
story.append(code(
    '# strategy.py lines 137-155 (CURRENT - BUGGY)\n' +
    'usable_cash = max(cash_reserve - 200.0, 0.0)  # 200 = 200 THB? 200 USDT?\n' +
    'if usable_cash > 0 and mvrv < 1.5:\n' +
    '    # ... deploy_rate logic ...\n' +
    '    injection = min(usable_cash * deploy_rate, 900.0)  # 900 THB = 27 USDT\n' +
    '    if price < realized_price * 1.05:\n' +
    '        injection = min(injection * 1.8, 1200.0)  # 1200 THB = 36 USDT'
))
story.append(body(
    'เมื่อ exchange=bitkub (THB): 900 THB เหมาะสม (ประมาณ 0.04% ของราคา BTC) ' +
    'แต่เมื่อ exchange=binance (USDT): 900 USDT = ~30,000 THB ซึ่งเท่ากับ 0.46% ของราคา BTC ' +
    'คิดเป็นการซื้อเกินไปประมาณ 11 เท่าตามสัดส่วน นี่คือสาเหตุหลักที่ทำให้เงินทุน 10,000 USDT หมดเร็วเกินไป'
))

story.append(h2('3.3 Fix Plan: Currency-Aware Reserve Caps'))
story.append(body(
    'แนวทางการแก้ไขคือทำให้ค่า reserve caps ขึ้นกับสกุลเงินของ Exchange โดยเพิ่ม Parameter ' +
    '<b>reserve_floor</b>, <b>reserve_cap_normal</b>, <b>reserve_cap_boosted</b> เข้าไปใน function signature ' +
    'ของ phoenix_v5_1_decision() โดย engine.py จะเป็นผู้คำนวณค่าเหล่านี้จาก config ก่อนส่งให้ strategy ' +
    'วิธีนี้ทำให้ strategy.py ยังคงเป็น pure function (ไม่ต้อง import config) แต่ได้ค่าที่ถูกต้อง'
))

story.append(code(
    '# strategy.py - FIXED VERSION\n' +
    'def phoenix_v5_1_decision(\n' +
    '    # ... existing params ...\n' +
    '    reserve_floor: float = 200.0,      # NEW: min cash to keep\n' +
    '    reserve_cap_normal: float = 900.0,  # NEW: max normal injection\n' +
    '    reserve_cap_boosted: float = 1200.0,# NEW: max boosted injection\n' +
    ') -> dict:\n' +
    '    usable_cash = max(cash_reserve - reserve_floor, 0.0)\n' +
    '    if usable_cash > 0 and mvrv < 1.5:\n' +
    '        # ... deploy_rate logic unchanged ...\n' +
    '        injection = min(usable_cash * deploy_rate, reserve_cap_normal)\n' +
    '        if price < realized_price * 1.05:\n' +
    '            injection = min(injection * 1.8, reserve_cap_boosted)'
))

story.append(h2('3.4 Config Changes'))
story.append(body(
    'ใน engine.py และ demo_portfolio.py จะมีการคำนวณค่า caps ก่อนเรียก strategy โดยอ้างอิงจาก ' +
    'ค่า base_budget เป็นตัวคูณ วิธีนี้ทำให้เมื่อเปลี่ยน DAILY_BUDGET_THB ค่า reserve caps จะปรับตามอัตโนมัติ ' +
    'ตัวอย่างเช่น ถ้า base_budget = 100 THB และ exchange = bitkub (THB) ค่า reserve_floor จะเป็น 2x base_budget = 200 THB ' +
    'แต่ถ้า exchange = binance (USDT) ค่า base_budget จะถูกแปลงเป็น ~3 USDT และ reserve_floor จะเป็น 6 USDT '
))

story.append(code(
    '# engine.py - compute currency-aware reserve caps\n' +
    'reserve_floor = base_budget * 2.0          # 2x daily budget\n' +
    'reserve_cap_normal = base_budget * 9.0    # 9x daily budget\n' +
    'reserve_cap_boosted = base_budget * 12.0  # 12x daily budget\n' +
    '\n' +
    'decision = strategy.phoenix_v5_1_decision(\n' +
    '    # ... existing params ...\n' +
    '    reserve_floor=reserve_floor,\n' +
    '    reserve_cap_normal=reserve_cap_normal,\n' +
    '    reserve_cap_boosted=reserve_cap_boosted,\n' +
    ')'
))

story.append(success(
    '<b>Impact:</b> เมื่อ exchange=binance (USDT) ค่า reserve_floor=6, cap=27, cap_boosted=36 USDT ' +
    'เทียบเท่ากับ THB ตามสัดส่วนอัตราแลกเปลี่ยน ทำให้การซื้อไม่เกินงบ และเหมาะสมกับทั้ง 2 Exchange'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 4: Reserve Source Validation
# ═══════════════════════════════════════════════════════════════
story.append(h1('4. Issue #2: Reserve Capital Source Validation'))

story.append(h2('4.1 Problem Description'))
story.append(body(
    'ในปัจจุบัน engine.py ส่ง <b>cash_balance</b> (ยอดเงินทั้งหมดในบัญชี) เข้าไปเป็น <b>cash_reserve</b> ' +
    'ใน strategy.py โดยตรง ทั้งที่ค่า cash_balance นี้รวมเงินทุนเริ่มต้น (DCA capital) ที่ยังไม่ได้ลงทุนด้วย ' +
    'แนวคิดเดิมของ Reserve Deployment คือ ใช้เงินที่ได้จากการขาย BTC กำไร ซื้อกลับเมื่อราคาดี ' +
    'แต่ระบบปัจจุบันไม่ได้แยกแยะว่าเงินส่วนไหนมาจากการขาย BTC ส่วนไหนเป็นเงินทุนเริ่มต้น ' +
    'ทำให้เงินทุนเริ่มต้น 10,000 USDT ถูกนำไป deploy เป็น reserve จนหมด'
))

story.append(h2('4.2 Concept: DCA Funds vs Reserve Fund'))
story.append(body(
    'เงินในระบบจะต้องแยกเป็น 2 ส่วนที่เข้าใจชัดเจน: ส่วนแรกคือ <b>DCA Waiting Funds</b> คือเงินที่ผู้ใช้เติมไว้ ' +
    'เพื่อรอซื้อ BTC ทีละนิดตามกำหนด (เช่น 100 THB/วัน) เงินส่วนนี้จะถูกใช้เป็น base_budget ในทุกรอบ ' +
    'ส่วนที่สองคือ <b>Reserve Fund from BTC Sales</b> คือเงินที่ได้จากการขาย BTC ที่สะสมออกมา ' +
    'เมื่อราคาขึ้นสูงถึงจุดขาย (MVRV > 2.5, Sell Score >= 45) เงินส่วนนี้เท่านั้นที่จะถูกนำไปใช้ ' +
    'ใน Buy-the-Dip Reserve Deployment เมื่อราคากลับลงมา'
))

story.append(h2('4.3 Fix Plan: Separate Fund Tracking'))
story.append(body(
    'เพิ่มฟิลด์ใหม่ใน state schema เพื่อแยก tracking ทั้ง 2 ส่วนอย่างชัดเจน โดยเพิ่ม <b>dca_waiting_funds</b> ' +
    'สำหรับเงินที่รอ DCA และ <b>reserve_fund</b> สำหรับเงินที่ได้จากการขาย BTC เท่านั้น ' +
    'เมื่อมีการขาย BTC สำเร็จ เงินที่ได้จากการขาย (หลังหัก fee) จะถูกเพิ่มเข้า reserve_fund ' +
    'และเมื่อ strategy ตัดสินใจ deploy reserve ก็จะดึงจาก reserve_fund เท่านั้น '
))

story.append(code(
    '# State schema changes (demo_portfolio.py + state.py)\n' +
    'DEMO_STATE_TEMPLATE = {\n' +
    '    # ... existing fields ...\n' +
    '    "dca_waiting_funds": 10000.0,   # NEW: money waiting for DCA\n' +
    '    "reserve_fund": 0.0,             # NEW: from BTC sales ONLY\n' +
    '    "total_sell_proceeds": 0.0,      # EXISTS: track total sell income\n' +
    '    "reserve_deployment_count": 0,   # NEW: how many times reserve deployed\n' +
    '}\n' +
    '# engine.py change - pass reserve_fund instead of cash_balance\n' +
    'decision = strategy.phoenix_v5_1_decision(\n' +
    '    # ... existing params ...\n' +
    '    cash_reserve=demo_state["reserve_fund"],  # CHANGED: only BTC sale proceeds\n' +
    ')'
))

story.append(info(
    '<b>Note:</b> การเปลี่ยนแปลงนี้ต้องแน่ใจว่า total cash = dca_waiting_funds + reserve_fund ' +
    'เสมอ และต้องมี assertion check ใน process_demo_trade() เพื่อป้องกัน inconsistent state'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 5: Buy-the-Dip Injection Audit
# ═══════════════════════════════════════════════════════════════
story.append(h1('5. Issue #3: Buy-the-Dip Injection Logic Audit'))

story.append(h2('5.1 Current Logic Analysis'))
story.append(body(
    'Reserve deployment ใน strategy.py ทำงานโดยตรวจสอบ 2 เงื่อนไขหลัก: ประการแรก <b>usable_cash > 0</b> ' +
    'ซึ่งหมายความว่ามีเงินสำรองเหลืออยู่ (หลังหัก reserve_floor) และประการที่สอง <b>mvrv < 1.5</b> ' +
    'ซึ่งหมายความว่า BTC อยู่ในโซนถูกหรือต่ำราคา ภายใต้เงื่อนไขเหล่านี้ ระบบจะคำนวณ deploy_rate ' +
    'ตามระดับ MVRV (0.03 - 0.25) และคูณกับ usable_cash แต่จำกัดด้วย reserve_cap'
))

story.append(h2('5.2 Issues Found'))
story.append(make_table(
    ['Issue', 'Detail', 'Impact'],
    [
        ['Hardcoded caps', '200/900/1200 ไม่ขึ้นกับสกุลเงิน', 'ซื้อเกิน 33x เมื่อใช้ USDT'],
        ['No cycle limit', 'deploy ได้ทุกรอบที่ mvrv < 1.5', 'เงินหมดเร็วเกิน'],
        ['Boost too aggressive', '1.8x multiplier เมื่อ price < realized * 1.05', 'ซื้อเพิ่มเกินในช่วงตลาดข้างเคียง'],
        ['Floor too high for USDT', '200 USDT = ~6,600 THB', 'ปิดโอกาส reserve deployment ตอนเริ่มต้น'],
    ],
    col_widths=[100, 150, 115],
))
story.append(Spacer(1, 6))

story.append(h2('5.3 Corrected Logic'))
story.append(body(
    'แผนการแก้ไขมี 3 ส่วนหลักคือ การทำให้ caps ขึ้นกับสกุลเงินผ่าน Parameter (เช่นเดียวกับประเด็นที่ 1) ' +
    'การเพิ่มเงื่อนไขที่ strategy จะตรวจสอบ reserve_fund เท่านั้น (เช่นเดียวกับประเด็นที่ 2) ' +
    'และการลด boost multiplier จาก 1.8x เป็น 1.5x เพื่อลดความก้าวร้าวในการซื้อ ' +
    'นอกจากนี้ควรเพิ่มเงื่อนไข cooldown สำหรับ reserve deployment เช่น หลัง deploy แล้วต้องรอ ' +
    'อย่างน้อย 3-5 รอบก่อนจะ deploy อีกครั้ง เพื่อป้องกันการซื้อซ้ำติดต่อกันเกินไป'
))

story.append(code(
    '# strategy.py - corrected reserve deployment\n' +
    'usable_cash = max(cash_reserve - reserve_floor, 0.0)\n' +
    'if usable_cash > 0 and mvrv < 1.5 and not np.isnan(realized_price):\n' +
    '    # deploy_rate logic unchanged (0.03 - 0.25 based on MVRV)\n' +
    '    injection = min(usable_cash * deploy_rate, reserve_cap_normal)\n' +
    '    if price < realized_price * 1.05:\n' +
    '        injection = min(injection * 1.5, reserve_cap_boosted)  # 1.5x (was 1.8x)\n' +
    '    buy_amount += injection\n' +
    '    # NEW: Reserve deployment cooldown check in engine.py\n' +
    '    # Only allow reserve deployment if reserve_cooldown == 0'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 6: Buy Status Reporting
# ═══════════════════════════════════════════════════════════════
story.append(h1('6. Issue #4: Buy/Sell Success/Failure Status Reporting'))

story.append(h2('6.1 Current Gap'))
story.append(body(
    'ในปัจจุบันระบบบันทึกข้อมูลการซื้อขายใน trade_log.json และ demo_trades.json แต่ไม่มีการระบุ ' +
    'สถานะความสำเร็จหรือความล้มเหลวของคำสั่งซื้ออย่างชัดเจน ใน Live Mode ถ้า exchange.market_buy() ' +
    'โยน Exception ระบบจะ print log และตั้ง buy_amount = 0 แต่ไม่มีการบันทึกลง state ' +
    'ว่าคำสั่งล้มเหลวเพราะอะไร (เงินไม่พอ, network error, API limit, บัญชีไม่มีสิทธิ์) ' +
    'ทำให้ผู้ใช้ไม่ทราบว่าบอททำงานปกติหรือไม่ จนกว่าจะเข้าไปดู GitHub Actions Log'
))

story.append(h2('6.2 Fix Plan'))
story.append(body(
    'เพิ่มฟิลด์ <b>last_trade_status</b> ใน state ที่บันทึกผลลัพธ์ของการซื้อขายล่าสุด โดยมีโครงสร้าง ' +
    'ประกอบด้วย side (buy/sell), amount, status (success/failed/skipped), reason, และ timestamp ' +
    'ในส่วนของ Live Mode จะจับ Exception จาก exchange.market_buy() และ market_sell() ' +
    'แยกเป็นประเภทของ error เพื่อให้ผู้ใช้ทราบสาเหตุที่ชัดเจน และส่ง notification ผ่าน Telegram ' +
    'ทันทีเมื่อเกิดการ failed หรือ skipped'
))

story.append(code(
    '# New state field\n' +
    '"last_trade_status": {\n' +
    '    "side": "buy",          # buy | sell | none\n' +
    '    "status": "success",    # success | failed | skipped\n' +
    '    "amount": 299.50,        # attempted amount\n' +
    '    "executed": 295.20,      # actual executed amount\n' +
    '    "reason": null,          # error reason if failed\n' +
    '    "timestamp": "2026-08-10T14:50:00Z"\n' +
    '}'
))

story.append(body(
    'สำหรับ Dashboard จะเพิ่มการแสดง last_trade_status ในรูปแบบ icon/badge ' +
    'เช่น สีเขียว = success, สีแดง = failed, สีเหลือง = skipped พร้อม reason สั้นๆ ' +
    'เพื่อให้เห็นภาพรวมของสถานะการทำงานของบอทได้ทันที'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 7: Low Balance Warning
# ═══════════════════════════════════════════════════════════════
story.append(h1('7. Issue #5: Low Balance Warning with Days Remaining'))

story.append(h2('7.1 Problem Description'))
story.append(body(
    'ใน Live Mode ถ้าผู้ใช้ลืมเติมเงินในบัญชี Exchange บอทจะพยายามส่งคำสั่งซื้อและล้มเหลว ' +
    'โดยไม่มีการแจ้งเตือนล่วงหน้า ผู้ใช้จะรู้ตอนที่สั่งซื้อไม่สำเร็จซึ่งอาจสายเกินไป ' +
    'โดยเฉพาะถ้าอยู่ในช่วงที่ MVRV ต่ำ (ช่วงซื้อสะสม) การพลาดการซื้อหลายวันติดต่อกัน ' +
    'อาจทำให้พลาดโอกาสซื้อ BTC ในราคาที่ดี จึงจำเป็นต้องมีระบบแจ้งเตือนล่วงหน้า'
))

story.append(h2('7.2 Days Remaining Calculation'))
story.append(body(
    'วิธีคำนวณคือ ดึงยอดเงินคงเหลือ (cash balance) หารด้วยค่าเฉลี่ยการซื้อต่อรอบ (avg_buy_per_run) ' +
    'โดยคำนวณจากยอดรวมการซื้อหารด้วยจำนวนครั้งที่ซื้อจริง ในกรณีที่ยังไม่มีข้อมูล (first few runs) ' +
    'จะใช้ base_budget เป็นตัวประมาณแทน สูตรคือ days_remaining = dca_waiting_funds / avg_buy_per_run ' +
    'โดยถ้าคำนวณโดยใช้ค่า dca_waiting_funds แทน cash_balance ทั้งหมดจะแม่นยำกว่า ' +
    'เนื่องจาก reserve_fund ไม่ใช่เงินที่จะใช้ซื้อ DCA ปกติ'
))

story.append(code(
    '# Low balance warning logic (engine.py)\n' +
    'avg_buy = (state["total_invested"] / max(state["buy_count"], 1))\n' +
    'if avg_buy < 1:\n' +
    '    avg_buy = base_budget\n' +
    'days_left = state["dca_waiting_funds"] / avg_buy\n' +
    '\n' +
    '# Warning thresholds (configurable)\n' +
    'LOW_BALANCE_WARNING_DAYS = 3   # Warn when 3 days left\n' +
    'LOW_BALANCE_CRITICAL_DAYS = 1   # Critical when 1 day left\n' +
    '\n' +
    'if days_left <= LOW_BALANCE_CRITICAL_DAYS:\n' +
    '    notifier.send_telegram(\n' +
    '        f"CRITICAL: DCA funds running out! "\n' +
    '        f"Only {days_left:.1f} days of buying remaining. "\n' +
    '        f"Please top up your account."\n' +
    '    )\n' +
    'elif days_left <= LOW_BALANCE_WARNING_DAYS:\n' +
    '    notifier.send_telegram(\n' +
    '        f"WARNING: Low balance. "\n' +
    '        f"~{days_left:.1f} days of DCA buying remaining."\n' +
    '    )'
))

story.append(body(
    'สำหรับ Dashboard ควรแสดง days_remaining เป็นตัวเลขพร้อมสีที่บ่งบอกระดับ (เขียว/เหลือง/แดง) ' +
    'และใน Telegram notification สามารถส่งเป็น scheduled reminder ทุกสัปดาห์เพื่อเตือนผู้ใช้ '
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 8: DCA vs Reserve Separation
# ═══════════════════════════════════════════════════════════════
story.append(h1('8. Issue #6: DCA Funds vs Reserve Fund Separation'))

story.append(h2('8.1 Conceptual Model'))
story.append(body(
    'การแยกเงินทั้ง 2 ประเภทนี้เป็นสิ่งสำคัญที่สุดในการทำให้ระบบทำงานถูกต้อง ในระบบ DCA ที่ดี ' +
    'เงินทุนจะต้องถูกจัดการแยกกันอย่างชัดเจน เพื่อป้องกันการใช้เงินผิดวัตถุประสงค์ ' +
    'เงิน DCA Waiting Funds คือเงินที่ผู้ใช้เติมเว้นเพื่อรอซื้อ BTC ทีละนิดตามรอบ ' +
    'เงินส่วนนี้จะถูกใช้เป็น base_budget ในทุกรอบ และเมื่อหมด บอทจะหยุดซื้อ DCA ' +
    'แต่ยังคงทำงานด้านอื่นได้ (เช่น ขาย BTC เมื่อถึงจุดขาย)'
))
story.append(body(
    'ส่วน Reserve Fund คือเงินที่ได้จากการขาย BTC ทำกำไร ซึ่งจะถูกนำมาใช้ซื้อ BTC กลับ ' +
    'เฉพาะเมื่อราคาดี (Buy-the-Dip) โดยมีเงื่อนไขที่เข้มงวดกว่า DCA ปกติ คือต้อง MVRV < 1.5 ' +
    'และต้องผ่านการคำนวณ deploy_rate ตามระดับความต่ำของราคา ' +
    'การแยกสองส่วนนี้ทำให้ผู้ใช้มั่นใจได้ว่าเงินทุนเริ่มต้นจะไม่ถูกนำไปใช้ในทางที่ผิด'
))

story.append(h2('8.2 State Schema Changes'))
story.append(make_table(
    ['Field', 'Type', 'Description', 'Initial Value'],
    [
        ['dca_waiting_funds', 'float', 'Money allocated for periodic DCA buys', 'initial_cash'],
        ['reserve_fund', 'float', 'Money from BTC sales only', '0.0'],
        ['total_sell_proceeds', 'float', 'Total received from all BTC sells', '0.0'],
        ['reserve_deployment_count', 'int', 'Number of reserve deployments', '0'],
        ['reserve_cooldown', 'int', 'Cooldown runs between reserve deploys', '0'],
    ],
    col_widths=[105, 40, 160, 60],
))
story.append(Spacer(1, 6))

story.append(h2('8.3 Fund Flow Rules'))
story.append(body(
    '<b>On Buy (DCA):</b> หักเงินจาก dca_waiting_funds ลดลงตาม buy_amount ' +
    'หาก buy_amount มากกว่า dca_waiting_funds ให้ใช้เงินที่มีอยู่ทั้งหมด ' +
    'และถ้า dca_waiting_funds < min_buy ให้ข้ามการซื้อ DCA แต่ยังคงตรวจสอบ reserve deployment'
))
story.append(body(
    '<b>On Reserve Deploy:</b> หักเงินจาก reserve_fund เท่านั้น ' +
    'ตั้ง reserve_cooldown = 5 (รอ 5 รอบก่อน deploy อีก) ' +
    'บันทึก reserve_deployment_count และ reserve_injection ใน trade log'
))
story.append(body(
    '<b>On Sell:</b> เพิ่ม net_proceeds (หลังหัก fee) เข้า reserve_fund ' +
    'อัพเดท total_sell_proceeds และแจ้งเตือนผ่าน Telegram ว่ามีเงินเข้า reserve fund'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 9: Config System
# ═══════════════════════════════════════════════════════════════
story.append(h1('9. Issue #7: Config System for Future Tuning'))

story.append(h2('9.1 Current Limitations'))
story.append(body(
    'ปัจจุบัน config.py มี Parameter จำนวนน้อยและไม่ครอบคลุม ค่าต่างๆ ถูก hardcoded ใน strategy.py ' +
    'เช่น reserve caps (200/900/1200), deploy_rate range (0.03-0.25), boost multiplier (1.8) ' +
    'และ minimum buy amounts ทำให้การปรับค่าต้องแก้ไข code โดยตรง ซึ่งเสี่ยงต่อความผิดพลาด ' +
    'และทำให้การทดสอบหลายๆ สถานการณ์ทำได้ยาก ดังนั้นจึงควรสร้าง Config System ' +
    'ที่ครอบคลุม Parameter สำคัญทั้งหมด โดยรองรับการตั้งค่าผ่าน Environment Variables '
))

story.append(h2('9.2 New Configurable Parameters'))
story.append(make_table(
    ['Env Variable', 'Default', 'Description'],
    [
        ['DAILY_BUDGET_THB', '100', 'DCA amount per run (THB base, converted for USDT)'],
        ['MAX_BUY_PER_RUN_MULTIPLIER', '10.0', 'Max buy = budget x this (caps total buy per run)'],
        ['MAX_BUY_PER_DAY_MULTIPLIER', '15.0', 'Max total buy per day (multiple runs)'],
        ['RESERVE_FLOOR_MULTIPLIER', '2.0', 'Reserve floor = budget x this'],
        ['RESERVE_CAP_NORMAL_MULTIPLIER', '9.0', 'Normal reserve cap = budget x this'],
        ['RESERVE_CAP_BOOSTED_MULTIPLIER', '12.0', 'Boosted reserve cap = budget x this'],
        ['RESERVE_BOOST_MULTIPLIER', '1.5', 'Boost multiplier when price < realized x 1.05'],
        ['RESERVE_COOLDOWN_RUNS', '5', 'Min runs between reserve deployments'],
        ['LOW_BALANCE_WARNING_DAYS', '3', 'Warn when DCA funds <= this many days'],
        ['LOW_BALANCE_CRITICAL_DAYS', '1', 'Critical alert when DCA funds <= this many days'],
        ['MIN_BUY_USDT', '10.0', 'Binance minimum order size (USDT)'],
        ['MIN_BUY_THB', '100.0', 'Bitkub minimum order size (THB)'],
    ],
    col_widths=[130, 45, 205],
))
story.append(Spacer(1, 6))

story.append(h2('9.3 Implementation Approach'))
story.append(body(
    'ระบบ Config จะใช้ Pattern เดียวกับที่มีอยู่แล้วใน config.py คืออ่านค่าจาก Environment Variables ' +
    'พร้อม default values ที่เหมาะสม โดยทุกค่าจะถูกแปลงเป็นสกุลเงินของ Exchange โดยอัตโนมัติ ' +
    'เมื่อ engine.py ทำงาน โดยค่าที่เป็น THB base (เช่น DAILY_BUDGET_THB) จะถูกหารด้วย USD_THB_RATE ' +
    'เมื่อ exchange=binance ส่วนค่าที่เป็น Multiplier (เช่น RESERVE_CAP_NORMAL_MULTIPLIER) ' +
    'จะคูณกับ base_budget ที่แปลงแล้ว ทำให้ได้ค่าสุดท้ายที่ถูกต้องตามสกุลเงินโดยอัตโนมัติ'
))

story.append(code(
    '# config.py additions\n' +
    'RESERVE_FLOOR_MULT = float(os.environ.get(\n' +
    '    "RESERVE_FLOOR_MULTIPLIER", "2.0"))\n' +
    'RESERVE_CAP_NORMAL_MULT = float(os.environ.get(\n' +
    '    "RESERVE_CAP_NORMAL_MULTIPLIER", "9.0"))\n' +
    'RESERVE_CAP_BOOSTED_MULT = float(os.environ.get(\n' +
    '    "RESERVE_CAP_BOOSTED_MULTIPLIER", "12.0"))\n' +
    'RESERVE_BOOST_MULT = float(os.environ.get(\n' +
    '    "RESERVE_BOOST_MULTIPLIER", "1.5"))\n' +
    'RESERVE_COOLDOWN = int(os.environ.get(\n' +
    '    "RESERVE_COOLDOWN_RUNS", "5"))\n' +
    'LOW_BALANCE_WARN_DAYS = int(os.environ.get(\n' +
    '    "LOW_BALANCE_WARNING_DAYS", "3"))\n' +
    'LOW_BALANCE_CRIT_DAYS = int(os.environ.get(\n' +
    '    "LOW_BALANCE_CRITICAL_DAYS", "1"))'
))

story.append(body(
    'ระบบนี้ช่วยให้ในอนาคตสามารถทดสอบ Scenario ต่างๆ ได้ง่าย เช่น การเพิ่ม DAILY_BUDGET_THB ' +
    'เป็น 200 หรือ 500 โดยไม่ต้องแก้ไข code หรือการปรับ RESERVE_CAP_NORMAL_MULTIPLIER ' +
    'เพื่อทดสอบผลกระทบของการเพิ่ม/ลด reserve deployment ผ่าน Demo Portfolio ก่อนนำไปใช้จริง'
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 10: Implementation Roadmap
# ═══════════════════════════════════════════════════════════════
story.append(h1('10. Implementation Roadmap'))

story.append(h2('10.1 Phase 1: Critical Bug Fixes (Priority: Immediate)'))
story.append(body(
    'Phase 1 มุ่งเน้นแก้ไขปัญหา Critical 3 ประการที่ทำให้ผลลัพธ์ Demo ไม่น่าเชื่อถือ ' +
    'ต้องดำเนินการก่อนรัน Demo รอบใหม่ทุกประการ เนื่องจากถ้าแก้ไม่ครบ ข้อมูลจะยังเสียอยู่ '
))

story.append(make_table(
    ['Step', 'Task', 'Files', 'Est. Time'],
    [
        ['1.1', 'Add reserve_floor/cap params to strategy()', 'strategy.py', '15 min'],
        ['1.2', 'Compute currency-aware caps in engine', 'engine.py', '20 min'],
        ['1.3', 'Compute currency-aware caps in demo', 'demo_portfolio.py', '20 min'],
        ['1.4', 'Add dca_waiting_funds + reserve_fund to state', 'demo_portfolio.py, state.py', '30 min'],
        ['1.5', 'Change cash_reserve to use reserve_fund only', 'engine.py (run_demo)', '15 min'],
        ['1.6', 'Add fund flow logic (buy/sell/deploy)', 'demo_portfolio.py', '30 min'],
        ['1.7', 'Reset demo_state.json + demo_trades.json', 'manual / --reset', '5 min'],
        ['1.8', 'Test with manual trigger, verify amounts', 'dca-demo.yml', '20 min'],
    ],
    col_widths=[30, 190, 130, 45],
))
story.append(Spacer(1, 6))

story.append(h2('10.2 Phase 2: New Features (Priority: High)'))
story.append(body(
    'Phase 2 เป็นการเพิ่มฟีเจอร์ที่จำเป็นสำหรับการใช้งานจริง (Go-Live) ' +
    'แต่ไม่ได้ block การทดสอบ Demo รอบใหม่ สามารถทำพร้อมกันกับการรัน Demo ได้ '
))

story.append(make_table(
    ['Step', 'Task', 'Files', 'Est. Time'],
    [
        ['2.1', 'Add last_trade_status to state schema', 'state.py, demo_portfolio.py', '20 min'],
        ['2.2', 'Capture buy/sell errors with reason', 'engine.py', '30 min'],
        ['2.3', 'Add trade status to Telegram notification', 'notifier.py', '15 min'],
        ['2.4', 'Calculate days_remaining from avg buy', 'engine.py', '15 min'],
        ['2.5', 'Add low balance warning to Telegram', 'notifier.py, engine.py', '20 min'],
        ['2.6', 'Display trade status + days left on dashboard', 'generate_dashboard.py', '30 min'],
    ],
    col_widths=[30, 200, 130, 45],
))
story.append(Spacer(1, 6))

story.append(h2('10.3 Phase 3: Config System (Priority: Medium)'))
story.append(body(
    'Phase 3 เป็นการปรับโครงสร้าง Config ให้รองรับการปรับค่า Parameters ต่างๆ ' +
    'ผ่าน Environment Variables โดยไม่ต้องแก้ไข code ทำให้การทดสอบหลายๆ Scenario ' +
    'และการปรับค่าในอนาคตทำได้สะดวกและปลอดภัยกว่า'
))

story.append(make_table(
    ['Step', 'Task', 'Files', 'Est. Time'],
    [
        ['3.1', 'Add new config params to config.py', 'config.py', '20 min'],
        ['3.2', 'Use config multipliers in engine budget calc', 'engine.py', '15 min'],
        ['3.3', 'Use config multipliers in demo budget calc', 'demo_portfolio.py', '15 min'],
        ['3.4', 'Add reserve_cooldown to state and strategy', 'strategy.py, engine.py', '20 min'],
        ['3.5', 'Update dca-demo.yml with new env vars', 'dca-demo.yml', '10 min'],
        ['3.6', 'Document all config params in README', 'README.md', '15 min'],
    ],
    col_widths=[30, 200, 130, 45],
))

# ═══════════════════════════════════════════════════════════════
# CHAPTER 11: Summary and Notes
# ═══════════════════════════════════════════════════════════════
story.append(h1('11. Summary and Recommendations'))

story.append(h2('11.1 Total Impact'))
story.append(body(
    'การแก้ไขทั้ง 7 ประเด็นนี้จะส่งผลให้ระบบ Phoenix v5.1 มีความน่าเชื่อถือสูงขึ้นอย่างมาก ' +
    'โดยเฉพาะการแก้ไขปัญหาหน่วยเงิน (Issue #1) และการแยกเงินทุนสำรอง (Issue #2) ' +
    'จะทำให้ผลลัพธ์ Demo สะท้อนพฤติกรรมจริงของ strategy ได้แม่นยำมากขึ้น ' +
    'การเพิ่มระบบแจ้งเตือน (Issue #4, #5) จะช่วยให้ผู้ใช้สามารถดูแลบอทในช่วง Live Mode ได้สบายขึ้น ' +
    'และระบบ Config (Issue #7) จะเปิดโอกาสให้ทดสอบและปรับแต่ง Parameters ได้หลากหลายมากขึ้น'
))

story.append(h2('11.2 Critical Actions Before Next Demo Run'))
story.append(body(
    '<b>1. Reset Demo State:</b> ต้องรัน --reset เพื่อเริ่ม demo_state.json และ demo_trades.json ใหม่ ' +
    'เนื่องจากข้อมูลเดิม 62 รอบมีข้อมูลเสีย (mixed THB/USDT prices, corrupted ROI) ' +
    'ไม่สามารถใช้ต่อได้แม้จะแก้ไข code แล้วก็ตาม เพราะ history ที่บันทึกไว้มี price ทั้ง THB และ USDT ปนกัน '
))
story.append(body(
    '<b>2. Verify Exchange Consistency:</b> ตรวจสอบว่า cron run และ manual trigger ใช้ exchange ' +
    'เดียวกันเสมอ โดยเพิ่ม validation ใน demo_portfolio.py ที่ตรวจสอบว่า exchange ' +
    'และ currency ใน demo_state.json ตรงกับที่ส่งเข้ามาจาก command line ' +
    'ถ้าไม่ตรงให้ skip และแจ้งเตือนผ่าน log'
))
story.append(body(
    '<b>3. Price Sanity Check:</b> เพิ่ม validation ใน engine.py ที่ตรวจสอบราคาที่ดึงมาว่า ' +
    'อยู่ในช่วงที่เป็นไปได้ (เช่น BTC ไม่น้อยกว่า 10,000 หรือมากกว่า 500,000 USDT) ' +
    'ถ้าราคาผิดปกติให้ skip รอบนั้นและแจ้งเตือน ปัญหา run 62 ที่ได้ราคา 2.1M USDT ' +
    'จะถูกป้องกันโดย validation นี้'
))

story.append(h2('11.3 Monitoring After Deployment'))
story.append(body(
    'หลังจาก deploy การแก้ไขแล้ว ควร monitor อย่างน้อย 14 รอบ (ประมาณ 2 สัปดาห์ในโหมด hourly) ' +
    'โดยตรวจสอบสิ่งต่อไปนี้: ยอดซื้อต่อรอบไม่เกิน base_budget + reserve_injection ที่คาดไว้ ' +
    'dca_waiting_funds ลดลงอย่างสม่ำเสมอตาม base_budget reserve_fund เพิ่มขึ้นเฉพาะเมื่อมีการขาย BTC ' +
    'และ days_remaining ลดลงตามที่คำนวณไว้ ถ้าพบ anomaly ให้ตรวจสอบ log และปรับ config '
))

# ── Build with TOC ──
toc = TableOfContents()
toc.levelStyles = [toc_level0, toc_level1]

# Insert TOC after a placeholder
story.insert(0, toc)
story.insert(1, PageBreak())

doc.multiBuild(story)
print(f'PDF generated: {OUTPUT}')
