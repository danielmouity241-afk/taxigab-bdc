"""
pdf_generator.py — Génération PDF du Bon de Commande (fidèle au modèle TAXI GAB+)
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, HRFlowable, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

# Couleurs TAXI GAB+
NAVY   = colors.HexColor('#0a2744')
GOLD   = colors.HexColor('#c5a028')
LIGHT  = colors.HexColor('#f5f5f5')
WHITE  = colors.white
BLACK  = colors.black
GREY   = colors.HexColor('#666666')

def _styles():
    styles = getSampleStyleSheet()
    custom = {
        'title': ParagraphStyle('title', fontSize=18, fontName='Helvetica-Bold',
                                 textColor=NAVY, alignment=TA_CENTER, spaceAfter=2),
        'subtitle': ParagraphStyle('subtitle', fontSize=10, fontName='Helvetica',
                                    textColor=GREY, alignment=TA_CENTER),
        'section_title': ParagraphStyle('section_title', fontSize=9, fontName='Helvetica-Bold',
                                         textColor=WHITE, alignment=TA_LEFT),
        'label': ParagraphStyle('label', fontSize=8, fontName='Helvetica-Bold',
                                 textColor=NAVY),
        'value': ParagraphStyle('value', fontSize=9, fontName='Helvetica',
                                 textColor=BLACK),
        'small': ParagraphStyle('small', fontSize=7, fontName='Helvetica',
                                 textColor=GREY, alignment=TA_CENTER),
        'footer': ParagraphStyle('footer', fontSize=7, fontName='Helvetica',
                                  textColor=GREY, alignment=TA_CENTER),
        'sign_title': ParagraphStyle('sign_title', fontSize=9, fontName='Helvetica-Bold',
                                      textColor=NAVY, alignment=TA_CENTER),
        'sign_sub': ParagraphStyle('sign_sub', fontSize=8, fontName='Helvetica',
                                    textColor=GREY, alignment=TA_CENTER),
        'obs_text': ParagraphStyle('obs_text', fontSize=9, fontName='Helvetica',
                                    textColor=BLACK),
    }
    return custom


def generate_bdc_pdf(bdc, config, avec_reception=False):
    """
    Génère le PDF d' un bon de commande.
    - Masque le fournisseur pour confidentialité vis-à-vis des transporteurs.
    - Affiche le numéro de bon mensuel (ex: BDC-09/26-00001).
    - Permet l'impression standard ou avec état de réception des pièces.
    - Sur bon garage : signature FOURNISSEUR à gauche et DIRECTION TECHNIQUE à droite.
    Retourne un objet bytes du PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.2*cm,
        bottomMargin=1.2*cm,
    )

    page_width = A4[0] - 3*cm
    S = _styles()
    story = []

    # ── EN-TÊTE ───────────────────────────────────────────────────────────
    logo_path = config.LOGO_PATH

    titre_doc = "BON DE COMMANDE — GARAGE" if getattr(bdc, 'est_garage', False) else "BON DE COMMANDE"
    if avec_reception:
        titre_doc += " (ÉTAT RÉCEPTION)"

    if os.path.exists(logo_path):
        logo_img = Image(logo_path, width=4*cm, height=3*cm, kind='proportional')
        header_data = [[
            logo_img,
            Paragraph(titre_doc, S['title']),
            ''
        ]]
    else:
        header_data = [[
            Paragraph(f"<b>{config.COMPANY_NAME}</b>", S['title']),
            Paragraph(titre_doc, S['title']),
            ''
        ]]

    # Numéro officiel mensuel (ex: BDC-09/26-00001) et date
    num_str = bdc.numero_affiche if hasattr(bdc, 'numero_affiche') else f"{bdc.numero:05d}"
    numero_date_data = [
        [Paragraph(f"<b>N° BON :</b> {num_str}", S['label']),
         Paragraph(f"<b>DATE :</b> {bdc.date_creation.strftime('%d/%m/%Y')}", S['label'])],
    ]
    numero_date_table = Table(numero_date_data, colWidths=[page_width*0.5, page_width*0.5])
    numero_date_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('LINEBELOW', (0,0), (-1,-1), 1, GOLD),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
    ]))

    header_table = Table(header_data, colWidths=[4*cm, page_width-4*cm, 0])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    story.append(header_table)
    story.append(Spacer(1, 4*mm))
    story.append(numero_date_table)
    story.append(Spacer(1, 6*mm))

    # ── SECTION : INFORMATIONS DU DEMANDEUR (FOURNISSEUR MASQUÉ SUR PDF) ──
    section_header = Table(
        [[Paragraph("INFORMATIONS DE LA COMMANDE", S['section_title'])]],
        colWidths=[page_width]
    )
    section_header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(section_header)

    if getattr(bdc, 'est_garage', False):
        demandeur_data = [
            [Paragraph("<b>Demandeur :</b>", S['label']),
             Paragraph(bdc.demandeur_nom or '—', S['value']),
             Paragraph("<b>Affectation :</b>", S['label']),
             Paragraph("<b>GARAGE (Usage interne atelier)</b>", S['value'])],
            [Paragraph("<b>Service / Département :</b>", S['label']),
             Paragraph(bdc.service_departement or '—', S['value']),
             Paragraph("<b>Type :</b>", S['label']),
             Paragraph("Bon de commande interne", S['value'])],
        ]
    else:
        demandeur_data = [
            [Paragraph("<b>Demandeur :</b>", S['label']),
             Paragraph(bdc.demandeur_nom or '—', S['value']),
             Paragraph("<b>Département :</b>", S['label']),
             Paragraph(bdc.service_departement or '—', S['value'])],
            [Paragraph("<b>Véhicule concerné :</b>", S['label']),
             Paragraph(bdc.vehicule_nom or '—', S['value']),
             Paragraph("<b>Immatriculation :</b>", S['label']),
             Paragraph(bdc.vehicule_immatriculation or '—', S['value'])],
            [Paragraph("<b>Transporteur :</b>", S['label']),
             Paragraph(bdc.transporteur or '—', S['value']),
             Paragraph("<b>Affectation :</b>", S['label']),
             Paragraph("Flotte Véhicule", S['value'])],
        ]
    demandeur_table = Table(demandeur_data, colWidths=[3.5*cm, page_width*0.35, 3.5*cm, page_width*0.25])
    demandeur_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), WHITE),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(demandeur_table)
    story.append(Spacer(1, 6*mm))

    # ── SECTION : MATÉRIAUX DEMANDÉS ─────────────────────────────────────
    sec_titre2 = "MATÉRIAUX DEMANDÉS & ÉTAT DE RÉCEPTION" if avec_reception else "MATÉRIAUX DEMANDÉS"
    section_header2 = Table(
        [[Paragraph(sec_titre2, S['section_title'])]],
        colWidths=[page_width]
    )
    section_header2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(section_header2)

    # En-tête du tableau des pièces
    if avec_reception:
        # Colonnes avec état de réception : N° / Désignation / Qté cmd / Reçu / Statut
        mat_col_widths = [1.2*cm, page_width - 1.2*cm - 2.2*cm - 2.2*cm - 4.5*cm, 2.2*cm, 2.2*cm, 4.5*cm]
        mat_header = [[
            Paragraph("<b>N°</b>", S['label']),
            Paragraph("<b>DÉSIGNATION</b>", S['label']),
            Paragraph("<b>QTÉ CMD</b>", S['label']),
            Paragraph("<b>QTÉ RECUE</b>", S['label']),
            Paragraph("<b>ÉTAT RÉCEPTION</b>", S['label']),
        ]]
        mat_rows = list(mat_header)
        for i, ligne in enumerate(bdc.lignes, 1):
            if ligne.statut_reception == 'recu':
                etat_str = f"<font color='#198754'><b>LIVRÉE ({ligne.quantite_recue}/{ligne.quantite})</b></font>"
            elif ligne.statut_reception == 'partiel':
                etat_str = f"<font color='#d97706'><b>PARTIEL ({ligne.quantite_recue or 0}/{ligne.quantite})</b></font>"
            else:
                etat_str = "<font color='#dc3545'><b>NON LIVRÉE</b></font>"

            row = [
                Paragraph(str(i), S['value']),
                Paragraph(ligne.designation or '', S['value']),
                Paragraph(str(ligne.quantite), S['value']),
                Paragraph(str(ligne.quantite_recue or 0), S['value']),
                Paragraph(etat_str, S['value']),
            ]
            mat_rows.append(row)
    else:
        # Tableau standard
        mat_col_widths = [1.2*cm, page_width - 1.2*cm - 2.5*cm - 5*cm, 2.5*cm, 5*cm]
        mat_header = [[
            Paragraph("<b>N°</b>", S['label']),
            Paragraph("<b>DÉSIGNATION</b>", S['label']),
            Paragraph("<b>QTÉ</b>", S['label']),
            Paragraph("<b>OBSERVATIONS</b>", S['label']),
        ]]
        mat_rows = list(mat_header)
        for i, ligne in enumerate(bdc.lignes, 1):
            row = [
                Paragraph(str(i), S['value']),
                Paragraph(ligne.designation or '', S['value']),
                Paragraph(str(ligne.quantite), S['value']),
                Paragraph(ligne.observations or '', S['value']),
            ]
            mat_rows.append(row)

    # Lignes vides pour remplissage (minimum 8 lignes au total)
    min_rows = 8
    col_count = 5 if avec_reception else 4
    while len(mat_rows) < min_rows + 1:
        mat_rows.append([''] * col_count)

    mat_table = Table(mat_rows, colWidths=mat_col_widths, rowHeights=[0.7*cm] + [0.65*cm]*(len(mat_rows)-1))
    mat_style = TableStyle([
        # En-tête
        ('BACKGROUND', (0,0), (-1,0), LIGHT),
        ('LINEBELOW', (0,0), (-1,0), 1.5, GOLD),
        # Corps
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ])
    # Alternance couleur
    for r in range(2, len(mat_rows), 2):
        mat_style.add('BACKGROUND', (0,r), (-1,r), colors.HexColor('#fafafa'))
    mat_table.setStyle(mat_style)
    story.append(mat_table)
    story.append(Spacer(1, 5*mm))

    # ── SECTION : OBSERVATIONS GÉNÉRALES ─────────────────────────────────
    section_header3 = Table(
        [[Paragraph("OBSERVATIONS GÉNÉRALES", S['section_title'])]],
        colWidths=[page_width]
    )
    section_header3.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(section_header3)

    obs_text = bdc.observations_generales or ' '
    obs_table = Table(
        [[Paragraph(obs_text, S['obs_text'])]],
        colWidths=[page_width]
    )
    obs_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), WHITE),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 24),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(obs_table)
    story.append(Spacer(1, 6*mm))

    # ── SECTION : SIGNATURES ─────────────────────────────────────────────
    if getattr(bdc, 'est_garage', False):
        titre_gauche = "FOURNISSEUR"
        sub_gauche = "Signature"
    else:
        titre_gauche = "TRANSPORTEUR / CHAUFFEUR"
        sub_gauche = "Signature"

    sign_data = [[
        Paragraph(titre_gauche, S['sign_title']),
        Paragraph("DIRECTION TECHNIQUE", S['sign_title']),
    ],[
        Paragraph(sub_gauche, S['sign_sub']),
        Paragraph("Signature & Cachet", S['sign_sub']),
    ],[
        '', ''
    ],[
        '', ''
    ],[
        '', ''
    ]]
    sign_table = Table(sign_data,
                       colWidths=[page_width*0.5, page_width*0.5],
                       rowHeights=[0.7*cm, 0.5*cm, 1.4*cm, 0.8*cm, 0.2*cm])
    sign_table.setStyle(TableStyle([
        ('BOX', (0,0), (0,-1), 0.5, colors.HexColor('#cccccc')),
        ('BOX', (1,0), (1,-1), 0.5, colors.HexColor('#cccccc')),
        ('BACKGROUND', (0,0), (-1,1), LIGHT),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBELOW', (0,-1), (-1,-1), 1, GOLD),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 5*mm))

    # ── PIED DE PAGE ─────────────────────────────────────────────────────
    footer_line1 = f"{config.COMPANY_NAME}    {config.COMPANY_ADDRESS}    Tél : {config.COMPANY_TEL}"
    footer_line2 = f"NIF : {config.COMPANY_NIF}    RCCM : {config.COMPANY_RCCM}    {config.COMPANY_FORME}    Capital : {config.COMPANY_CAPITAL}"

    footer_table = Table(
        [[Paragraph(footer_line1, S['footer'])],
         [Paragraph(footer_line2, S['footer'])]],
        colWidths=[page_width]
    )
    footer_table.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 1, GOLD),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(footer_table)

    # ── GÉNÉRATION ───────────────────────────────────────────────────────
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
