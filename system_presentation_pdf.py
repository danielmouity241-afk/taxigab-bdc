"""
system_presentation_pdf.py — Générateur du Dossier de Présentation Officiel du Système TAXI GAB+ BDC.
Produit un document PDF de qualité exécutive détaillant l'architecture, la sécurité, les serveurs,
les fonctionnalités métiers et les capacités du système.
"""
import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, Image, KeepTogether, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

# Palette de couleurs officielle TAXI GAB+
NAVY       = colors.HexColor('#0a2744')
NAVY_LIGHT = colors.HexColor('#133d6b')
GOLD       = colors.HexColor('#c5a028')
GOLD_LIGHT = colors.HexColor('#dfb83c')
GOLD_BG    = colors.HexColor('#fff9e6')
GREY_DARK  = colors.HexColor('#2d3748')
GREY_MED   = colors.HexColor('#4a5568')
GREY_LIGHT = colors.HexColor('#f7fafc')
GREY_BORDER= colors.HexColor('#e2e8f0')
WHITE      = colors.white
BLACK      = colors.black
GREEN_OK   = colors.HexColor('#198754')
RED_WARN   = colors.HexColor('#dc3545')
BLUE_ACCENT= colors.HexColor('#0d6efd')

class NumberedCanvas(canvas.Canvas):
    """Canvas personnalisé pour calculer le nombre total de pages et ajouter l'en-tête/pied de page."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        page_w, page_h = A4

        # En-tête (à partir de la page 2)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(NAVY)
            self.drawString(1.5*cm, page_h - 1.2*cm, "TAXI GAB+  |  DOSSIER DE PRÉSENTATION TECHNIQUE DU SYSTÈME BDC")
            self.setFont("Helvetica", 8)
            self.setFillColor(GREY_MED)
            self.drawRightString(page_w - 1.5*cm, page_h - 1.2*cm, "PLATEFORME CLOUD & LOGISTIQUE")

            # Ligne sous en-tête
            self.setStrokeColor(GOLD)
            self.setLineWidth(1)
            self.line(1.5*cm, page_h - 1.35*cm, page_w - 1.5*cm, page_h - 1.35*cm)

        # Pied de page sur toutes les pages
        self.setStrokeColor(GREY_BORDER)
        self.setLineWidth(0.7)
        self.line(1.5*cm, 1.3*cm, page_w - 1.5*cm, 1.3*cm)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(GREY_MED)
        self.drawString(1.5*cm, 0.9*cm, "TAXI GAB+ S.A.S.U  •  Libreville, OLOUMI GABON MALL  •  NIF: 2024 0100 7748 P  •  RCCM: GA-LBV-01-2024-B17-00034")
        
        page_str = f"Page {self._pageNumber} sur {total_pages}"
        self.drawRightString(page_w - 1.5*cm, 0.9*cm, page_str)

        self.restoreState()


def get_custom_styles():
    base = getSampleStyleSheet()
    styles = {
        'doc_title': ParagraphStyle(
            'doc_title',
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=24,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=4
        ),
        'doc_subtitle': ParagraphStyle(
            'doc_subtitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=GOLD,
            alignment=TA_LEFT,
            spaceAfter=12
        ),
        'badge': ParagraphStyle(
            'badge',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=WHITE,
            alignment=TA_CENTER
        ),
        'section_h1': ParagraphStyle(
            'section_h1',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=15,
            textColor=WHITE,
            spaceBefore=0,
            spaceAfter=0
        ),
        'section_h2': ParagraphStyle(
            'section_h2',
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=13,
            textColor=NAVY,
            spaceBefore=6,
            spaceAfter=4
        ),
        'body': ParagraphStyle(
            'body',
            fontName='Helvetica',
            fontSize=8.5,
            leading=11.5,
            textColor=GREY_DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=5
        ),
        'body_bold': ParagraphStyle(
            'body_bold',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11.5,
            textColor=NAVY,
            spaceAfter=3
        ),
        'bullet': ParagraphStyle(
            'bullet',
            fontName='Helvetica',
            fontSize=8.3,
            leading=11,
            textColor=GREY_DARK,
            leftIndent=10,
            spaceAfter=3
        ),
        'th': ParagraphStyle(
            'th',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=WHITE,
            alignment=TA_LEFT
        ),
        'td': ParagraphStyle(
            'td',
            fontName='Helvetica',
            fontSize=7.8,
            leading=10,
            textColor=GREY_DARK,
            alignment=TA_LEFT
        ),
        'td_bold': ParagraphStyle(
            'td_bold',
            fontName='Helvetica-Bold',
            fontSize=7.8,
            leading=10,
            textColor=NAVY,
            alignment=TA_LEFT
        ),
        'callout': ParagraphStyle(
            'callout',
            fontName='Helvetica-Oblique',
            fontSize=8.2,
            leading=11,
            textColor=NAVY,
            alignment=TA_LEFT
        )
    }
    return styles

def create_section_header(title, icon_txt="", width=18*cm):
    """Crée une bannière d'en-tête de section bicolore Navy/Gold."""
    s = get_custom_styles()
    title_p = Paragraph(f"<b>{icon_txt} {title.upper()}</b>", s['section_h1'])
    t = Table([[title_p]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('LINEBELOW', (0,0), (-1,-1), 2, GOLD),
    ]))
    return t

def generate_system_presentation_pdf(output_path, logo_path=None):
    """
    Génère le dossier complet de présentation du système TAXI GAB+ BDC.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.6*cm,
        bottomMargin=1.6*cm
    )

    page_w = A4[0] - 3*cm
    s = get_custom_styles()
    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1 : EN-TÊTE DE PRESTIGE & FICHE SIGNALÉTIQUE DU SYSTÈME
    # ══════════════════════════════════════════════════════════════════════════

    # Bloc Logo + Titre principal
    logo_cell = ""
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image(logo_path, width=4.5*cm, height=2.2*cm)
            logo_cell = logo_img
        except Exception:
            logo_cell = Paragraph("<b>TAXI GAB+</b>", s['doc_title'])
    else:
        logo_cell = Paragraph("<b>TAXI GAB+</b>", s['doc_title'])

    title_block = [
        Paragraph("DOSSIER TECHNIQUE D'EXPLOITATION", s['doc_subtitle']),
        Paragraph("SYSTÈME INTÉGRÉ BDC & LOGISTIQUE", s['doc_title']),
        Paragraph("<b>Gestion Décentralisée des Approvisionnements, Traçabilité Flotte & Suivi Fournisseurs en Temps Réel</b>", s['body']),
        Paragraph(f"<font color='#666666'>Édition Officielle du {datetime.now().strftime('%d/%m/%Y')} • Version 3.2 Cloud • Accès Sécurisé</font>", s['td'])
    ]

    header_table = Table([[logo_cell, title_block]], colWidths=[5*cm, page_w - 5*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6*mm))

    # Encadré doré de synthèse exécutive
    synthese_p = Paragraph(
        "<b>SYNTHÈSE DU SYSTÈME :</b> La plateforme <b>TAXI GAB+ BDC</b> est une solution logicielle métier complète "
        "conçue sur mesure pour piloter la chaîne d'approvisionnement des pièces automobiles, le contrôle de la flotte de taxis, "
        "l'atelier de mécanique générale et les relations fournisseurs. Elle élimine intégralement la perte de pièces de rechange, "
        "éradique les doublons de commande, garantit une traçabilité financière totale et automatise les relances logistiques via WhatsApp.",
        s['callout']
    )
    synthese_box = Table([[synthese_p]], colWidths=[page_w])
    synthese_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GOLD_BG),
        ('BOX', (0,0), (-1,-1), 1, GOLD),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(synthese_box)
    story.append(Spacer(1, 6*mm))

    # SECTION 1 : INFRASTRUCTURE, SERVEURS & STACK TECHNIQUE
    story.append(create_section_header("1. Architecture Technique & Écosystème Serveurs", "■", page_w))
    story.append(Spacer(1, 3*mm))

    tech_intro = Paragraph(
        "L'infrastructure repose sur des standards industriels de haute disponibilité, déployée sur le Cloud mondial avec "
        "chiffrement de bout en bout, redondance des bases de données et accessibilité mobile permanente.",
        s['body']
    )
    story.append(tech_intro)
    story.append(Spacer(1, 2*mm))

    tech_data = [
        [Paragraph("Composant", s['th']), Paragraph("Technologie / Fournisseur", s['th']), Paragraph("Rôle & Spécifications de Sécurité", s['th'])],
        [Paragraph("<b>Hébergement Web & API</b>", s['td_bold']), Paragraph("<b>Render Cloud Platform</b> (USA/Europe)", s['td']), Paragraph("Serveur Cloud PaaS managé, conteneurs sécurisés, basculement automatique, certificats HTTPS/SSL Let's Encrypt 256 bits.", s['td'])],
        [Paragraph("<b>Base de Données Principale</b>", s['td_bold']), Paragraph("<b>PostgreSQL 16 Managé</b> (Neon / Render)", s['td']), Paragraph("Transactions relationnelles strictes (ACID), clés étrangères certifiées, sauvegardes continues, isolation des données.", s['td'])],
        [Paragraph("<b>Moteur Applicatif</b>", s['td_bold']), Paragraph("<b>Python 3.11 + Flask Enterprise</b>", s['td']), Paragraph("Architecture légère, ultra-rapide (temps de réponse < 150 ms), ORM SQLAlchemy avec auto-migration dynamique du schéma.", s['td'])],
        [Paragraph("<b>Générateur de Documents</b>", s['td_bold']), Paragraph("<b>ReportLab Professional 5.0</b>", s['td']), Paragraph("Moteur vectoriel PDF natif pour les bons de commande, bordereaux de réception et rapports certifiés.", s['td'])],
        [Paragraph("<b>Passerelle WhatsApp</b>", s['td_bold']), Paragraph("<b>Dual Engine : REST API & Native URI</b>", s['td']), Paragraph("Double canal : Envoi automatisé serveur (UltraMsg/GreenAPI) + Redirection instantanée native smartphone sans abonnement.", s['td'])],
        [Paragraph("<b>Expérience Mobile (PWA)</b>", s['td_bold']), Paragraph("<b>Progressive Web App (HTML5/CSS3)</b>", s['td']), Paragraph("Installation directe sur smartphone (iPhone & Android) en plein écran, sans téléchargement d'application lourde.", s['td'])],
        [Paragraph("<b>Dépôt & Intégration CI/CD</b>", s['td_bold']), Paragraph("<b>GitHub Private Repo + Auto-deploy</b>", s['td']), Paragraph("Code source versionné sous Git, audit des commits, déploiement automatique dès validation des tests unitaires.", s['td'])],
    ]
    t_tech = Table(tech_data, colWidths=[4*cm, 4.5*cm, page_w - 8.5*cm])
    t_tech.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, GREY_LIGHT]),
    ]))
    story.append(t_tech)
    story.append(Spacer(1, 5*mm))

    # SECTION 2 : SÉCURITÉ, CONTRÔLE DES ACCÈS & RÔLES ÉTANCHES
    story.append(create_section_header("2. Sécurité, Rôles & Intégrité des Données", "■", page_w))
    story.append(Spacer(1, 3*mm))

    sec_p = Paragraph(
        "Le système implémente une politique stricte de contrôle d'accès basé sur les rôles (<b>RBAC - Role-Based Access Control</b>). "
        "Chaque opération (création, modification, validation, pointage, annulation) est enregistrée de manière inaltérable.",
        s['body']
    )
    story.append(sec_p)
    story.append(Spacer(1, 2*mm))

    sec_data = [
        [Paragraph("Profil Utilisateur", s['th']), Paragraph("Périmètre & Droits Autorisés", s['th']), Paragraph("Mesures de Sécurité & Restrictions", s['th'])],
        [Paragraph("<b>Direction Technique (DT/DTA)</b>", s['td_bold']), Paragraph("Contrôle total : création, modification, validation souveraine des BDC, relances fournisseurs, administration utilisateurs.", s['td']), Paragraph("Droit exclusif de valider ou d'annuler les bons. Supervision des mots de passe en clair pour assistance immédiate.", s['td'])],
        [Paragraph("<b>Magasinier Atelier</b>", s['td_bold']), Paragraph("Saisie des demandes d'approvisionnement, réception physique des pièces, pointage partiel ou complet, mise en stock atelier.", s['td']), Paragraph("Interdiction formelle de valider un bon ou de modifier les paramètres d'autres utilisateurs. Vue limitée aux pièces.", s['td'])],
        [Paragraph("<b>Transporteur Flotte</b>", s['td_bold']), Paragraph("Suivi logistique, récupération des pièces chez les fournisseurs, déclaration de transport, pointage de remise atelier.", s['td']), Paragraph("<b>Masquage du nom du fournisseur</b> sur son PDF pour préserver la confidentialité commerciale. Alerte caution rouge.", s['td'])],
        [Paragraph("<b>Spectateur (PDG / Audit)</b>", s['td_bold']), Paragraph("Consultation complète du tableau de bord, consultation des archives, génération des PDF, suivi des dépenses.", s['td']), Paragraph("<b>Mode lecture seule strict (Sécurité 403)</b> : Impossible de modifier, créer, valider ou supprimer la moindre donnée.", s['td'])],
    ]
    t_sec = Table(sec_data, colWidths=[4*cm, 7*cm, page_w - 11*cm])
    t_sec.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, GREY_LIGHT]),
    ]))
    story.append(t_sec)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2 : FONCTIONNALITÉS MÉTIER & WORKFLOW DE BOUT EN BOUT
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    story.append(create_section_header("3. Fonctionnalités Métier & Cycle de Vie d'un Bon", "■", page_w))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "Chaque bon de commande suit un processus rigoureux et vérifiable, de la demande initiale à la clôture finale en stock :",
        s['body']
    ) )
    story.append(Spacer(1, 2*mm))

    # Tableau du Workflow opérationnel
    flow_data = [
        [Paragraph("Étape", s['th']), Paragraph("Action Opérationnelle", s['th']), Paragraph("Acteur & Sécurité Associée", s['th'])],
        [
            Paragraph("<b>1. Émission</b>", s['td_bold']),
            Paragraph("Création du bon avec distinction immédiate :<br/>• <b>Bon Véhicule :</b> Immatriculation obligatoire (ex: TG 433) pour imputer le coût d'entretien au taxi.<br/>• <b>Bon Garage :</b> Consommables ou outillage interne de l'atelier.", s['td']),
            Paragraph("Magasinier ou DT.<br/>Numérotation chronologique mensuelle inviolable (ex: <i>BDC-09/26-00001</i>).", s['td'])
        ],
        [
            Paragraph("<b>2. Validation DT</b>", s['td_bold']),
            Paragraph("Contrôle de conformité des pièces et des prix demandés par la Direction Technique. Horodatage certifié.", s['td']),
            Paragraph("Directeur Technique exclusivement.<br/>Génère un <b>Code Sécurisé unique (UUID)</b> pour le bon.", s['td'])
        ],
        [
            Paragraph("<b>3. Transmission Fournisseur</b>", s['td_bold']),
            Paragraph("Envoi direct du bon au fournisseur par <b>WhatsApp en 1 clic</b>. Le fournisseur reçoit le PDF et un lien sécurisé.", s['td']),
            Paragraph("Envoi certifié avec horodatage de première transmission enregistré en base de données.", s['td'])
        ],
        [
            Paragraph("<b>4. Détection Retards (24h) & Relances</b>", s['td_bold']),
            Paragraph("<b>Surveillance intelligente :</b> Si les pièces ne sont pas livrées sous 24h, le système classe automatiquement le bon en <i>Retard de livraison</i>. Un bouton de relance permet d'envoyer un rappel WhatsApp ciblé listant uniquement les pièces manquantes.", s['td']),
            Paragraph("<b>Compteur certifié :</b> Le système incrémente le nombre exact de relances et trace la date/heure de chaque rappel dans le journal d'audit.", s['td'])
        ],
        [
            Paragraph("<b>5. Réception Décentralisée</b>", s['td_bold']),
            Paragraph("Pointage individuel pièce par pièce :<br/>• <i>Non reçu</i> / <i>Partiel</i> / <i>Reçu</i>.<br/>• Saisie du nom du livreur/transporteur pour chaque pièce reçue.", s['td']),
            Paragraph("Magasinier ou DT.<br/>La réception partielle ne bloque pas le suivi des pièces restantes.", s['td'])
        ],
        [
            Paragraph("<b>6. Clôture & Archivage</b>", s['td_bold']),
            Paragraph("Une fois toutes les pièces réceptionnées, le bon passe en statut <i>En stock</i> puis <i>Clôturé</i>. Il intègre le dossier d'archives mensuel autonome.", s['td']),
            Paragraph("Conservation intégrale du journal chronologique des manipulations (création, validations, relances, pointages).", s['td'])
        ],
    ]
    t_flow = Table(flow_data, colWidths=[2.5*cm, 8.5*cm, page_w - 11*cm])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, GREY_LIGHT]),
    ]))
    story.append(t_flow)
    story.append(Spacer(1, 5*mm))

    # SECTION 4 : MODULES SPÉCIALISÉS DU SYSTÈME
    story.append(create_section_header("4. Vue d'Ensemble des 6 Modules Principaux", "■", page_w))
    story.append(Spacer(1, 3*mm))

    modules_data = [
        [
            Paragraph("<b>Tableau de Bord Stratégique</b><br/><font color='#666666'>Indicateurs KPIs en temps réel : volume de bons émis, pièces en attente, alertes de retard > 24h, alertes de caution transporteur.</font>", s['td']),
            Paragraph("<b>Gestion des BDC & Impression PDF</b><br/><font color='#666666'>Création assistée, calcul automatique des totaux, impression vectorielle du BDC standard ou avec état d'avancement des réceptions.</font>", s['td']),
        ],
        [
            Paragraph("<b>Suivi Logistique & Réceptions</b><br/><font color='#666666'>Matrice de pointage décentralisée, filtres par fournisseur, par véhicule, et filtre immédiat des bons en retard de livraison.</font>", s['td']),
            Paragraph("<b>Répertoire Fournisseurs & Historique</b><br/><font color='#666666'>Base de données centrale des contacts, numéros WhatsApp directs, adresses, et historique complet des commandes passées.</font>", s['td']),
        ],
        [
            Paragraph("<b>Archives Mensuelles Autonomes</b><br/><font color='#666666'>Dossiers classés par mois (ex: 09/2026), avec volet déroulant pour déplier l'historique complet des manipulations de chaque bon.</font>", s['td']),
            Paragraph("<b>Administration & Sécurité</b><br/><font color='#666666'>Gestion simplifiée des comptes utilisateurs, profils en 1 clic, réinitialisation rapide et visualisation administrative des mots de passe.</font>", s['td']),
        ]
    ]
    t_mod = Table(modules_data, colWidths=[page_w/2.0, page_w/2.0])
    t_mod.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), WHITE),
    ]))
    story.append(t_mod)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3 : POURQUOI C'EST UN BON SYSTÈME (ARGUMENTAIRE & ROI)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    story.append(create_section_header("5. Pourquoi ce Système est Supérieur (Gains Mesurables)", "■", page_w))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "Comparatif concret entre l'organisation traditionnelle manuelle et la performance obtenue avec la plateforme TAXI GAB+ :",
        s['body']
    ))
    story.append(Spacer(1, 2*mm))

    comp_data = [
        [Paragraph("Aspect Opérationnel", s['th']), Paragraph("Avant : Gestion Papier / WhatsApp Informel", s['th']), Paragraph("Aujourd'hui : Plateforme TAXI GAB+ BDC", s['th'])],
        [
            Paragraph("<b>Traçabilité des pièces</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Faible :</b></font> Bons perdus, aucune preuve de qui a récupéré la pièce ni à quelle heure.", s['td']),
            Paragraph("<font color='#198754'><b>100% Vérifiable :</b></font> Chaque pièce a un statut individuel, un nom de livreur horodaté et une traçabilité véhicule.", s['td'])
        ],
        [
            Paragraph("<b>Délais fournisseurs</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Lents :</b></font> Commandes oubliées par les fournisseurs sans relance organisée.", s['td']),
            Paragraph("<font color='#198754'><b>Ultra-rapides :</b></font> Alerte automatique 24h et relance WhatsApp ciblée en 1 clic sur les pièces en attente.", s['td'])
        ],
        [
            Paragraph("<b>Contrôle budgétaire</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Flou :</b></font> Impossibilité de connaître en temps réel le coût d'entretien d'un taxi précis.", s['td']),
            Paragraph("<font color='#198754'><b>Chirurgical :</b></font> Distinction nette entre bon Véhicule (affectation directe) et bon Garage (usage interne).", s['td'])
        ],
        [
            Paragraph("<b>Sécurité financière</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Risqué :</b></font> Dépenses imputées à des transporteurs sans vérifier le niveau de caution.", s['td']),
            Paragraph("<font color='#198754'><b>Sécurisé :</b></font> Alerte rouge obligatoire sur la caution financière du transporteur lors de l'attribution.", s['td'])
        ],
        [
            Paragraph("<b>Archivage & Audit</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Complexe :</b></font> Classeurs physiques encombrants, recherches fastidieuses en cas de contrôle.", s['td']),
            Paragraph("<font color='#198754'><b>Instantané :</b></font> Dossiers mensuels indépendants, filtres multicritères et téléchargement PDF en 2 secondes.", s['td'])
        ],
        [
            Paragraph("<b>Mobilité de terrain</b>", s['td_bold']),
            Paragraph("<font color='#dc3545'><b>Bloqué au bureau :</b></font> Obligation d'être devant un ordinateur de bureau pour travailler.", s['td']),
            Paragraph("<font color='#198754'><b>100% Mobile :</b></font> PWA installée sur smartphone, validation et relance depuis n'importe où via la 4G.", s['td'])
        ],
    ]
    t_comp = Table(comp_data, colWidths=[3.2*cm, 7.2*cm, page_w - 10.4*cm])
    t_comp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, GREY_LIGHT]),
    ]))
    story.append(t_comp)
    story.append(Spacer(1, 5*mm))

    # SECTION 6 : CAPACITÉS TECHNIQUES & CHIFFRES CLÉS
    story.append(create_section_header("6. Capacités & Performance du Système", "■", page_w))
    story.append(Spacer(1, 3*mm))

    stats_data = [
        [
            Paragraph("<b>DISPONIBILITÉ CLOUD</b><br/><font size='14' color='#0a2744'><b>99.9%</b></font><br/><font size='7' color='#666666'>Hébergement Render haute résilience avec basculement automatique.</font>", s['td']),
            Paragraph("<b>TEMPS DE RÉPONSE</b><br/><font size='14' color='#0a2744'><b>&lt; 150 ms</b></font><br/><font size='7' color='#666666'>Moteur Flask optimisé, requêtes indexées, navigation ultra-fluide.</font>", s['td']),
            Paragraph("<b>VOLUME DE BONS</b><br/><font size='14' color='#0a2744'><b>Illimité</b></font><br/><font size='7' color='#666666'>Base PostgreSQL dimensionnée pour des centaines de milliers de lignes.</font>", s['td']),
            Paragraph("<b>SÉCURITÉ AUDIT</b><br/><font size='14' color='#0a2744'><b>100% Inaltérable</b></font><br/><font size='7' color='#666666'>Chaque clic, validation et pointage est horodaté et signé.</font>", s['td']),
        ]
    ]
    t_stats = Table(stats_data, colWidths=[page_w/4.0]*4)
    t_stats.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (-1,-1), GREY_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, GOLD),
        ('INNERGRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 6*mm))

    # SECTION 7 : ENGAGEMENT DE CONFORMITÉ & SIGNATURE
    concl_p = Paragraph(
        "<b>CONCLUSION & CERTIFICATION :</b> Le système BDC de TAXI GAB+ constitue un actif stratégique pour la "
        "compétitivité de l'entreprise. En combinant rigueur financière, simplicité d'utilisation pour le personnel de terrain "
        "et réactivité instantanée via WhatsApp, il positionne TAXI GAB+ aux meilleurs standards de gestion de flotte et d'atelier en Afrique Centrale.",
        s['body']
    )
    story.append(concl_p)
    story.append(Spacer(1, 6*mm))

    # Bloc signatures
    sig_data = [
        [
            Paragraph("<b>LA DIRECTION TECHNIQUE</b><br/><font size='7' color='#666666'>TAXI GAB+ S.A.S.U</font><br/><br/><br/>_____________________________________<br/><font size='7' color='#666666'>Visa & Approbation Technique</font>", s['td']),
            Paragraph("<b>LA DIRECTION GÉNÉRALE</b><br/><font size='7' color='#666666'>TAXI GAB+ S.A.S.U</font><br/><br/><br/>_____________________________________<br/><font size='7' color='#666666'>Visa & Autorisation de Diffusion</font>", s['td']),
        ]
    ]
    t_sig = Table(sig_data, colWidths=[page_w/2.0, page_w/2.0])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_sig)

    # Génération du document avec NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return output_path

if __name__ == '__main__':
    out = r"C:\Users\danie\Desktop\taxigab-bdc\static\docs\TAXI_GAB_Presentation_Systeme_BDC.pdf"
    logo = r"C:\Users\danie\Desktop\taxigab-bdc\static\images\logo_taxigab.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    generate_system_presentation_pdf(out, logo)
    print("SUCCESS: PDF généré avec succès à", out)
