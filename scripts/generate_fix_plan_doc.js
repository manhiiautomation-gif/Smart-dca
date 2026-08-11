const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Header, Footer,
  AlignmentType, HeadingLevel, PageNumber, PageBreak,
  TableOfContents, Table, TableRow, TableCell,
  BorderStyle, ShadingType, WidthType, TableLayoutType,
  SectionType, NumberFormat,
} = require("docx");

// Palette: Lapis Tech
const P = {
  primary: "#1A1F36",
  accent: "#667eea",
  surface: "#F8F9FF",
  cover: {
    bg: "#1A1F36",
    titleColor: "#FFFFFF",
    subtitleColor: "#C8CCE0",
    metaColor: "#9BA0B8",
    footerColor: "#6B7094",
    accent: "#667eea",
  },
};
const c = (hex) => hex.replace("#", "");
const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const pgSize = { width: 11906, height: 16838, orientation: 0 };
const pgMargin = { top: 1440, bottom: 1440, left: 1701, right: 1417 };

function calcTitleLayout(title, maxW, pref = 40, min = 24) {
  for (let pt = pref; pt >= min; pt -= 2) {
    const cpl = Math.floor(maxW / (pt * 11));
    const words = title.split(/(\s+)/);
    const lines = []; let cur = "";
    for (const w of words) {
      if (cur.length + w.length <= cpl) { cur += w; }
      else if (!cur) lines.push(w);
      else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    if (lines.length <= 3) return { titlePt: pt, titleLines: lines };
  }
  return { titlePt: min, titleLines: [title] };
}

function calcCoverSpacing(p) {
  const titleH = p.titleLineCount * (p.titlePt * 23 + 200);
  const subH = p.hasSubtitle ? (15 * 23 + 600) : 0;
  const elH = p.hasEnglishLabel ? (9 * 23 + 500) : 0;
  const metaH = p.metaLineCount * 350;
  const fixedH = p.fixedHeight || 400;
  const contentH = titleH + subH + elH + metaH + fixedH;
  const avail = Math.max(15638 - contentH, 2000);
  const topS = Math.min(Math.floor(avail * 0.25), 4500);
  const midS = Math.min(Math.floor(avail * 0.10), 1200);
  const botS = Math.min(Math.max(avail - topS - midS, 400), 4500);
  return { topSpacing: topS, midSpacing: midS, bottomSpacing: botS };
}

function h(text, level = HeadingLevel.HEADING_1) {
  const sizes = { [HeadingLevel.HEADING_1]: 32, [HeadingLevel.HEADING_2]: 28, [HeadingLevel.HEADING_3]: 24 };
  return new Paragraph({
    heading: level,
    spacing: { before: level === HeadingLevel.HEADING_1 ? 360 : 240, after: 120 },
    children: [new TextRun({ text, bold: true, size: sizes[level] || 24, color: "000000", font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}

function p(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: 480 }, spacing: { line: 312 },
    children: [new TextRun({ text, size: 24, color: "000000", font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}

function pni(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { line: 312 },
    children: [new TextRun({ text, size: 24, color: "000000", font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}

function tbl(headers, rows) {
  const hCells = headers.map(hd => new TableCell({
    width: { size: Math.floor(100 / headers.length), type: WidthType.PERCENTAGE },
    shading: { type: ShadingType.CLEAR, fill: c(P.primary) },
    borders: { top: NB, bottom: { style: BorderStyle.SINGLE, size: 4, color: c(P.accent) }, left: NB, right: NB },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
      children: [new TextRun({ text: hd, bold: true, size: 20, color: "FFFFFF", font: { ascii: "Calibri", eastAsia: "SimHei" } })] })],
  }));
  const dRows = rows.map((row, ri) => new TableRow({ children: row.map(cell => new TableCell({
    width: { size: Math.floor(100 / headers.length), type: WidthType.PERCENTAGE },
    shading: ri % 2 === 1 ? { type: ShadingType.CLEAR, fill: c(P.surface) } : undefined,
    borders: { top: NB, bottom: NB, left: NB, right: NB },
    children: [new Paragraph({ spacing: { before: 40, after: 40 },
      children: [new TextRun({ text: String(cell), size: 20, color: "000000", font: { ascii: "Calibri", eastAsia: "SimSun" } })] })],
  })) }));
  return new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, layout: TableLayoutType.FIXED, borders: allNoBorders, rows: [new TableRow({ tableHeader: true, children: hCells }), ...dRows] });
}

function buildCover(config) {
  const PC = config.palette;
  const padL = 1200, padR = 800;
  const availW = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availW, 36, 24);
  const tSize = titlePt * 2;
  const sp = calcCoverSpacing({ titleLineCount: titleLines.length, titlePt, hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel, metaLineCount: (config.metaLines || []).length, fixedHeight: 400 });
  const accentL = { style: BorderStyle.SINGLE, size: 8, color: PC.accent, space: 12 };
  const ch = [];
  ch.push(new Paragraph({ spacing: { before: sp.topSpacing } }));
  if (config.englishLabel) {
    ch.push(new Paragraph({ indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: PC.accent, space: 8 } },
      children: [new TextRun({ text: config.englishLabel.split("").join("  "), size: 18, color: PC.accent, font: { ascii: "Calibri", eastAsia: "SimHei" }, characterSpacing: 40 })] }));
  }
  for (let i = 0; i < titleLines.length; i++) {
    ch.push(new Paragraph({
      indent: { left: padL, right: padR },
      spacing: { after: i < titleLines.length - 1 ? 80 : 300, line: titlePt * 23, lineRule: "atLeast" },
      border: i === 0 ? { left: accentL } : undefined,
      children: [new TextRun({ text: titleLines[i], size: tSize, bold: true, color: PC.titleColor, font: { ascii: "Calibri", eastAsia: "SimHei" } })],
    }));
  }
  if (config.subtitle) {
    ch.push(new Paragraph({ indent: { left: padL, right: padR }, spacing: { after: 600 },
      children: [new TextRun({ text: config.subtitle, size: 26, color: PC.subtitleColor, font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" } })] }));
  }
  ch.push(new Paragraph({ spacing: { before: sp.midSpacing } }));
  (config.metaLines || []).forEach(line => {
    ch.push(new Paragraph({ indent: { left: padL, right: padR }, spacing: { after: 200 },
      children: [new TextRun({ text: line, size: 22, color: PC.metaColor, font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" } })] }));
  });
  ch.push(new Paragraph({ spacing: { before: sp.bottomSpacing } }));
  if (config.footerLeft || config.footerRight) {
    ch.push(new Paragraph({ indent: { left: padL, right: padR },
      border: { top: { style: BorderStyle.SINGLE, size: 4, color: PC.accent, space: 8 } }, spacing: { before: 200 },
      children: [
        ...(config.footerLeft ? [new TextRun({ text: config.footerLeft, size: 18, color: PC.footerColor, font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" } })] : []),
        ...(config.footerRight ? [new TextRun({ text: "    " + config.footerRight, size: 18, color: PC.footerColor, font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" } })] : []),
      ],
    }));
  }
  return [new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, layout: TableLayoutType.FIXED, borders: allNoBorders,
    rows: [new TableRow({ height: { value: 16838, rule: "exact" }, children: [new TableCell({
      shading: { type: ShadingType.CLEAR, fill: PC.bg }, borders: noBorders, verticalAlign: "top",
      margins: { top: 0, bottom: 0, left: 0, right: 0 }, children: ch,
    })] })] })];
}

async function main() {
  const today = "2026-08-11";
  const doc = new Document({
    styles: {
      default: { document: { run: { font: { ascii: "Times New Roman", eastAsia: "SimSun" }, size: 24, color: "000000" }, paragraph: { spacing: { line: 312 } } } },
      heading1: { run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 32, bold: true, color: "000000" }, paragraph: { spacing: { before: 360, after: 120, line: 312 } } },
      heading2: { run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 28, bold: true, color: "000000" }, paragraph: { spacing: { before: 240, after: 120, line: 312 } } },
      heading3: { run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 24, bold: true, color: "000000" }, paragraph: { spacing: { before: 200, after: 100, line: 312 } } },
    },
    sections: [
      // Cover
      { properties: { page: { size: pgSize, margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
        children: buildCover({
          title: "Phoenix v5.1 Demo Fix Plan",
          englishLabel: "FIX PLAN  &  IMPROVEMENT  ROUND  2",
          subtitle: "Bug Analysis, System Design, and Config",
          metaLines: [
            `Date: ${today}`,
            "Project: Phoenix v5.1 Live DCA Bot",
            "Scope: 7 Issues (3 Bugs + 4 Features)",
          ],
          palette: P.cover,
          footerLeft: "Phoenix DCA Bot Project",
          footerRight: today,
        }),
      },
      // TOC (Roman)
      { properties: { type: SectionType.NEXT_PAGE, page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN } } },
        footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" })] })] }) },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 480, after: 360 }, children: [new TextRun({ text: "\u0e2a\u0e32\u0e23\u0e1a\u0e31\u0e0d", bold: true, size: 32, font: { eastAsia: "SimHei", ascii: "Times New Roman" } })] }),
          new TableOfContents("TOC", { hyperlink: true, headingStyleRange: "1-3" }),
          new Paragraph({ spacing: { before: 200 }, children: [new TextRun({ text: "Note: Right-click the Table of Contents and select \"Update Field\" to refresh page numbers.", italics: true, size: 18, color: "888888" })] }),
          new Paragraph({ children: [new PageBreak()] }),
        ],
      },
      // Body (Arabic)
      { properties: { type: SectionType.NEXT_PAGE, page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
        headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Phoenix v5.1 Fix Plan", size: 18, color: "808080", font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" } })] })] }) },
        footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" })] })] }) },
        children: [
          // 1. Executive Summary
          h("\u0e2a\u0e23\u0e38\u0e1b\u0e1c\u0e25\u0e40\u0e1a\u0e37\u0e49\u0e2d\u0e07\u0e15\u0e49\u0e19 (Executive Summary)"),
          p("\u0e40\u0e2d\u0e01\u0e2a\u0e32\u0e23\u0e19\u0e35\u0e49\u0e23\u0e27\u0e1a\u0e23\u0e27\u0e21\u0e01\u0e32\u0e23\u0e27\u0e34\u0e40\u0e04\u0e23\u0e32\u0e30\u0e2b\u0e4c\u0e41\u0e25\u0e30\u0e41\u0e1c\u0e19\u0e01\u0e32\u0e23\u0e0b\u0e48\u0e2d\u0e21 7 \u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19\u0e2a\u0e33\u0e04\u0e31\u0e0d\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a Phoenix v5.1 Live Bot \u0e17\u0e35\u0e48\u0e1e\u0e1a\u0e08\u0e32\u0e01\u0e01\u0e32\u0e23\u0e17\u0e14\u0e2a\u0e2d\u0e1a Demo Portfolio 62 runs (6-10 \u0e2a.\u0e04. 2026) \u0e1c\u0e48\u0e32\u0e19 GitHub Actions \u0e42\u0e14\u0e22\u0e43\u0e0a\u0e49 Binance \u0e40\u0e1b\u0e47\u0e19 Exchange \u0e2b\u0e25\u0e31\u0e01 (USDT) \u0e01\u0e32\u0e23\u0e17\u0e14\u0e2a\u0e2d\u0e1a\u0e40\u0e1c\u0e22\u0e1b\u0e31\u0e0d\u0e2b\u0e32\u0e22\u0e23\u0e30\u0e1a\u0e1a\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07 3 \u0e02\u0e49\u0e2d \u0e42\u0e14\u0e22\u0e2a\u0e33\u0e04\u0e31\u0e0d\u0e04\u0e37\u0e2d\u0e01\u0e32\u0e23\u0e43\u0e0a\u0e49\u0e2b\u0e19\u0e48\u0e27\u0e22\u0e40\u0e07\u0e34\u0e19\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14 (THB vs USDT) \u0e43\u0e19 reserve deployment \u0e17\u0e33\u0e43\u0e2b\u0e49\u0e1a\u0e2d\u0e17\u0e0b\u0e37\u0e49\u0e2d BTC \u0e40\u0e01\u0e34\u0e19\u0e04\u0e27\u0e32\u0e21\u0e40\u0e2b\u0e21\u0e32\u0e30\u0e2a\u0e21 33 \u0e40\u0e17\u0e48\u0e32 \u0e41\u0e25\u0e30 cash \u0e2b\u0e21\u0e14\u0e25\u0e07 0 \u0e20\u0e32\u0e22\u0e43\u0e19 62 runs"),
          p("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19\u0e2b\u0e25\u0e31\u0e01\u0e04\u0e37\u0e2d 3 Critical Bugs: (1) \u0e2b\u0e19\u0e48\u0e27\u0e22\u0e40\u0e07\u0e34\u0e19\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14 THB/USDT \u0e43\u0e19 strategy.py reserve deployment \u0e2a\u0e48\u0e07\u0e1c\u0e25\u0e43\u0e2b\u0e49\u0e0b\u0e37\u0e49\u0e2d\u0e40\u0e01\u0e34\u0e19 33x \u0e40\u0e17\u0e48\u0e32 (2) \u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25 THB/USDT \u0e1b\u0e19\u0e01\u0e31\u0e19\u0e43\u0e19 demo history \u0e17\u0e33\u0e25\u0e32\u0e22\u0e20\u0e32\u0e1e portfolio \u0e41\u0e17\u0e49 (3) exchange \u0e40\u0e1b\u0e25\u0e35\u0e48\u0e22\u0e19 mid-run \u0e42\u0e14\u0e22\u0e44\u0e21\u0e48\u0e21\u0e35 validation \u0e1b\u0e23\u0e30\u0e01\u0e2d\u0e1a 4 Feature Improvements: \u0e01\u0e32\u0e23\u0e41\u0e22\u0e01 DCA parameters \u0e40\u0e1b\u0e47\u0e19 config, \u0e41\u0e22\u0e01\u0e40\u0e07\u0e34\u0e19 DCA \u0e01\u0e31\u0e1a Reserve, buy-the-dip audit, \u0e23\u0e32\u0e22\u0e07\u0e2d\u0e32\u0e19, \u0e41\u0e25\u0e30 low-balance warning"),

          // 2. Background
          h("\u0e1e\u0e37\u0e49\u0e19\u0e2b\u0e25\u0e31\u0e01\u0e41\u0e25\u0e30\u0e1b\u0e31\u0e0d\u0e2b\u0e32\u0e22\u0e23\u0e30\u0e1a\u0e1a"),
          h("\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23 Demo Portfolio", HeadingLevel.HEADING_2),
          p("Phoenix v5.1 Live Bot \u0e16\u0e39\u0e01\u0e2d\u0e2d\u0e01\u0e41\u0e1a\u0e1a Demo Portfolio \u0e1c\u0e48\u0e32\u0e19 GitHub Actions \u0e42\u0e14\u0e22\u0e43\u0e0a\u0e49 Binance \u0e40\u0e1b\u0e47\u0e19 exchange \u0e2b\u0e25\u0e31\u0e01 (currency=USDT) \u0e42\u0e14\u0e22\u0e40\u0e23\u0e34\u0e48\u0e21\u0e15\u0e49\u0e19\u0e14\u0e49\u0e27\u0e22\u0e40\u0e07\u0e34\u0e19 10,000 USDT \u0e43\u0e19\u0e27\u0e31\u0e19\u0e17\u0e35\u0e48 6 \u0e2a.\u0e04. 2026 \u0e2b\u0e25\u0e31\u0e07\u0e08\u0e32\u0e01 62 runs \u0e1e\u0e1a\u0e27\u0e48\u0e32 portfolio \u0e41\u0e2a\u0e14\u0e07\u0e1c\u0e25\u0e25\u0e1a\u0e41\u0e1a\u0e1a\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07: cash=0, peak_value=240,053 (\u0e04\u0e27\u0e23\u0e40\u0e1b\u0e47\u0e19 ~10,000), max_drawdown=24.8% (\u0e04\u0e27\u0e23\u0e40\u0e1b\u0e47\u0e19 -0.1%) \u0e2a\u0e48\u0e27\u0e19\u0e17\u0e35\u0e48\u0e40\u0e2b\u0e25\u0e37\u0e2d\u0e44\u0e1b\u0e04\u0e37\u0e2d\u0e04\u0e48\u0e32\u0e18\u0e23\u0e23\u0e21\u0e40\u0e07\u0e34\u0e19\u0e41\u0e25\u0e30 fee \u0e08\u0e32\u0e01\u0e01\u0e32\u0e23\u0e0b\u0e37\u0e49\u0e2d\u0e40\u0e01\u0e34\u0e19\u0e08\u0e23\u0e34\u0e07"),
          h("\u0e2a\u0e32\u0e40\u0e2b\u0e15\u0e38\u0e1b\u0e31\u0e0d\u0e2b\u0e32\u0e22\u0e17\u0e35\u0e48\u0e1e\u0e1a", HeadingLevel.HEADING_2),
          p("\u0e01\u0e32\u0e23\u0e27\u0e34\u0e40\u0e04\u0e23\u0e32\u0e30\u0e2b\u0e4c demo_state.json \u0e1e\u0e1a\u0e2b\u0e25\u0e31\u0e01\u0e10\u0e32\u0e19 3 \u0e1b\u0e23\u0e30\u0e01\u0e32\u0e23 \u0e14\u0e31\u0e07\u0e19\u0e35\u0e49: (1) History entries \u0e41\u0e23\u0e01\u0e21\u0e35 price \u0e23\u0e32\u0e27\u0e21 2,143,446 \u0e41\u0e25\u0e30 2,127,959 (THB \u0e08\u0e32\u0e01 Bitkub) \u0e41\u0e15\u0e48\u0e15\u0e31\u0e27\u0e15\u0e48\u0e2d\u0e21\u0e21\u0e35 price ~64,980 (USDT \u0e08\u0e32\u0e01 Binance) \u0e2b\u0e21\u0e32\u0e22\u0e16\u0e36\u0e07 exchange \u0e40\u0e1b\u0e25\u0e35\u0e48\u0e22\u0e19 Bitkub/THB \u0e44\u0e1b Binance/USDT \u0e42\u0e14\u0e22\u0e44\u0e21\u0e48 reset state (2) peak_value=240,053 \u0e41\u0e15\u0e48\u0e04\u0e27\u0e23\u0e40\u0e1b\u0e47\u0e19 ~10,000 \u0e40\u0e19\u0e37\u0e48\u0e2d\u0e07\u0e08\u0e32\u0e01 THB price \u0e1b\u0e19 \u0e43\u0e19 USDT history (3) cash=0.0 \u0e2b\u0e21\u0e14\u0e25\u0e07 \u0e40\u0e1e\u0e23\u0e32\u0e30 reserve deployment \u0e43\u0e0a\u0e49 threshold 200/900/1200 (THB) \u0e41\u0e15\u0e48 currency \u0e40\u0e1b\u0e47\u0e19 USDT \u0e17\u0e33\u0e43\u0e2b\u0e49 deploy \u0e40\u0e07\u0e34\u0e19\u0e40\u0e01\u0e34\u0e19 33x"),
          pni("\u0e15\u0e32\u0e23\u0e32\u0e07\u0e2a\u0e23\u0e38\u0e1b \u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14 7 \u0e23\u0e32\u0e22\u0e01\u0e32\u0e23"),
          tbl(
            ["#", "\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19", "\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17", "\u0e04\u0e27\u0e32\u0e21\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07", "\u0e44\u0e1f\u0e25\u0e4c\u0e2b\u0e25\u0e31\u0e01"],
            [
              ["1", "\u0e2b\u0e19\u0e48\u0e27\u0e22\u0e40\u0e07\u0e34\u0e19 THB/USDT + Config DCA", "BUG", "Critical", "config.py, strategy.py, engine.py"],
              ["2", "Reserve \u0e15\u0e49\u0e2d\u0e07\u0e21\u0e32\u0e08\u0e32\u0e01 BTC sell \u0e40\u0e17\u0e48\u0e32\u0e19\u0e31\u0e49\u0e19", "BUG", "High", "strategy.py, engine.py"],
              ["3", "Buy-the-dip injection logic \u0e40\u0e01\u0e34\u0e19\u0e04\u0e27\u0e32\u0e21", "BUG", "High", "strategy.py"],
              ["4", "\u0e23\u0e32\u0e22\u0e07\u0e2d\u0e32\u0e19 buy/sell success/fail", "Feature", "Medium", "notifier.py"],
              ["5", "Low-balance warning + \u0e04\u0e32\u0e14\u0e40\u0e07\u0e34\u0e19\u0e04\u0e07\u0e40\u0e2b\u0e25\u0e37\u0e2d", "Feature", "Medium", "engine.py, notifier.py"],
              ["6", "\u0e41\u0e22\u0e01 DCA cash vs Reserve cash", "Feature", "High", "strategy.py, engine.py, state.py"],
              ["7", "\u0e23\u0e35\u0e40\u0e0b\u0e15 demo data", "Action", "High", "demo_state.json, demo_trades.json"],
            ]
          ),
          new Paragraph({ spacing: { after: 200 } }),

          // 3. Issue 1
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 1: \u0e2b\u0e19\u0e48\u0e27\u0e22\u0e40\u0e07\u0e34\u0e19\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14 + DCA Config Parameterization"),
          h("\u0e23\u0e32\u0e22\u0e25\u0e30\u0e40\u0e2d\u0e35\u0e22\u0e14\u0e1b\u0e31\u0e0d\u0e2b\u0e32\u0e22", HeadingLevel.HEADING_2),
          p("\u0e23\u0e30\u0e1a\u0e1a\u0e21\u0e35 config.py \u0e17\u0e35\u0e48\u0e01\u0e33\u0e2b\u0e19\u0e14\u0e04\u0e48\u0e32\u0e43\u0e19\u0e2b\u0e19\u0e48\u0e27\u0e22 THB \u0e04\u0e37\u0e2d DAILY_BUDGET_THB \u0e41\u0e25\u0e30 MAX_BUY_THB \u0e41\u0e25\u0e49\u0e27 convert \u0e40\u0e1b\u0e47\u0e19 USDT \u0e14\u0e49\u0e27\u0e22 USD_THB_RATE \u0e43\u0e19 engine.py \u0e41\u0e15\u0e48 strategy.py \u0e21\u0e35\u0e04\u0e48\u0e32 reserve hardcode \u0e40\u0e1b\u0e47\u0e19 THB \u0e15\u0e23\u0e07\u0e17\u0e35\u0e48 \u0e1a\u0e23\u0e23\u0e17\u0e31\u0e14 137-155: usable_cash = max(cash_reserve - 200, 0), injection = min(usable_cash * deploy_rate, 900), injection boosted cap 1200 \u0e40\u0e21\u0e37\u0e48\u0e2d currency=USDT \u0e04\u0e48\u0e32\u0e40\u0e2b\u0e25\u0e48\u0e32\u0e19\u0e35\u0e49\u0e04\u0e27\u0e23\u0e40\u0e1b\u0e47\u0e19 ~6/27/36 USDT \u0e44\u0e21\u0e48\u0e43\u0e0a\u0e48 200/900/1200 \u0e0b\u0e36\u0e48\u0e07\u0e17\u0e33\u0e43\u0e2b\u0e49\u0e0b\u0e37\u0e49\u0e2d BTC \u0e40\u0e01\u0e34\u0e19 33x"),
          h("\u0e42\u0e04\u0e23\u0e07\u0e01\u0e32\u0e23\u0e41\u0e01\u0e49", HeadingLevel.HEADING_2),
          h("1a. \u0e02\u0e22\u0e32\u0e22 config.py \u0e40\u0e1e\u0e34\u0e48\u0e21 DCAConfig", HeadingLevel.HEADING_3),
          p("\u0e40\u0e1e\u0e34\u0e48\u0e21 DCAConfig dataclass \u0e17\u0e35\u0e48\u0e21\u0e35 parameter: daily_dca_amount (default \u0e02\u0e36\u0e49\u0e19\u0e01\u0e31\u0e1a exchange), max_dca_per_day, reserve_floor_pct, reserve_injection_cap_pct, reserve_boosted_cap_pct, deploy_rate_tiers \u0e17\u0e38\u0e01\u0e04่\u0e32\u0e2d่\u0e32น env vars \u0e41\u0e25ะ\u0e21\u0e35 default \u0e2dั\u0e15โ\u0e19\u0e21\u0e31\u0e15\u0e34\u0e15\u0e32\u0e21 currency \u0e02\u0e2d\u0e07 exchange. \u0e43\u0e0a\u0e49 percentage-based caps \u0e41\u0e17\u0e19 absolute THB values \u0e40\u0e1e\u0e37\u0e48\u0e2d scale \u0e2dัตโ\u0e19\u0e21ั\u0e15\u0e34\u0e01ั\u0e1aทุก portfolio size"),
          h("1b. \u0e41\u0e01\u0e49 strategy.py \u0e1a\u0e23\u0e23\u0e17ัด 137-155", HeadingLevel.HEADING_3),
          p("\u0e40\u0e1b\u0e25ี่\u0e22น hardcode 200/900/1200 \u0e40\u0e1b\u0e47\u0e19 reserve_config \u0e17ี\u0e48ส่\u0e07เข้าม\u0e32\u0e40ป็\u0e19 parameter \u0e02\u0e2dง phoenix_v5_1_decision(). \u0e43\u0e0a\u0e49 reserve_floor = cash_reserve * reserve_floor_pct \u0e41ทน absolute 200 \u0e41ละ injection_cap / boosted_cap \u0e40ป็\u0e19 percentage \u0e02\u0e2dง cash_reserve. deploy_rate_tiers \u0e2d่า\u0e19จาก config \u0e41ทน hardcode dict \u0e43\u0e19 function"),
          h("1c. \u0e41\u0e01\u0e49 engine.py budget conversion", HeadingLevel.HEADING_3),
          p("\u0e43\u0e19 run_daily() \u0e41\u0e25ะ run_demo() \u0e2aร้\u0e32ง DCAConfig \u0e08าก config \u0e41ละส่\u0e07 reserve_config parameter \u0e40\u0e02้า strategy \u0e40\u0e1eิ่ม validation \u0e27่า exchange.currency \u0e15รงกับ state currency \u0e01่อน run. \u0e16้\u0e32ไม่ตร\u0e07\u0e01ัน skip \u0e41ละ\u0e41จ้\u0e07 warning"),
          h("\u0e04่\u0e32 Default \u0e15\u0e32ม Exchange", HeadingLevel.HEADING_3),
          tbl(
            ["\u0e1e\u0e32\u0e23\u0e32\u0e21\u0e34\u0e40\u0e15\u0e2d\u0e23\u0e4c", "USDT (Binance)", "THB (Bitkub)", "\u0e2b\u0e21\u0e32\u0e22\u0e40\u0e2b\u0e15\u0e38"],
            [
              ["daily_dca_amount", "3 USDT", "100 THB", "~1:33"],
              ["max_dca_per_day", "10 USDT", "300 THB", "3x daily"],
              ["reserve_floor_pct", "2%", "2%", "of cash_reserve"],
              ["reserve_injection_cap_pct", "5%", "5%", "of cash_reserve"],
              ["reserve_boosted_cap_pct", "10%", "10%", "of cash_reserve"],
            ]
          ),
          new Paragraph({ spacing: { after: 200 } }),

          // 4. Issue 2
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 2: Reserve \u0e15้\u0e2d\u0e07\u0e21า\u0e08\u0e32ก BTC Sell \u0e40\u0e17่\u0e32\u0e19ั้\u0e19"),
          h("\u0e23\u0e32\u0e22\u0e25ะ\u0e40\u0e2d\u0e35\u0e22\u0e14\u0e1bัญ\u0e2b\u0e32\u0e22", HeadingLevel.HEADING_2),
          p("\u0e1bัจจุบัน cash_reserve \u0e17ี่ส่\u0e07เข้า strategy \u0e04ือ cash_balance \u0e17ั้งหมด \u0e23วม DCA \u0e40งินที่รอซื้อ BTC \u0e14้วย \u0e0bึ่งงคิดว่า bot \u0e08ะ deploy reserve \u0e40\u0e1eื่อซื้อ BTC \u0e40\u0e1eิ่ม \u0e43นเงิน DCA \u0e40ดียวกัน \u0e0bึ่งผิด: reserve \u0e04ือ \u0e40\u0e07ินที่ได้\u0e08าก BTC sell \u0e43น bull run \u0e40\u0e1eื่\u0e2dเ\u0e01็บไว้ซื้\u0e2d BTC \u0e15่\u0e33\u0e43น bear \u0e44ม่ใช่ DCA cash"),
          h("\u0e42\u0e04\u0e23\u0e07\u0e01า\u0e23\u0e41\u0e01\u0e49", HeadingLevel.HEADING_2),
          p("\u0e40\u0e1eิ่\u0e21 reserve_balance field \u0e43\u0e19 state.json \u0e41ละ demo_state.json \u0e2bย่\u0e2dย total_sell_proceeds \u0e08าก cash_balance \u0e41ล้วส่\u0e07 reserve_balance \u0e41ท\u0e19 cash_balance \u0e44ป strategy. \u0e43น engine.py \u0e40มื่\u0e2d sell \u0e2a่\u0e07 net_proceeds \u0e40ข้า reserve_balance (\u0e44\u0e21่ใช่ cash_balance) \u0e41\u0e25ะ Telegram \u0e41สด\u0e07 cash \u0e41ยก DCA / Reserve \u0e0aัดเจน"),

          // 5. Issue 3
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 3: Buy-the-Dip Injection Logic Audit"),
          p("\u0e1a\u0e23\u0e23\u0e17ัด 137-155 \u0e02\u0e2d\u0e07 strategy.py \u0e21\u0e35 condition: \u0e16้\u0e32 price < realized_price * 1.05 \u0e08ะ boost injection * 1.8 \u0e17ั\u0e49\u0e07\u0e19\u0e35\u0e49 realized_price = price/mvrv \u0e0bึ่\u0e07\u0e40\u0e1b็น\u0e23\u0e32\u0e04า\u0e40ฉลี่ย BTC \u0e17ี่\u0e16ือครบ (\u0e40ช่น 50,000 \u0e41\u0e15่ BTC \u0e23า\u0e04า 65,000) \u0e17\u0e33\u0e43\u0e2b้ price \u0e17ั้\u0e07\u0e2bมด \u0e15่\u0e33\u0e01ว่า realized_price \u0e43\u0e19 bear market \u0e2a่\u0e07ผล boost 1.8x \u0e15ลอดเวล\u0e32"),
          p("\u0e41\u0e01้: \u0e40\u0e1bลี่\u0e22น condition \u0e40\u0e1b็น price < realized_price * 0.95 \u0e41\u0e17\u0e19 \u0e40\u0e1eื่อตรวจสอบว่า price \u0e15่\u0e33\u0e01ว่\u0e32 realized_price \u0e2dย่\u0e32ง\u0e19\u0e49\u0e2dย 5% \u0e41\u0e25ะเ\u0e1eิ่\u0e21 in_bear check \u0e40ข้า condition \u0e14้\u0e27ย \u0e40\u0e1eื่อก\u0e31\u0e19\u0e44\u0e21่ boost \u0e43\u0e19 bull market"),

          // 6. Issue 4
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 4: \u0e23\u0e32\u0e22\u0e07\u0e2dาน Buy/Sell Success or Fail"),
          p("\u0e1bัจจ\u0e38\u0e1aั\u0e19 notifier.py format_report() \u0e41\u0e2aด\u0e07\u0e40\u0e09\u0e1eาะ decision amounts \u0e44\u0e21่แส\u0e14\u0e07ว่า order \u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08\u0e2bร\u0e37\u0e2d\u0e25้\u0e21\u0e40\u0e2b\u0e15ุ \u0e16้\u0e32 exchange API \u0e21\u0e35\u0e1bั\u0e0d\u0e2bา (insufficient funds, rate limit, network) bot \u0e08\u0e30 set buy_amount=0 \u0e41ต่ Telegram \u0e44\u0e21่\u0e41ส\u0e14\u0e07 error \u0e41\u0e01\u0e49: \u0e40\u0e1eิ่\u0e21 trade_result dict \u0e2a\u0e48\u0e07เ\u0e02้\u0e32 notifier \u0e42ดยระ\u0e1a\u0e38 success/fail, amount executed, error message"),

          // 7. Issue 5
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 5: Low-Balance Warning + Remaining Days"),
          p("\u0e1bั\u0e08\u0e08\u0e38\u0e1a\u0e31\u0e19 bot \u0e0b\u0e37้อ BTC \u0e08นกระทั่\u0e07 cash=0 \u0e42ดย\u0e44\u0e21่\u0e21\u0e35\u0e01\u0e32\u0e23\u0e41จ\u0e49\u0e07\u0e40\u0e15\u0e37\u0e2dน \u0e41\u0e01\u0e49: \u0e40\u0e1eิ่\u0e21 balance check \u0e43\u0e19 engine.py \u0e17\u0e38ก\u0e04รั้\u0e07: \u0e16้\u0e32 cash < daily_dca * 3 \u0e2a่\u0e07 Telegram warning \u0e1eร้\u0e2d\u0e21\u0e04ำ\u0e19ว\u0e19 DCA \u0e04\u0e07เ\u0e2bลื\u0e2d (cash / daily_dca) \u0e41ละถ้\u0e32 cash < min_buy \u0e2a่\u0e07 critical alert"),

          // 8. Issue 6
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 6: \u0e41\u0e22\u0e01 DCA Cash vs Reserve Cash"),
          p("\u0e17ั\u0e49\u0e07 DCA \u0e41\u0e25ะ Reserve \u0e15้\u0e2d\u0e07แยกกัน\u0e0aัดเจน: DCA cash = \u0e40\u0e07ิ\u0e19\u0e17ี่ร\u0e2dซื\u0e49\u0e2d BTC \u0e15าม DCA schedule (base_budget * multiplier). Reserve cash = \u0e40\u0e07ิ\u0e19\u0e17ี่\u0e44\u0e14้\u0e08\u0e32\u0e01 BTC sell. \u0e42\u0e14ย\u0e1bั\u0e08\u0e08ุ\u0e1a\u0e31\u0e19 state \u0e21\u0e35 cash \u0e2dั\u0e19\u0e40\u0e14ีย\u0e27 \u0e41\u0e25ะ strategy deploy \u0e23วม\u0e01ั\u0e19 \u0e41\u0e01้: \u0e40\u0e1eิ่\u0e21 dca_cash \u0e41\u0e25ะ reserve_cash \u0e41ยกกั\u0e19 \u0e43\u0e19 state \u0e41\u0e25ะ engine \u0e2a่\u0e07 base_budget \u0e2bัก dca_cash, reserve_injection \u0e2bัก reserve_cash"),

          // 9. Issue 7
          h("\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 \u0e17\u0e35\u0e48 7: \u0e23\u0e35\u0e40\u0e0b\u0e15 Demo Data"),
          p("\u0e15้\u0e2d\u0e07\u0e25บ demo_state.json \u0e41\u0e25ะ demo_trades.json \u0e40\u0e14\u0e35ยว\u0e01\u0e48อน test \u0e23อบ\u0e43หม่ \u0e40\u0e19ื\u0e48อ\u0e07จาก history \u0e21ี THB/USDT \u0e1b\u0e19\u0e01ัน \u0e41\u0e25ะ peak_value \u0e40\u0e1b็น 240,053 (\u0e04วร ~10,000) \u0e02ั้นตอน: (1) delete demo_state.json \u0e41\u0e25ะ demo_trades.json (2) run --demo --reset \u0e43\u0e2bม่ (3) verify initial_cash, currency, exchange \u0e16ูก\u0e15้\u0e2d\u0e07 (4) run --demo --force \u0e40\u0e1e\u0e37่\u0e2d confirm buy amounts \u0e2d\u0e22ู่\u0e43น\u0e02อบ\u0e40\u0e07ิน"),

          // 10. Roadmap
          h("\u0e41\u0e1c\u0e19\u0e1bฏิ\u0e1a\u0e31\u0e15ิ\u0e01า\u0e23 (Implementation Roadmap)"),
          p("\u0e01\u0e32\u0e23แ\u0e01\u0e49\u0e44ข\u0e41บ่\u0e07\u0e40\u0e1b็น 3 phase \u0e15\u0e32ม\u0e25\u0e33\u0e14ั\u0e1a \u0e42ดย Phase 1 \u0e41\u0e01\u0e49 Critical Bugs \u0e01\u0e48อ\u0e19 (\u0e1b\u0e23ะ\u0e40\u0e14\u0e47\u0e19 1-3, 7) \u0e41\u0e25้ว Phase 2 \u0e40\u0e1eิ่\u0e21 Features (\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19 4-6) \u0e41\u0e25ะ Phase 3 \u0e17\u0e14\u0e2a\u0e2d\u0e1a\u0e23อ\u0e1a"),
          tbl(
            ["Phase", "\u0e1b\u0e23\u0e30\u0e40\u0e14\u0e47\u0e19", "\u0e44\u0e1f\u0e25\u0e4c", "\u0e01\u0e32\u0e23\u0e17\u0e14\u0e2a\u0e2d\u0e1a"],
            [
              ["1A", "\u0e02\u0e22\u0e32\u0e22 config.py (DCAConfig)", "config.py", "Unit: config loads per exchange"],
              ["1B", "\u0e41\u0e01\u0e49 strategy.py reserve", "strategy.py", "Unit: reserve scales with currency"],
              ["1C", "\u0e41\u0e01\u0e49 engine.py budget conversion", "engine.py", "Unit: DCAConfig to strategy"],
              ["1D", "\u0e41\u0e22\u0e01 reserve_balance in state", "state.py", "Migration: add field"],
              ["1E", "Reset demo data", "demo_*.json", "Manual: verify clean state"],
              ["2A", "Buy-the-dip audit fix", "strategy.py", "Unit: boost only if price < RP*0.95"],
              ["2B", "Trade result reporting", "notifier.py", "Integration: Telegram success/fail"],
              ["2C", "Low-balance warning", "engine.py", "Unit: warning at thresholds"],
              ["2D", "Separate DCA vs Reserve", "state.py, engine.py", "Integration: track both"],
              ["3", "Full demo re-run (14+ days)", "GitHub Actions", "Validation report pass"],
            ]
          ),
          new Paragraph({ spacing: { after: 200 } }),

          // 11. Risk
          h("\u0e04วาม\u0e40\u0e2aี่ยง\u0e41\u0e25ะผล\u0e01ระทบ (Risk Assessment)"),
          p("\u0e01าร\u0e41\u0e01\u0e49 Phase 1 \u0e21\u0e35\u0e04วาม\u0e40\u0e2aี่ยง\u0e15่\u0e33 \u0e40\u0e19ื่\u0e2d\u0e07จากเป็น\u0e01\u0e32\u0e23\u0e40\u0e1bลี่\u0e22\u0e19 parameter \u0e41\u0e25ะ logic \u0e42\u0e14ย\u0e44\u0e21่\u0e48\u0e41\u0e15ะ trade API \u0e2a่\u0e27\u0e19 DRY_RUN \u0e41\u0e25ะ DEMO \u0e2dย\u0e39่\u0e43น safe sandbox \u0e01\u0e32\u0e23เ\u0e1bลี่\u0e22น state schema (\u0e40\u0e1eิ่\u0e21 reserve_balance) \u0e15้\u0e2d\u0e07 migration script \u0e2a\u0e33\u0e2b\u0e23ั\u0e1a state.json \u0e40\u0e14ิ\u0e21 \u0e41ต่\u0e2a\u0e33\u0e2bรั\u0e1a demo \u0e2a\u0e32\u0e21าร\u0e16 reset \u0e43\u0e2b\u0e21่\u0e44ด้\u0e40\u0e25ย\u0e42ดย\u0e44\u0e21่\u0e48\u0e15้\u0e2d\u0e07 migration"),

          // 12. Appendix
          h("\u0e1f\u0e34\u0e23\u0e4c\u0e14\u0e31\u0e1a: \u0e2b\u0e25ั\u0e01\u0e10\u0e32\u0e19 Bug \u0e08\u0e32\u0e01 demo_state.json"),
          h("Evidence 1: THB prices in USDT state", HeadingLevel.HEADING_2),
          p("History entry \u0e41\u0e23\u0e01\u0e02อ\u0e07 demo \u0e21\u0e35 price=2,143,446.25 (THB \u0e08\u0e32\u0e01 Bitkub) \u0e41\u0e15\u0e48 state \u0e21\u0e35 currency=USDT, exchange=binance. History entry \u0e17\u0e35\u0e48 4 \u0e21\u0e35 price=64,780.10 (USDT) \u0e41\u0e2a\u0e14\u0e07\u0e27่\u0e32 exchange \u0e40\u0e1b\u0e25\u0e35่\u0e22\u0e19 Bitkub\u2192Binance \u0e23\u0e30\u0e2bว\u0e48\u0e32\u0e07 run \u0e42\u0e14ย\u0e44\u0e21่\u0e48 reset"),
          h("Evidence 2: Reserve injection 33x overbuy", HeadingLevel.HEADING_2),
          p("\u0e1a\u0e23\u0e23\u0e17ั\u0e14 137: usable_cash = max(cash_reserve - 200, 0) \u0e16้\u0e32 cash=9,000 USDT \u0e08ะ deploy 8,800 USDT \u0e41ทน\u0e17ี่\u0e04วร\u0e40\u0e1b\u0e47\u0e19 ~8,820 * deploy_rate \u0e40\u0e1eรา\u0e30 200 \u0e04ื\u0e2d 200 THB \u0e04\u0e27ร\u0e40\u0e1b็\u0e19 ~6 USDT (200/33.4) \u0e17\u0e33\u0e43\u0e2b้ usable_cash \u0e40พิ่\u0e21\u0e02ึ้น 194 USDT"),
          h("Evidence 3: Cash exhausted in 62 runs", HeadingLevel.HEADING_2),
          p("demo_state.json: cash=0.0, buy_count=62, total_invested=9,985.02, cumulative_fees=14.98, cumulative_slippage=3.19 \u0e23วม = 10,003.19 \u0e41สด\u0e07\u0e27่\u0e32 initial 10,000 \u0e16ูก\u0e43\u0e0a\u0e49\u0e2bมด\u0e41\u0e25้\u0e27 \u0e42ดย cash \u0e2bมดลง 0 \u0e43\u0e19 5 \u0e27ั\u0e19 (62 runs = ~4 runs/day via manual trigger) \u0e40\u0e19\u0e37่\u0e2d\u0e07จาก reserve deployment \u0e42ดย\u0e44\u0e21่\u0e21ี cap \u0e17ี่\u0e40\u0e2b\u0e21\u0e32ะ\u0e2a\u0e21"),
        ],
      },
    ],
  });
  const buf = await Packer.toBuffer(doc);
  const out = "/home/z/my-project/download/phoenix_v51_fix_plan.docx";
  fs.writeFileSync(out, buf);
  console.log("Generated: " + out);
}
main().catch(console.error);
