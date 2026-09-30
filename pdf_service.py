import os
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether, HRFlowable
)

from core.agents.map_service import MapGeneratorService

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(BASE_DIR, "data", "pdf")
os.makedirs(PDF_DIR, exist_ok=True)

class CampaignPdfService:
    """Service de génération de Plan Média au format PDF A4 Paysage."""

    def __init__(self, pdf_dir: str = PDF_DIR):
        self.pdf_dir = pdf_dir
        os.makedirs(self.pdf_dir, exist_ok=True)
        self.map_service = MapGeneratorService()
        self.logo_path = os.path.join(BASE_DIR, "core", "template", "logo-mmove.png")

    def generate_campaign_pdf(self, campaign_plan: Dict[str, Any], client_name: str = "Partenaire") -> str:
        """
        Construit le PDF A4 Paysage pour le plan média :
        - 1 colonne texte à gauche
        - La carte en vis-à-vis dans la colonne de droite
        - Un saut de page entre chaque mois
        """
        summary = campaign_plan.get("summary", {})
        months = campaign_plan.get("months", [])
        loc = summary.get("location", "Wallonie")
        months_count = summary.get("months_count", len(months))
        total_faces = summary.get("total_faces_deployed", 0)
        total_ots = summary.get("total_cumulative_ots", 0)
        avg_veh = summary.get("avg_veh_per_day", 0)

        # Hash pour mise en cache
        plan_hash = hashlib.md5(str(campaign_plan.get("periods", [])).encode("utf-8")).hexdigest()[:10]
        pdf_filename = f"plan_media_mmove_{loc.lower()}_{plan_hash}.pdf"
        pdf_path = os.path.join(self.pdf_dir, pdf_filename)

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=landscape(A4),
            leftMargin=25,
            rightMargin=25,
            topMargin=20,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()

        # Styles personnalisés M Move
        # Couleurs : Orange M Move = #F4920D, Bleu nuit = #1E293B, Bleu profond = #0F172A
        c_orange = colors.HexColor("#F4920D")
        c_navy = colors.HexColor("#0F172A")
        c_slate = colors.HexColor("#334155")
        c_light = colors.HexColor("#F8FAFC")
        c_border = colors.HexColor("#E2E8F0")

        style_title = ParagraphStyle(
            "MmoveTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            textColor=c_navy
        )
        style_subtitle = ParagraphStyle(
            "MmoveSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=c_orange
        )
        style_month_title = ParagraphStyle(
            "MmoveMonthTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=c_navy
        )
        style_badge = ParagraphStyle(
            "MmoveBadge",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.white
        )
        style_panel_item = ParagraphStyle(
            "MmovePanelItem",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=c_slate
        )
        style_panel_item_bold = ParagraphStyle(
            "MmovePanelItemBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=c_navy
        )
        style_meta = ParagraphStyle(
            "MmoveMeta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B")
        )
        style_tech = ParagraphStyle(
            "MmoveTech",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=c_slate
        )

        story = []

        total_pages = len(months)

        for page_idx, m in enumerate(months, start=1):
            period_str = m.get("period", "")
            period_human = m.get("period_human", "")
            panels = m.get("panels", [])
            m_stats = m.get("stats", {})
            m_veh = m_stats.get("veh_per_day", 0)
            m_ots = m_stats.get("ots_month", 0)
            deadline = m.get("deadline", "")
            deadline_full = m.get("deadline_full", "")

            # 1. En-tête de page (Logo M Move + Brand + Synthèse Campagne)
            logo_element = Image(self.logo_path, width=68, height=26) if os.path.exists(self.logo_path) else Paragraph("<b>M MOVE</b>", style_title)

            header_table_data = [
                [
                    logo_element,
                    Paragraph(f"<b>M MOVE CONSEIL</b> · <font color='#F4920D'>PLAN MÉDIA CAMPAGNE 8M²</font>", style_title),
                    Paragraph(f"<b>Client :</b> {client_name} · <b>Bassin :</b> {loc} · <b>Page {page_idx}/{total_pages}</b>", style_meta)
                ],
                [
                    "",
                    Paragraph(f"Dispositif <b>{months_count} mois</b> · <b>{total_faces} faces</b> au total · <b>~{total_ots:,.0f} occasions d'être vu (OTS)</b>".replace(",", " "), style_subtitle),
                    Paragraph(f"Format bâche : <b>390 × 200 cm</b> (bords perdus 392×202 cm)", style_meta)
                ]
            ]
            header_table = Table(header_table_data, colWidths=[75, 425, 285])
            header_table.setStyle(TableStyle([
                ("SPAN", (0, 0), (0, 1)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=1.5, color=c_orange, spaceBefore=2, spaceAfter=8))

            # 2. Colonne de Gauche : Descriptif des Faces du Mois
            left_flowables = []

            # Titre du mois avec badge
            left_flowables.append(
                Paragraph(f"<b>MOIS {page_idx} — {period_human.upper()}</b> : {len(panels)} FACES EN VISIBILITÉ DIRECTE", style_month_title)
            )
            left_flowables.append(Spacer(1, 4))

            # Tableau des panneaux du mois
            panel_rows = [
                [
                    Paragraph("<b>N°</b>", style_panel_item_bold),
                    Paragraph("<b>ID & Axe</b>", style_panel_item_bold),
                    Paragraph("<b>Emplacement & Direction</b>", style_panel_item_bold),
                    Paragraph("<b>Véh./jour</b>", style_panel_item_bold),
                    Paragraph("<b>OTS / mois</b>", style_panel_item_bold),
                ]
            ]

            for p_idx, p in enumerate(panels, start=1):
                pid = p.get("id", "")
                axe = p.get("axe_routier") or p.get("code_route") or "Axe principal"
                loc_txt = p.get("localisation") or p.get("ville") or ""
                city_txt = p.get("ville", "")
                dir_txt = p.get("direction_in") or p.get("direction_out") or "Sens unique"
                freq_val = p.get("frequentation_jour", 0)
                ots_val = p.get("ots_mensuel", int(freq_val * 36))

                # Pastille orange pour le numéro
                num_cell = Paragraph(f"<font color='#F4920D'><b>● {p_idx}</b></font>", style_panel_item_bold)
                id_axe_cell = Paragraph(f"<b>#{pid}</b><br/><font color='#64748B'>{axe}</font>", style_panel_item)
                desc_cell = Paragraph(f"<b>{city_txt}</b> ({loc_txt})<br/><font color='#64748B'>Dir. {dir_txt}</font>", style_panel_item)
                veh_cell = Paragraph(f"<b>{freq_val:,.0f}</b>".replace(",", " "), style_panel_item)
                ots_cell = Paragraph(f"<b>{ots_val:,.0f}</b>".replace(",", " "), style_panel_item)

                panel_rows.append([num_cell, id_axe_cell, desc_cell, veh_cell, ots_cell])

            panels_table = Table(panel_rows, colWidths=[28, 72, 195, 55, 65])
            panels_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), c_light),
                ("TEXTCOLOR", (0, 0), (-1, 0), c_navy),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, 0), 1, c_orange),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, c_border),
            ]))
            left_flowables.append(panels_table)
            left_flowables.append(Spacer(1, 8))

            # Synthèse mensuelle & rétroplanning
            impact_box_data = [
                [
                    Paragraph(
                        f"<b>Impact du mois de {period_human} :</b><br/>"
                        f"• <b>{m_veh:,.0f} véhicules/jour</b> sur les axes stratégiques.<br/>"
                        f"• <b>~{m_ots:,.0f} occasions d'être vu (OTS)</b> générées.<br/>"
                        f"• <b>Diversité garantie :</b> 5 axes différents, sans saturation.",
                        style_panel_item
                    ),
                    Paragraph(
                        f"<b>RÉTROPLANNING BÂCHE :</b><br/>"
                        f"Livraison des visuels : <b>avant le {deadline_full}</b><br/>"
                        f"<font color='#64748B'>Format PDF vectoriel CMJN (65 dpi min)</font><br/>"
                        f"Pose & calage assurés par nos équipes avant le 1er {period_human}.",
                        style_panel_item
                    )
                ]
            ]
            impact_table = Table(impact_box_data, colWidths=[210, 205])
            impact_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")), # Jaune pâle doux
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#FDE68A")),
            ]))
            left_flowables.append(impact_table)

            # 3. Colonne de Droite : La Carte HD du Mois en Vis-à-Vis
            right_flowables = []
            map_img_path = self.map_service.generate_campaign_map(panels, period_str=period_str, width=650, height=440)
            if os.path.exists(map_img_path):
                right_flowables.append(
                    Image(map_img_path, width=365, height=265)
                )
            right_flowables.append(Spacer(1, 4))
            right_flowables.append(
                Paragraph(
                    f"<b>Carte d'implantation — {period_human}</b> : Les pastilles <font color='#F4920D'><b>● 1 à 5</b></font> correspondent aux remorques du tableau ci-contre. Emplacements optimisés pour un maillage étendu sans redondance.",
                    style_meta
                )
            )

            # 4. Assemblage en 2 Colonnes Vis-à-Vis
            two_cols_data = [
                [left_flowables, right_flowables]
            ]
            two_cols_table = Table(two_cols_data, colWidths=[420, 368])
            two_cols_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(two_cols_table)

            # 5. Pied de page technique & réassurance commerciale
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.5, color=c_border, spaceBefore=2, spaceAfter=4))
            footer_data = [
                [
                    Paragraph("<b>M MOVE CONSEIL</b> · Affichage Mobile & Remorques Publicitaires 8m² en Wallonie", style_tech),
                    Paragraph("<b>Prestation Réseau :</b> Emplacements stratégiques 8m² · Pose & Dépose assurées · Assurance RC", style_tech),
                    Paragraph("<b>Contact :</b> mmove@mediasee.be · www.remorquepublicitaire.be", style_tech),
                ]
            ]
            footer_table = Table(footer_data, colWidths=[250, 370, 168])
            footer_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ]))
            story.append(footer_table)

            # Saut de page entre chaque mois (sauf après le dernier mois)
            if page_idx < total_pages:
                story.append(PageBreak())

        doc.build(story)
        return pdf_path
