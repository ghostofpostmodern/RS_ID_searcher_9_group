import os
from typing import Dict, Any, List

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm

from PIL import Image as PilImage


def build_pdf_report(
    rsid: str,
    extended_summary: Dict[str, Any],
    images: List[str],
    output_path: str,
) -> str:
    """
    Читаемый PDF-отчёт:
    - страница 1: basic info + таблица + предупреждения
    - дальше: по одному графику на страницу, без сплющивания (с сохранением пропорций)
    """
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    page_width, page_height = A4
    frame_width = page_width - doc.leftMargin - doc.rightMargin

    story = []

    basic = extended_summary.get("basic_info") or {}
    pops = extended_summary.get("populations") or []
    warnings = extended_summary.get("warnings") or []

    # --- Title ---
    story.append(Paragraph(f"SNP Report: {rsid}", styles["Title"]))
    story.append(Spacer(1, 0.6 * cm))

    # --- 1. Basic info ---
    story.append(Paragraph("Basic information", styles["Heading2"]))
    genes_list = basic.get("genes") or []
    genes = ", ".join(genes_list) if genes_list else "-"
    info_lines = [
        f"rsID: {basic.get('rsid', rsid)}",
        f"Variant type: {basic.get('variant_type', '-')}",
        f"Chromosome: {basic.get('chrom', '-')}",
        f"Position (GRCh38): {basic.get('pos38', '-')}",
        f"Gene(s): {genes}",
        f"HGVS (coding): {basic.get('hgvs_c', '-')}",
        f"HGVS (protein): {basic.get('hgvs_p', '-')}",
        f"Region: {basic.get('region', '-')}",
    ]
    story.append(Paragraph("<br/>".join(info_lines), styles["Normal"]))
    story.append(Spacer(1, 0.6 * cm))

    # --- 2. Population table ---
    if pops:
        story.append(Paragraph("Population frequencies", styles["Heading2"]))

        table_data: List[List[str]] = [
            ["Population", "Source", "p", "q", "MAF", "N samples", "Category"]
        ]
        for p in pops:
            table_data.append(
                [
                    p.get("name", "-"),
                    p.get("source", "-"),
                    f"{p.get('p', 0):.4f}",
                    f"{p.get('q', 0):.4f}",
                    f"{p.get('maf', 0):.4f}",
                    str(p.get("sample_n", 0)),
                    p.get("category", "-"),
                ]
            )

        col_widths = [
            frame_width * 0.20,  # Population
            frame_width * 0.20,  # Source
            frame_width * 0.10,  # p
            frame_width * 0.10,  # q
            frame_width * 0.10,  # MAF
            frame_width * 0.15,  # N
            frame_width * 0.15,  # Category
        ]

        table = Table(table_data, colWidths=col_widths, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (2, 1), (4, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 0.6 * cm))

    # --- 3. Warnings ---
    if warnings:
        story.append(Paragraph("Warnings", styles["Heading2"]))
        for w in warnings:
            story.append(Paragraph(f"- {w}", styles["Normal"]))
        story.append(Spacer(1, 0.6 * cm))

    # --- 4. Graphs: каждый график на отдельной странице, с сохранением пропорций ---
    for img_path in images:
        if not os.path.exists(img_path):
            continue

        story.append(PageBreak())
        # Можно дать заголовок по имени файла, если хочется, но пока просто "Graph"
        story.append(Paragraph("Graph", styles["Heading2"]))
        story.append(Spacer(1, 0.5 * cm))

        try:
            with PilImage.open(img_path) as im:
                orig_width, orig_height = im.size
        except Exception:
            # fallback: если не удалось прочитать, используем фиксированное соотношение
            orig_width, orig_height = 1000, 700

        if orig_width <= 0:
            aspect = 0.7
        else:
            aspect = orig_height / orig_width

        img_width = frame_width
        img_height = frame_width * aspect

        story.append(Image(img_path, width=img_width, height=img_height))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc.build(story)

    return output_path
