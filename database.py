from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

db = SQLAlchemy()

# ─────────────────────────────────────────
# UTILISATEURS
# ─────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    username           = db.Column(db.String(64), unique=True, nullable=False)
    password_hash      = db.Column(db.String(256), nullable=False)
    mot_de_passe_clair = db.Column(db.String(128), nullable=True)  # Mot de passe lisible pour l'administrateur
    nom_complet        = db.Column(db.String(128), nullable=False)
    role               = db.Column(db.String(128), nullable=False)  # Titre libre manuel (ex: Président Directeur Général, Magasinier...)
    actif              = db.Column(db.Boolean, default=True)
    date_creation      = db.Column(db.DateTime, default=datetime.utcnow)

    # Permissions granulaires personnalisables
    peut_creer_bdc           = db.Column(db.Boolean, default=False)
    peut_valider_dt          = db.Column(db.Boolean, default=False)
    peut_gerer_stock         = db.Column(db.Boolean, default=False)
    peut_recuperer           = db.Column(db.Boolean, default=False)
    peut_cloturer            = db.Column(db.Boolean, default=False)
    peut_annuler             = db.Column(db.Boolean, default=False)
    peut_gerer_utilisateurs  = db.Column(db.Boolean, default=False)
    peut_voir_historique     = db.Column(db.Boolean, default=False)  # Accès à l'historique et la traçabilité
    peut_voir_archives       = db.Column(db.Boolean, default=False)  # Accès aux archives mensuelles
    est_spectateur           = db.Column(db.Boolean, default=False)  # Consultation totale et impression sans modification
    peut_valider_fournisseur = db.Column(db.Boolean, default=False)  # Validation bon & délais par le fournisseur

    # Relations
    bons_crees    = db.relationship('BonDeCommande', foreign_keys='BonDeCommande.createur_id', backref='createur', lazy=True)
    bons_valides  = db.relationship('BonDeCommande', foreign_keys='BonDeCommande.validateur_dt_id', backref='validateur_dt', lazy=True)
    actions       = db.relationship('HistoriqueAction', backref='acteur', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.mot_de_passe_clair = password

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def profil_simple_badge(self):
        if self.est_spectateur:
            return {'label': 'Spectateur (Lecture seule)', 'color': 'info', 'icon': 'bi-eye-fill'}
        if self.role in ('DT', 'Directeur Technique') or (self.peut_valider_dt and self.peut_gerer_utilisateurs):
            return {'label': 'Direction Technique (Admin)', 'color': 'primary', 'icon': 'bi-shield-shaded'}
        if self.role in ('DTA', 'Directeur Technique Adjoint'):
            return {'label': 'Dir. Technique Adjointe', 'color': 'primary', 'icon': 'bi-shield-check'}
        if self.role in ('fournisseur', 'Fournisseur') or getattr(self, 'peut_valider_fournisseur', False):
            return {'label': 'Fournisseur (Partenaire)', 'color': 'warning text-dark', 'icon': 'bi-shop'}
        if self.role in ('magasinier', 'Magasinier') or self.peut_gerer_stock:
            return {'label': 'Magasinier / Stock', 'color': 'success', 'icon': 'bi-box-seam-fill'}
        if self.role in ('transporteur', 'Transporteur') or self.peut_recuperer:
            return {'label': 'Transporteur / Chauffeur', 'color': 'purple', 'icon': 'bi-truck'}
        return {'label': self.role_label, 'color': 'secondary', 'icon': 'bi-person-badge'}

    @property
    def role_label(self):
        labels = {
            'DT': 'Directeur Technique',
            'DTA': 'Dir. Technique Adjoint',
            'magasinier': 'Magasinier',
            'fournisseur': 'Fournisseur',
            'transporteur': 'Transporteur',
            'DG': 'Directeur Général',
            'PDG': 'Président Directeur Général',
        }
        return labels.get(self.role, self.role or 'Utilisateur')

    @property
    def is_fournisseur(self):
        if not self.actif:
            return False
        return bool(self.role in ('fournisseur', 'Fournisseur') or getattr(self, 'peut_valider_fournisseur', False))

    @property
    def is_magasinier(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.role in ('magasinier', 'Magasinier') or self.peut_gerer_stock)

    @property
    def can_valider_fournisseur(self):
        if not self.actif:
            return False
        # Le fournisseur et le DT (super-admin pour test/assistance) peuvent valider côté fournisseur
        return bool(self.is_fournisseur or self.is_directeur_technique or self.role in ('DT', 'Directeur Technique'))

    @property
    def can_creer_bdc(self):
        if not self.actif or self.est_spectateur:
            return False
        # Seul le DT ou un collaborateur expressément habilité par le DT (peut_creer_bdc=True) peut écrire un BDC
        if self.role in ('DT', 'Directeur Technique') or self.is_directeur_technique:
            return True
        return bool(self.peut_creer_bdc)

    @property
    def can_valider_dt(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.role in ('DT', 'Directeur Technique') or self.is_directeur_technique or self.peut_valider_dt)

    @property
    def is_directeur_technique(self):
        if not self.actif or self.est_spectateur:
            return False
        return self.role in ('DT', 'Directeur Technique') or bool(self.peut_valider_dt and self.peut_gerer_utilisateurs)

    @property
    def can_gerer_stock(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_gerer_stock or self.role in ('DT', 'DTA', 'magasinier', 'Directeur Technique', 'Directeur Technique Adjoint', 'Magasinier'))

    def can_annuler(self, bdc=None):
        if not self.actif or self.est_spectateur:
            return False
        if bdc and getattr(bdc, 'statut', None) == 'annulee':
            return False
        # Pouvoir exclusif du Directeur Technique (DT) d'annuler les bons (y compris déjà validés)
        return bool(self.role in ('DT', 'Directeur Technique') or self.is_directeur_technique)

    @property
    def can_cloturer(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_cloturer or self.role in ('DT', 'DTA', 'Directeur Technique', 'Directeur Technique Adjoint'))

    @property
    def can_recuperer(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_recuperer or self.role in ('DT', 'DTA', 'magasinier', 'transporteur', 'Directeur Technique', 'Magasinier', 'Transporteur'))

    @property
    def can_gerer_utilisateurs(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_gerer_utilisateurs or self.role in ('DT', 'Directeur Technique'))

    @property
    def can_voir_historique(self):
        if not self.actif:
            return False
        return bool(self.peut_voir_historique or self.est_spectateur or self.role in ('DT', 'Directeur Technique', 'DTA', 'Directeur Technique Adjoint'))

    @property
    def can_voir_archives(self):
        if not self.actif:
            return False
        return bool(self.peut_voir_archives or self.est_spectateur or self.role in ('DT', 'Directeur Technique', 'DTA', 'Directeur Technique Adjoint'))

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


# ─────────────────────────────────────────
# STATUTS BON DE COMMANDE
# ─────────────────────────────────────────
STATUTS_BDC = {
    'en_attente':              'En attente',
    'validee':                 'Validée',
    'refusee':                 'Refusée',
    'livree':                  'Livrée',
    'en_stock':                'En stock',
    'recuperee_transporteur':  'Récupérée par le transporteur',
    'cloturee':                'Clôturée',
    'annulee':                 'Annulée',
}

STATUTS_COULEURS = {
    'en_attente':              'warning',
    'validee':                 'primary',
    'refusee':                 'danger',
    'livree':                  'info',
    'en_stock':                'success',
    'recuperee_transporteur':  'purple',
    'cloturee':                'secondary',
    'annulee':                 'dark',
}

class BonDeCommande(db.Model):
    __tablename__ = 'bons_de_commande'
    id                       = db.Column(db.Integer, primary_key=True)
    numero                   = db.Column(db.Integer, nullable=False, index=True)
    date_creation            = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Type de bon : 'vehicule' ou 'garage'
    type_bon                 = db.Column(db.String(32), default='vehicule', nullable=False)
    dossier_assurance        = db.Column(db.String(128), nullable=True)  # Réf / Nom assurance (si type_bon == 'assurance')

    # Demandeur
    createur_id              = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    demandeur_nom            = db.Column(db.String(128), nullable=False)
    service_departement      = db.Column(db.String(128))

    # Fournisseur
    fournisseur              = db.Column(db.String(128), nullable=True)
    fournisseur_whatsapp     = db.Column(db.String(64), nullable=True)
    code_securise            = db.Column(db.String(64), unique=True, index=True, nullable=True)

    # Véhicule & Transporteur (uniquement si type_bon == 'vehicule')
    vehicule_nom             = db.Column(db.String(64))   # ex: TG 433
    vehicule_immatriculation = db.Column(db.String(64))   # ex: LH-819-AA
    transporteur             = db.Column(db.String(128))  # Transporteur / Chauffeur concerné

    # Observations générales
    observations_generales   = db.Column(db.Text)

    # Statut
    statut                   = db.Column(db.String(32), default='en_attente', nullable=False)

    # Validation DT
    validateur_dt_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    date_validation_dt       = db.Column(db.DateTime, nullable=True)
    motif_refus_dt           = db.Column(db.Text, nullable=True)

    # Livraison par le fournisseur au garage
    date_livraison           = db.Column(db.DateTime, nullable=True)
    receptionniste_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Mise en stock
    date_en_stock            = db.Column(db.DateTime, nullable=True)
    magasinier_stock_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Récupération par le transporteur
    date_recuperation        = db.Column(db.DateTime, nullable=True)
    nom_recuperateur         = db.Column(db.String(128), nullable=True)

    # Clôture / Annulation
    date_cloture             = db.Column(db.DateTime, nullable=True)
    date_annulation          = db.Column(db.DateTime, nullable=True)
    motif_annulation         = db.Column(db.Text, nullable=True)
    annulateur_id            = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Envoi WhatsApp & Relances
    whatsapp_envoye          = db.Column(db.Boolean, default=False)
    date_envoi_whatsapp      = db.Column(db.DateTime, nullable=True)
    nb_relances_whatsapp     = db.Column(db.Integer, default=0, nullable=False)
    date_derniere_relance    = db.Column(db.DateTime, nullable=True)

    # Validation Fournisseur
    fournisseur_a_valide     = db.Column(db.Boolean, default=False)
    date_validation_fournisseur = db.Column(db.DateTime, nullable=True)
    validateur_fournisseur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Livraison déclarée par le fournisseur
    fournisseur_a_livre      = db.Column(db.Boolean, default=False)
    date_livraison_fournisseur = db.Column(db.DateTime, nullable=True)
    livreur_fournisseur_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    note_livraison_fournisseur = db.Column(db.String(256), nullable=True)

    # Réception physique certifiée par le magasinier à la Direction Technique
    reception_magasinier_validee = db.Column(db.Boolean, default=False)
    date_reception_magasinier = db.Column(db.DateTime, nullable=True)
    magasinier_reception_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    note_reception_magasinier = db.Column(db.Text, nullable=True)

    # Impressions & Traçabilité des Doublons
    nb_impressions           = db.Column(db.Integer, default=0, nullable=False)
    date_derniere_impression = db.Column(db.DateTime, nullable=True)
    dernier_imprimeur_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relations
    lignes     = db.relationship('LigneBDC', backref='bon', lazy=True,
                                  cascade='all, delete-orphan', order_by='LigneBDC.ordre')
    historique = db.relationship('HistoriqueAction', backref='bon', lazy=True,
                                  cascade='all, delete-orphan',
                                  order_by='HistoriqueAction.timestamp.desc()')
    receptionniste   = db.relationship('User', foreign_keys=[receptionniste_id])
    magasinier_stock = db.relationship('User', foreign_keys=[magasinier_stock_id])
    annulateur       = db.relationship('User', foreign_keys=[annulateur_id])
    dernier_imprimeur = db.relationship('User', foreign_keys=[dernier_imprimeur_id])
    validateur_fournisseur = db.relationship('User', foreign_keys=[validateur_fournisseur_id])
    livreur_fournisseur   = db.relationship('User', foreign_keys=[livreur_fournisseur_id])
    magasinier_reception  = db.relationship('User', foreign_keys=[magasinier_reception_id])

    @property
    def numero_affiche(self):
        date_ref = self.date_creation or datetime.utcnow()
        return f"BDC-{date_ref.strftime('%m/%y')}-{self.numero:05d}"

    @property
    def est_garage(self):
        return self.type_bon == 'garage'

    @property
    def est_assurance(self):
        return self.type_bon == 'assurance'

    @property
    def type_label(self):
        if self.est_garage:
            return "Garage (Interne)"
        elif self.est_assurance:
            return "Assurance"
        return "Véhicule"


    @property
    def statut_label(self):
        return STATUTS_BDC.get(self.statut, self.statut)

    @property
    def statut_couleur(self):
        return STATUTS_COULEURS.get(self.statut, 'secondary')

    @property
    def pieces_recues(self):
        return sum(1 for l in self.lignes if l.statut_reception == 'recu')

    @property
    def total_pieces(self):
        return len(self.lignes)

    @property
    def pieces_en_attente(self):
        """Liste des lignes de pièces non encore reçues ou partiellement reçues."""
        return [l for l in self.lignes if l.statut_reception != 'recu' or (l.quantite_recue or 0) < l.quantite]

    @property
    def total_pieces_en_attente(self):
        return len(self.pieces_en_attente)

    @property
    def est_completement_recu(self):
        return len(self.pieces_en_attente) == 0 and len(self.lignes) > 0

    @property
    def date_reference_transmission(self):
        """Date de transmission / validation ou création."""
        return self.date_validation_dt or self.date_envoi_whatsapp or self.date_creation

    @property
    def delai_ecoule_heures(self):
        """Nombre d'heures écoulées depuis la validation/transmission."""
        ref = self.date_reference_transmission
        if not ref:
            return 0
        diff = datetime.utcnow() - ref
        return max(0, int(diff.total_seconds() // 3600))

    @property
    def pieces_en_attente_sans_promesse(self):
        """Pièces en attente qui n'ont pas de promesse de délai active."""
        return [l for l in self.pieces_en_attente if not getattr(l, 'est_sous_delai_actif', False)]

    @property
    def est_sous_promesse_attente(self):
        """Vrai si le bon a été classé au niveau des promesses d'attente fournisseur (1 sem, 2 sem, 3 sem, 1 mois...)
        et qu'aucune de ses pièces n'a dépassé son échéance convenue."""
        if not self.pieces_en_attente:
            return False
        if self.a_pieces_avec_delai and not self.a_pieces_en_retard_delai:
            return True
        return False

    @property
    def est_en_retard_24h(self):
        """Vrai si validé depuis +24h, non clôturé/annulé, pièces en attente,
        ET NON classé sous promesse d'attente (délai fournisseur 1 sem, 2 sem, 3 sem, 1 mois...).
        Dès qu'une promesse d'attente est enregistrée, le bon ne s'affiche plus dans les retards."""
        if self.statut in ('refusee', 'cloturee', 'annulee'):
            return False
        if self.statut not in ('validee', 'livree', 'en_stock', 'recuperee_transporteur'):
            return False
        if not self.pieces_en_attente:
            return False

        # Si le bon est classé avec des promesses d'attente (1 sem, 2 sem, 3 sem, 1 mois...)
        # et que l'échéance n'est pas encore dépassée : IL NE S'AFFICHE PLUS DANS LES RETARDS !
        if self.est_sous_promesse_attente:
            return False

        # Si toutes les pièces en attente ont un délai convenu non échu : pas de retard
        if not self.pieces_en_attente_sans_promesse:
            return False

        return self.delai_ecoule_heures >= 24

    @property
    def a_pieces_avec_delai(self):
        """Vrai si au moins une pièce a un délai de livraison fixé par le fournisseur."""
        return any(l.a_delai for l in self.lignes)

    @property
    def lignes_avec_delai(self):
        """Liste des pièces ayant un délai de livraison fixé."""
        return [l for l in self.lignes if l.a_delai]

    @property
    def a_pieces_en_retard_delai(self):
        """Vrai si au moins une pièce a dépassé la date limite promise par le fournisseur."""
        return any(l.est_en_retard_delai for l in self.lignes)

    def ensure_code_securise(self):
        if not self.code_securise:
            self.code_securise = secrets.token_urlsafe(16)
        return self.code_securise

    def __repr__(self):
        return f'<BDC N°{self.numero_affiche} [{self.statut}]>'


# ─────────────────────────────────────────
# LIGNES DU BON DE COMMANDE
# ─────────────────────────────────────────
class LigneBDC(db.Model):
    __tablename__ = 'lignes_bdc'
    id               = db.Column(db.Integer, primary_key=True)
    bdc_id           = db.Column(db.Integer, db.ForeignKey('bons_de_commande.id'), nullable=False)
    ordre            = db.Column(db.Integer, nullable=False)
    designation      = db.Column(db.String(256), nullable=False)
    quantite         = db.Column(db.Integer, nullable=False, default=1)
    observations     = db.Column(db.String(256))
    # Suivi réception & livraison
    livreur_nom      = db.Column(db.String(128), nullable=True)  # Sous-traitant ou fournisseur livreur effectif
    statut_reception = db.Column(db.String(32), default='non_recu')  # non_recu / recu / partiel
    quantite_recue   = db.Column(db.Integer, default=0)
    date_reception   = db.Column(db.DateTime, nullable=True)
    note_reception   = db.Column(db.String(256))

    # Délais promis par le fournisseur
    delai_livraison_texte = db.Column(db.String(64), nullable=True)   # ex: "Dans 1 semaine", "Dans 2 semaines", "Dans 3 semaines", "Dans 1 mois"
    date_livraison_prevue = db.Column(db.Date, nullable=True)        # Date d'échéance calculée ou choisie
    date_definition_delai = db.Column(db.DateTime, nullable=True)
    motif_delai           = db.Column(db.String(256), nullable=True)

    @property
    def statut_reception_label(self):
        labels = {
            'non_recu': 'Non reçu',
            'recu':     'Reçu',
            'partiel':  'Partiel',
        }
        return labels.get(self.statut_reception, self.statut_reception)

    @property
    def statut_reception_couleur(self):
        couleurs = {
            'non_recu': 'danger',
            'recu':     'success',
            'partiel':  'warning',
        }
        return couleurs.get(self.statut_reception, 'secondary')

    @property
    def quantite_restante(self):
        """Nombre d'unités de cette pièce encore en attente de réception."""
        return max(0, (self.quantite or 1) - (self.quantite_recue or 0))

    @property
    def a_delai(self):
        """Vrai si un délai a été renseigné sur cette ligne."""
        return bool(self.date_livraison_prevue or self.delai_livraison_texte)

    @property
    def est_sous_delai_actif(self):
        """Vrai si un délai a été fixé (1 sem, 2 sem, 3 sem, 1 mois...) et que la date limite n'est pas dépassée."""
        if not self.a_delai or self.statut_reception == 'recu':
            return False
        from datetime import date
        if self.date_livraison_prevue:
            return date.today() <= self.date_livraison_prevue
        return True

    @property
    def est_en_retard_delai(self):
        """Vrai si une date limite a été fixée, dépassée, et la pièce n'est pas encore reçue."""
        if not self.date_livraison_prevue or self.statut_reception == 'recu':
            return False
        from datetime import date
        return date.today() > self.date_livraison_prevue

    @property
    def est_echeance_proche(self):
        """Vrai si l'échéance est aujourd'hui ou dans les 48 heures (non encore reçue)."""
        if not self.date_livraison_prevue or self.statut_reception == 'recu':
            return False
        from datetime import date
        delta = (self.date_livraison_prevue - date.today()).days
        return 0 <= delta <= 2

    @property
    def jours_restants_delai(self):
        """Nombre de jours avant l'échéance (négatif si en retard)."""
        if not self.date_livraison_prevue:
            return None
        from datetime import date
        return (self.date_livraison_prevue - date.today()).days


# ─────────────────────────────────────────
# HISTORIQUE / JOURNAL D'AUDIT
# ─────────────────────────────────────────
class HistoriqueAction(db.Model):
    __tablename__ = 'historique_actions'
    id             = db.Column(db.Integer, primary_key=True)
    bdc_id         = db.Column(db.Integer, db.ForeignKey('bons_de_commande.id'), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timestamp      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    type_action    = db.Column(db.String(64), nullable=False)
    ancien_statut  = db.Column(db.String(32), nullable=True)
    nouveau_statut = db.Column(db.String(32), nullable=True)
    details        = db.Column(db.Text, nullable=True)

    @property
    def type_action_label(self):
        labels = {
            'creation':                  'Création',
            'validation_dt':             'Validation DT',
            'refus_validation':          'Refus DT',
            'validation_fournisseur':    'Validation Bon par Fournisseur',
            'delai_fournisseur':         'Délai de livraison fixé par Fournisseur',
            'livraison_fournisseur':     'Livraison déclarée par Fournisseur',
            'reception_magasinier':      'Réception certifiée par Magasinier (DT)',
            'livraison':                 'Livrée (fournisseur)',
            'mise_en_stock':             'Mise en stock',
            'recuperation_transporteur': 'Récupérée par le transporteur',
            'reception_piece':           'Réception pièce mise à jour',
            'cloture':                   'Clôture',
            'annulation':                'Annulation',
            'modification':              'Modification',
            'envoi_whatsapp':            'Envoi WhatsApp Fournisseur',
            'relance_whatsapp':          'Relance WhatsApp Fournisseur (+24h)',
            'impression_pdf':            'Impression du Bon (PDF)',
        }
        return labels.get(self.type_action, self.type_action)

    @property
    def icone(self):
        icones = {
            'creation':                  'bi-plus-circle-fill text-primary',
            'validation_dt':             'bi-check-circle-fill text-success',
            'refus_validation':          'bi-x-circle-fill text-danger',
            'validation_fournisseur':    'bi-patch-check-fill text-warning',
            'delai_fournisseur':         'bi-clock-history text-danger',
            'livraison_fournisseur':     'bi-truck-flatbed text-info',
            'reception_magasinier':      'bi-shield-check text-success',
            'livraison':                 'bi-box-seam-fill text-info',
            'mise_en_stock':             'bi-archive-fill text-success',
            'recuperation_transporteur': 'bi-truck text-purple',
            'reception_piece':           'bi-check2-square text-warning',
            'cloture':                   'bi-lock-fill text-secondary',
            'annulation':                'bi-trash-fill text-dark',
            'modification':              'bi-pencil-fill text-warning',
            'envoi_whatsapp':            'bi-whatsapp text-success',
            'relance_whatsapp':          'bi-arrow-repeat text-warning',
            'impression_pdf':            'bi-printer-fill text-danger',
        }
        return icones.get(self.type_action, 'bi-circle-fill text-muted')


# ─────────────────────────────────────────
# FOURNISSEURS
# ─────────────────────────────────────────
class Fournisseur(db.Model):
    __tablename__ = 'fournisseurs'
    id            = db.Column(db.Integer, primary_key=True)
    nom           = db.Column(db.String(128), unique=True, nullable=False)
    contact_nom   = db.Column(db.String(128), nullable=True)
    telephone     = db.Column(db.String(64), nullable=True)
    whatsapp      = db.Column(db.String(64), nullable=True)
    email         = db.Column(db.String(128), nullable=True)
    adresse       = db.Column(db.String(256), nullable=True)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Fournisseur {self.nom}>'


# ─────────────────────────────────────────
# CONFIGURATION SYSTÈME & PASSERELLES
# ─────────────────────────────────────────
class ConfigurationSysteme(db.Model):
    __tablename__ = 'configurations_systeme'
    cle         = db.Column(db.String(64), primary_key=True)
    valeur      = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(256), nullable=True)

    @classmethod
    def get(cls, cle, defaut=None):
        try:
            item = cls.query.filter_by(cle=cle).first()
            return item.valeur if item and item.valeur is not None else defaut
        except Exception:
            return defaut

    @classmethod
    def set(cls, cle, valeur, description=None):
        item = cls.query.filter_by(cle=cle).first()
        if not item:
            item = cls(cle=cle, valeur=valeur, description=description)
            db.session.add(item)
        else:
            item.valeur = valeur
            if description:
                item.description = description
        db.session.commit()

    def __repr__(self):
        return f'<Config {self.cle}={self.valeur}>'
