import os
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether, HRFlowable, Flowable
)

from core.agents.map_service import MapGeneratorService

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(BASE_DIR, "data", "pdf")
os.makedirs(PDF_DIR, exist_ok=True)


class InteractiveCheckbox(Flowable):
    """Case à cocher interactive pour formulaire PDF (AcroForm) avec affichage/impression soigné."""
    def __init__(self, name: str, size: int = 10, tooltip: str = "Sélectionner cette face"):
        super().__init__()
        self.name = name
        self.size = size
        self.tooltip = tooltip
        self.width = size + 2
        self.height = size + 2

    def draw(self):
        canv = self.canv
        canv.saveState()
        # Carré blanc à bordure orange M Move
        canv.setStrokeColor(colors.HexColor("#F4920D"))
        canv.setFillColor(colors.HexColor("#FFFFFF"))
        canv.setLineWidth(1.1)
        canv.roundRect(1, 1, self.size, self.size, 1.8, fill=1, stroke=1)

        # Widget AcroForm cliquable pour formulaire interactif PDF
        if hasattr(canv, "acroForm") and canv.acroForm:
            try:
                canv.acroForm.checkbox(
                    name=self.name,
                    tooltip=self.tooltip,
                    checked=False,
                    buttonStyle='check',
                    shape='square',
                    size=self.size,
                    x=1,
                    y=1,
                    borderColor=colors.HexColor("#F4920D"),
                    fillColor=colors.HexColor("#FFFFFF"),
                    textColor=colors.HexColor("#F4920D"),
                    borderWidth=1.1,
                    relative=True
                )
            except Exception:
                pass
        canv.restoreState()

class CampaignPdfService:
    """Service de génération de Plan Média au format PDF A4 Paysage."""

    def __init__(self, pdf_dir: str = PDF_DIR):
        self.pdf_dir = pdf_dir
        os.makedirs(self.pdf_dir, exist_ok=True)
        self.map_service = MapGeneratorService()
        self.logo_path = os.path.join(BASE_DIR, "core", "template", "logo-mmove.png")

    def generate_campaign_pdf(
        self,
        campaign_plan: Dict[str, Any],
        client_name: str = "Partenaire",
        salesperson: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Construit le PDF A4 Paysage pour le plan média :
        - 1 colonne texte à gauche
        - La carte en vis-à-vis dans la colonne de droite
        - Un saut de page entre chaque mois
        - Coordonnées personnalisées du commercial connecté
        """
        summary = campaign_plan.get("summary", {})
        months = campaign_plan.get("months", [])
        loc = summary.get("location", "Wallonie")
        months_count = summary.get("months_count", len(months))
        total_faces = summary.get("total_faces_deployed", 0)
        total_ots = summary.get("total_cumulative_ots", 0)
        avg_veh = summary.get("avg_veh_per_day", 0)

        # Extraction des coordonnées du commercial
        sp_initials = (salesperson.get("initials") if salesperson else "DR") or "DR"
        sp_name = (salesperson.get("name") if salesperson else "David Rossomme") or "David Rossomme"
        sp_phone = (salesperson.get("phone") if salesperson else "+32 477 38 40 20") or ""
        sp_email = (salesperson.get("email") if salesperson else "david@mediasee.be") or ""

        # Hash pour mise en cache (dépend du client et du commercial pour régénération immédiate)
        client_slug = "".join(c if c.isalnum() else "_" for c in client_name.lower())[:15]
        plan_hash = hashlib.md5(f"v6_{client_name}_{sp_initials}_{str(campaign_plan.get('periods', []))}".encode("utf-8")).hexdigest()[:10]
        pdf_filename = f"plan_media_mmove_{client_slug}_{loc.lower()}_{sp_initials.lower()}_{plan_hash}.pdf"
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
        style_header_title = ParagraphStyle(
            "MmoveHeaderTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=c_navy
        )
        style_header_subtitle = ParagraphStyle(
            "MmoveHeaderSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=c_slate
        )
        style_header_meta_client = ParagraphStyle(
            "MmoveHeaderMetaClient",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=2,
            textColor=c_navy
        )
        style_header_meta_date = ParagraphStyle(
            "MmoveHeaderMetaDate",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=2,
            textColor=colors.HexColor("#64748B")
        )
        style_header_meta_notice = ParagraphStyle(
            "MmoveHeaderMetaNotice",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=6.5,
            leading=8.5,
            alignment=2,
            textColor=colors.HexColor("#94A3B8")
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

        french_months = {
            1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
            7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
        }
        now = datetime.now()
        date_str = f"{now.day} {french_months.get(now.month, '')} {now.year}"

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

            # 1. En-tête de page harmonieux (Logo M Move + Brand + Synthèse Campagne & Client)
            logo_element = Image(self.logo_path, width=86, height=33) if os.path.exists(self.logo_path) else Paragraph("<b>M MOVE</b>", style_title)

            header_left_block = [
                Paragraph("<b>M MOVE CONSEIL</b> &nbsp;·&nbsp; <font color='#F4920D'><b>PLAN MÉDIA CAMPAGNE 8M²</b></font>", style_header_title),
                Spacer(1, 2),
                Paragraph(f"Dispositif <b>{months_count} mois</b> &nbsp;·&nbsp; <b>{total_faces} faces</b> au total &nbsp;·&nbsp; <font color='#F4920D'><b>~{total_ots:,.0f} OTS cumulés</b></font>".replace(",", " "), style_header_subtitle)
            ]

            header_right_block = [
                Paragraph(f"<b>Client :</b> <font color='#F4920D'><b>{client_name}</b></font> &nbsp;·&nbsp; <b>Bassin :</b> {loc}", style_header_meta_client),
                Spacer(1, 1),
                Paragraph(f"<b>Conseiller :</b> <b>{sp_name}</b> ({sp_initials}) &nbsp;·&nbsp; <b>Émis le :</b> {date_str}", style_header_meta_date),
                Spacer(1, 1),
                Paragraph(f"Page {page_idx}/{total_pages} &nbsp;·&nbsp; *Disponibilités indicatives sous réserve d'options", style_header_meta_notice)
            ]

            header_table_data = [
                [
                    logo_element,
                    header_left_block,
                    header_right_block
                ]
            ]
            header_table = Table(header_table_data, colWidths=[92, 395, 304])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
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
                        f"Tournée de placement sur 3 jours ouvrables pour l'ensemble des placements.",
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
            map_img_path = self.map_service.generate_campaign_map(panels, period_str=period_str, width=1300, height=880)
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

            # 5. Pied de page technique & contact commercial dédié
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.5, color=c_border, spaceBefore=2, spaceAfter=4))
            sp_contact_parts = []
            if sp_phone:
                sp_contact_parts.append(f"Tél : {sp_phone}")
            if sp_email:
                sp_contact_parts.append(sp_email)
            sp_contact_str = " · ".join(sp_contact_parts) if sp_contact_parts else "info@mediasee.be"

            footer_data = [
                [
                    Paragraph("<b>M MOVE CONSEIL</b> · Affichage Mobile & Remorques 8m²", style_tech),
                    Paragraph("<b>Prestation Réseau :</b> Emplacements stratégiques 8m² · Tournée de placement & retrait · Assurance RC", style_tech),
                    Paragraph(f"<b>Votre contact :</b> {sp_name} · {sp_contact_str}", style_tech),
                ]
            ]
            footer_table = Table(footer_data, colWidths=[205, 325, 258])
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

    def generate_availability_pdf(
        self,
        panels: List[Dict[str, Any]],
        location_name: str = "Wallonie",
        periods: Optional[List[str]] = None,
        client_name: str = "Partenaire",
        salesperson: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Construit un catalogue des disponibilités 8m² au format PDF A4 Paysage :
        - En-tête personnalisé au nom du client et de la zone
        - Cartographie d'ensemble des emplacements disponibles
        - Tableau détaillé des remorques pour sélection client (adresses, flux, directions)
        - Coordonnées directes du commercial
        """
        sp_initials = (salesperson.get("initials") if salesperson else "DR") or "DR"
        sp_name = (salesperson.get("name") if salesperson else "David Rossomme") or "David Rossomme"
        sp_phone = (salesperson.get("phone") if salesperson else "+32 477 38 40 20") or ""
        sp_email = (salesperson.get("email") if salesperson else "david@mediasee.be") or ""

        periods = periods or []
        periods_human = []
        month_names = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        for p in periods:
            parts = p.split("-")
            if len(parts) == 2:
                try:
                    m_int = int(parts[1])
                    periods_human.append(f"{month_names[m_int].capitalize()} {parts[0]}")
                except Exception:
                    periods_human.append(p)
            else:
                periods_human.append(p)
        periods_str = " & ".join(periods_human) if periods_human else "Prochainement"

        loc_slug = "".join(c if c.isalnum() else "_" for c in location_name.lower())[:15]
        client_slug = "".join(c if c.isalnum() else "_" for c in client_name.lower())[:15]
        h_str = f"dispo_v6_{client_name}_{sp_initials}_{location_name}_{periods_str}_{len(panels)}"
        dispo_hash = hashlib.md5(h_str.encode("utf-8")).hexdigest()[:10]
        pdf_filename = f"catalogue_dispos_mmove_{client_slug}_{loc_slug}_{sp_initials.lower()}_{dispo_hash}.pdf"
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
        c_orange = colors.HexColor("#F4920D")
        c_navy = colors.HexColor("#0F172A")
        c_slate = colors.HexColor("#334155")
        c_light = colors.HexColor("#F8FAFC")
        c_border = colors.HexColor("#CBD5E1")

        style_title = ParagraphStyle(
            "DispoTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=16,
            textColor=c_navy
        )
        style_sub = ParagraphStyle(
            "DispoSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=c_slate
        )
        style_right = ParagraphStyle(
            "DispoRight",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=2,
            textColor=c_navy
        )
        style_th = ParagraphStyle(
            "DispoTH",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=8.5,
            textColor=colors.white
        )
        style_td = ParagraphStyle(
            "DispoTD",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=c_navy
        )
        style_td_bold = ParagraphStyle(
            "DispoTDBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=c_navy
        )
        style_td_orange = ParagraphStyle(
            "DispoTDOrange",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=c_orange
        )
        style_notice = ParagraphStyle(
            "DispoNotice",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=c_slate
        )
        style_comm_notice = ParagraphStyle(
            "DispoCommNotice",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8.8,
            textColor=c_slate
        )

        style_th_center = ParagraphStyle(
            "DispoTHCenter",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.white
        )
        style_td_center_bold = ParagraphStyle(
            "DispoTDCenterBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            alignment=1,
            textColor=c_orange
        )

        # Construction de la liste des faces disponibles (dédoublement si IN et OUT sont libres)
        available_faces = []
        for p_idx, p in enumerate(panels, 1):
            pid = str(p.get("id"))
            dispos = p.get("disponibilites", {})

            in_free = True
            out_free = True
            if periods:
                for prd in periods:
                    m_disp = dispos.get(prd, {})
                    if m_disp:
                        if m_disp.get("IN") == "LOUÉ":
                            in_free = False
                        if m_disp.get("OUT") == "LOUÉ":
                            out_free = False

            dir_in = p.get("direction_in") or "Sens entrant"
            dir_out = p.get("direction_out") or "Sens sortant"

            if in_free and out_free:
                available_faces.append({
                    **p,
                    "pin_num": p_idx,
                    "face": "IN",
                    "face_tag": "IN",
                    "direction": dir_in,
                    "display_code": f"#{pid} IN",
                    "chk_name": f"chk_{pid}_in"
                })
                available_faces.append({
                    **p,
                    "pin_num": p_idx,
                    "face": "OUT",
                    "face_tag": "OUT",
                    "direction": dir_out,
                    "display_code": f"#{pid} OUT",
                    "chk_name": f"chk_{pid}_out"
                })
            elif in_free:
                available_faces.append({
                    **p,
                    "pin_num": p_idx,
                    "face": "IN",
                    "face_tag": "IN",
                    "direction": dir_in,
                    "display_code": f"#{pid} IN",
                    "chk_name": f"chk_{pid}_in"
                })
            elif out_free:
                available_faces.append({
                    **p,
                    "pin_num": p_idx,
                    "face": "OUT",
                    "face_tag": "OUT",
                    "direction": dir_out,
                    "display_code": f"#{pid} OUT",
                    "chk_name": f"chk_{pid}_out"
                })
            else:
                dir_gen = p.get("direction") or dir_out or dir_in or "Double sens"
                available_faces.append({
                    **p,
                    "pin_num": p_idx,
                    "face": "A",
                    "face_tag": "A",
                    "direction": dir_gen,
                    "display_code": f"#{pid}",
                    "chk_name": f"chk_{pid}"
                })

        total_faces = len(available_faces)
        total_panels = len(panels)
        total_veh = sum(p.get("frequentation_jour") or p.get("frequentation") or 0 for p in panels)
        total_ots = sum(p.get("ots_mensuel") or p.get("ots") or 0 for p in panels)
        today_str = datetime.now().strftime("%d/%m/%Y")

        def make_header():
            hdr_cells = []
            if os.path.exists(self.logo_path):
                # Respect strict du ratio 2.6:1 du logo M Move sans déformation
                hdr_cells.append(Image(self.logo_path, width=86, height=33))
            else:
                hdr_cells.append(Paragraph("<b>M MOVE</b>", style_title))

            hdr_cells.append([
                Paragraph(f"<b>CATALOGUE DES DISPONIBILITÉS 8M² — SÉLECTION CLIENT</b>", style_title),
                Spacer(1, 2),
                Paragraph(f"Bassin cible : <b>{location_name}</b> · Période : <b>{periods_str}</b> · <b>{total_faces} faces disponibles ({total_panels} panneaux qualifiés)</b>", style_sub)
            ])

            hdr_cells.append([
                Paragraph(f"<b>Client :</b> <font color='#F4920D'>{client_name}</font>", style_right),
                Paragraph(f"Document d'aide au choix · Édité le {today_str}", style_right),
                Paragraph(f"<b>Contact :</b> {sp_name}", style_right)
            ])
            t = Table([hdr_cells], colWidths=[96, 470, 225])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            return t

        def make_footer():
            sp_contact_parts = []
            if sp_phone:
                sp_contact_parts.append(f"Tél : {sp_phone}")
            if sp_email:
                sp_contact_parts.append(sp_email)
            sp_contact_str = " · ".join(sp_contact_parts) if sp_contact_parts else "info@mediasee.be"
            f_table = Table([[
                Paragraph("<b>M MOVE CONSEIL</b> · Réseau d'Affichage Mobile 8m² en Wallonie", style_sub),
                Paragraph("<i>Cochez vos faces favorites ou transmettez leurs numéros à votre conseiller pour monter le Plan Média certifié.</i>", style_sub),
                Paragraph(f"<b>{sp_name}</b> · {sp_contact_str}", style_right)
            ]], colWidths=[240, 310, 240])
            f_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEABOVE", (0, 0), (-1, -1), 0.5, c_border),
            ]))
            return f_table

        story = []

        # PAGE 1 : Synthèse + Carte HD + Premiers emplacements
        story.append(make_header())
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1, color=c_orange, spaceBefore=0, spaceAfter=5))

        # KPI Bar (Terminologie : Faces et Panneaux)
        kpi_cells = [
            [
                Paragraph("<b>FACES DISPONIBLES</b>", style_th),
                Paragraph("<b>FLUX TRAFIC DIRECT CUMULÉ</b>", style_th),
                Paragraph("<b>AUDIENCE MENSUELLE TOTALE</b>", style_th),
                Paragraph("<b>ZONE COUVERTE</b>", style_th)
            ],
            [
                Paragraph(f"<font size=11 color='#F4920D'><b>{total_faces} faces</b></font> ({total_panels} panneaux)", style_td_bold),
                Paragraph(f"<font size=11 color='#0F172A'><b>{total_veh:,}</b></font> véh./jour".replace(",", " "), style_td_bold),
                Paragraph(f"<font size=11 color='#0F172A'><b>~{total_ots:,}</b></font> OTS / mois".replace(",", " "), style_td_bold),
                Paragraph(f"<font size=11 color='#0F172A'><b>{location_name}</b></font> & périphérie", style_td_bold)
            ]
        ]
        kpi_table = Table(kpi_cells, colWidths=[185, 205, 205, 195])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), c_navy),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6))

        # Répartition page 1 vs page 2 : Jusqu'à 9 faces en Page 1, le reste en Page 2
        if total_faces <= 9:
            page1_faces = available_faces
            remaining_faces = []
        else:
            page1_faces = available_faces[:8]
            remaining_faces = available_faces[8:]

        # Colonne de gauche Page 1 : Tableau des faces avec case à cocher interactive et colonne Direction dédiée
        left_rows = [
            [
                Paragraph("<b>Choix</b>", style_th_center),
                Paragraph("<b>N°</b>", style_th_center),
                Paragraph("<b>Face</b>", style_th),
                Paragraph("<b>Commune & Emplacement</b>", style_th),
                Paragraph("<b>Axe</b>", style_th),
                Paragraph("<b>Direction</b>", style_th),
                Paragraph("<b>Trafic</b>", style_th),
                Paragraph("<b>OTS</b>", style_th),
            ]
        ]
        for f in page1_faces:
            pid = str(f.get("id"))
            pin_n = str(f.get("pin_num", 1))
            face_tag = f.get("face_tag", "A")
            v = f.get("ville", "")
            loc = f.get("localisation", "")
            axe = f.get("code_route") or f.get("axe_routier") or ""
            d = f.get("direction", "Double sens")
            if len(d) > 17:
                d = d[:15] + ".."
            freq = f"{f.get('frequentation_jour', 0):,}".replace(",", " ")
            ots = f"{f.get('ots_mensuel', 0):,}".replace(",", " ")
            dist = f" ({f.get('distance_km')} km)" if f.get("distance_km") else ""

            chk = InteractiveCheckbox(f["chk_name"], size=10, tooltip=f"Sélectionner {f['display_code']}")

            left_rows.append([
                chk,
                Paragraph(f"<b>● {pin_n}</b>", style_td_center_bold),
                Paragraph(f"<b>#{pid}</b> <font size=6.5 color='#F4920D'><b>{face_tag}</b></font>", style_td),
                Paragraph(f"<b>{v}</b> - {loc}{dist}", style_td),
                Paragraph(f"{axe}", style_td),
                Paragraph(f"{d}", style_td),
                Paragraph(f"<b>{freq}</b>", style_td),
                Paragraph(f"{ots}", style_td),
            ])

        # Largeur totale = 442 pt : colonnes harmonisées
        left_tbl = Table(left_rows, colWidths=[26, 24, 52, 118, 44, 86, 46, 46])
        left_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), c_navy),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ALIGN", (2, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (1, -1), 1),
            ("RIGHTPADDING", (0, 0), (1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_light]),
            ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ]))

        # Encadré commercial valorisant les disponibilités et incitant à l'option
        notice_box = Table([[
            Paragraph(
                f"<b>* Disponibilités constatées en temps réel au {today_str} :</b> compte tenu de la forte rotation de notre réseau et de la demande soutenue sur le bassin de <b>{location_name}</b>, ces faces sont proposées sous réserve de confirmation au moment de la réservation ferme.<br/>"
                f"<b>Recommandation :</b> <i>posez une option prioritaire (sans engagement) auprès de votre conseiller afin de sécuriser immédiatement vos faces favorites.</i>",
                style_comm_notice
            )
        ]], colWidths=[442])
        notice_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("LINELEFT", (0, 0), (0, -1), 2.5, c_orange),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))

        left_flowables = [
            Paragraph("<b>Sélection des faces prioritaires (cliquez pour cocher) :</b>", style_td_bold),
            Spacer(1, 3),
            left_tbl,
            Spacer(1, 4),
            Paragraph(
                "<b>Conseil :</b> <i>cochez 2 à 5 faces complémentaires pour couvrir l'ensemble des axes d'accès majeurs sans doublon de visibilité.</i>",
                style_notice
            ),
            Spacer(1, 4),
            notice_box
        ]

        # Colonne de droite Page 1 : Carte HD des disponibilités (avec cadrage et marges sécurisées)
        right_flowables = []
        map_img_path = self.map_service.generate_campaign_map(panels[:20], period_str=f"dispo_{dispo_hash}", width=1100, height=750)
        if os.path.exists(map_img_path):
            right_flowables.append(Image(map_img_path, width=340, height=230))
        right_flowables.append(Spacer(1, 3))
        right_flowables.append(Paragraph(
            f"<b>Carte du bassin {location_name}</b> : Pastilles oranges numérotées correspondant aux emplacements libres du tableau. Couverture équilibrée des axes structurants.",
            style_notice
        ))

        p1_two_cols = Table([[left_flowables, right_flowables]], colWidths=[442, 348])
        p1_two_cols.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(p1_two_cols)
        story.append(Spacer(1, 6))
        story.append(make_footer())

        # Si plus de faces que l'espace disponible en Page 1, ajouter les pages suivantes
        if remaining_faces:
            story.append(PageBreak())
            story.append(make_header())
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=1, color=c_orange, spaceBefore=0, spaceAfter=6))
            story.append(Paragraph(f"<b>Suite des disponibilités pour sélection ({len(remaining_faces)} faces complémentaires) :</b>", style_td_bold))
            story.append(Spacer(1, 4))

            # Table complète en pleine largeur (790 pt)
            full_rows = [
                [
                    Paragraph("<b>Choix</b>", style_th_center),
                    Paragraph("<b>N°</b>", style_th_center),
                    Paragraph("<b>Face</b>", style_th),
                    Paragraph("<b>Commune</b>", style_th),
                    Paragraph("<b>Emplacement précis</b>", style_th),
                    Paragraph("<b>Axe Routier</b>", style_th),
                    Paragraph("<b>Direction du flux</b>", style_th),
                    Paragraph("<b>Distance</b>", style_th),
                    Paragraph("<b>Trafic direct</b>", style_th),
                    Paragraph("<b>OTS mensuels</b>", style_th),
                ]
            ]
            for f in remaining_faces:
                pid = str(f.get("id"))
                pin_n = str(f.get("pin_num", 1))
                face_tag = f.get("face_tag", "A")
                v = f.get("ville", "")
                loc = f.get("localisation", "")
                axe = f.get("code_route") or f.get("axe_routier") or ""
                d = f.get("direction", "Double sens")
                freq = f"{f.get('frequentation_jour', 0):,}".replace(",", " ")
                ots = f"{f.get('ots_mensuel', 0):,}".replace(",", " ")
                dist = f"{f.get('distance_km')} km" if f.get("distance_km") else "-"

                chk = InteractiveCheckbox(f["chk_name"], size=10, tooltip=f"Sélectionner {f['display_code']}")

                full_rows.append([
                    chk,
                    Paragraph(f"<b>● {pin_n}</b>", style_td_center_bold),
                    Paragraph(f"<b>#{pid}</b> <font size=6.5 color='#F4920D'><b>{face_tag}</b></font>", style_td),
                    Paragraph(f"<b>{v}</b>", style_td),
                    Paragraph(f"{loc}", style_td),
                    Paragraph(f"{axe}", style_td),
                    Paragraph(f"{d}", style_td),
                    Paragraph(f"{dist}", style_td),
                    Paragraph(f"<b>{freq} v/j</b>", style_td),
                    Paragraph(f"~{ots}", style_td),
                ])

            full_tbl = Table(full_rows, colWidths=[26, 24, 52, 70, 180, 60, 130, 48, 80, 80])
            full_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), c_navy),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("ALIGN", (2, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (1, -1), 1),
                ("RIGHTPADDING", (0, 0), (1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_light]),
                ("GRID", (0, 0), (-1, -1), 0.5, c_border),
            ]))
            story.append(full_tbl)
            story.append(Spacer(1, 10))
            story.append(make_footer())

        doc.build(story)
        return pdf_path
