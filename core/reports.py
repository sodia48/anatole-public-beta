from __future__ import annotations

from io import BytesIO
from datetime import datetime
from typing import Iterable

import pandas as pd


def portfolio_excel_bytes(
    title: str,
    market: pd.DataFrame,
    portfolio: pd.DataFrame,
    notifications: pd.DataFrame,
) -> bytes:
    output = BytesIO()

    def excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        for column in result.columns:
            if isinstance(result[column].dtype, pd.DatetimeTZDtype):
                result[column] = result[column].astype(str)
            elif result[column].dtype == "object":
                result[column] = result[column].map(
                    lambda value: value.isoformat() if hasattr(value, "isoformat") else value
                )
        return result

    market = excel_safe(market)
    portfolio = excel_safe(portfolio)
    notifications = excel_safe(notifications)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        market.to_excel(writer, sheet_name="Marché", index=False)
        portfolio.to_excel(writer, sheet_name="Portefeuille", index=False)
        notifications.to_excel(writer, sheet_name="Notifications", index=False)
        workbook = writer.book
        title_fmt = workbook.add_format({"bold": True, "font_size": 18, "font_color": "#0F2742"})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#2563EB", "font_color": "#FFFFFF", "border": 0})
        money_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        pct_fmt = workbook.add_format({"num_format": "+0.00%;-0.00%"})
        for sheet_name, frame in [("Marché", market), ("Portefeuille", portfolio), ("Notifications", notifications)]:
            sheet = writer.sheets[sheet_name]
            sheet.set_row(0, 24, header_fmt)
            sheet.freeze_panes(1, 0)
            for col_idx, column in enumerate(frame.columns):
                width = min(max(len(str(column)) + 3, 12), 34)
                if not frame.empty:
                    width = min(max(width, int(frame[column].astype(str).str.len().quantile(.9)) + 2), 34)
                sheet.set_column(col_idx, col_idx, width)
            if sheet_name == "Marché" and "Prix" in frame.columns:
                idx = frame.columns.get_loc("Prix")
                sheet.set_column(idx, idx, 14, money_fmt)
            if sheet_name == "Marché" and "Variation" in frame.columns:
                idx = frame.columns.get_loc("Variation")
                sheet.set_column(idx, idx, 14, workbook.add_format({"num_format": "+0.00;-0.00"}))

        summary = workbook.add_worksheet("Résumé")
        summary.write("A1", title, title_fmt)
        summary.write("A2", f"Généré le {datetime.now():%Y-%m-%d %H:%M}")
        summary.write("A4", "Nombre de titres suivis")
        summary.write("B4", len(market))
        summary.write("A5", "Positions")
        summary.write("B5", len(portfolio))
        summary.write("A6", "Notifications")
        summary.write("B6", len(notifications))
        summary.set_column("A:A", 30)
        summary.set_column("B:B", 18)
    return output.getvalue()


def market_pdf_bytes(
    title: str,
    market: pd.DataFrame,
    portfolio: pd.DataFrame,
    notifications: pd.DataFrame,
    notes: str = "",
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SkyTitle", parent=styles["Title"], textColor=colors.HexColor("#0F2742"), alignment=TA_CENTER, fontSize=23, leading=28))
    styles.add(ParagraphStyle(name="SkyH2", parent=styles["Heading2"], textColor=colors.HexColor("#2563EB"), spaceBefore=8, spaceAfter=6))
    story = [Paragraph(escape(title), styles["SkyTitle"]), Paragraph(f"Généré le {datetime.now():%d-%m-%Y à %H:%M}", styles["Normal"]), Spacer(1, 8)]
    if notes:
        story += [Paragraph(escape(notes), styles["Normal"]), Spacer(1, 8)]

    def add_table(section: str, frame: pd.DataFrame, columns: Iterable[str], max_rows: int = 18) -> None:
        story.append(Paragraph(section, styles["SkyH2"]))
        cols = [c for c in columns if c in frame.columns]
        if frame.empty or not cols:
            story.append(Paragraph("Aucune donnée disponible.", styles["Normal"]))
            return
        data = [cols]
        for _, row in frame.head(max_rows).iterrows():
            values = []
            for col in cols:
                value = row[col]
                if isinstance(value, float):
                    values.append(f"{value:,.2f}")
                else:
                    values.append(str(value)[:70])
            data.append(values)
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#BDD7EA")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#EEF8FF")]),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 5),
            ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 8))

    add_table("Résumé du marché", market, ["Ticker", "Nom", "Secteur", "Prix", "Variation", "Volume"])
    add_table("Portefeuille", portfolio, ["Ticker", "Quantité", "Coût moyen", "Prix", "Valeur", "Gain/perte $", "Gain/perte %"])
    add_table("Notifications", notifications, ["created_at", "category", "title", "ticker", "severity"])
    story.append(Spacer(1, 10))
    story.append(Paragraph("Données de tiers pouvant être différées ou révisées. Ce rapport est informatif et ne constitue pas une recommandation personnalisée.", styles["Normal"]))
    doc.build(story)
    return buffer.getvalue()
