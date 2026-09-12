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
    username       = db.Column(db.String(64), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    nom_complet    = db.Column(db.String(128), nullable=False)
    role           = db.Column(db.String(128), nullable=False)  # Titre libre manuel (ex: Président Directeur Général, Magasinier...)
    actif          = db.Column(db.Boolean, default=True)
    date_creation  = db.Column(db.DateTime, default=datetime.utcnow)

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

    # Relations
    bons_crees    = db.relationship('BonDeCommande', foreign_keys='BonDeCommande.createur_id', backref='createur', lazy=True)
    bons_valides  = db.relationship('BonDeCommande', foreign_keys='BonDeCommande.validateur_dt_id', backref='validateur_dt', lazy=True)
    actions       = db.relationship('HistoriqueAction', backref='acteur', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def role_label(self):
        labels = {
            'DT': 'Directeur Technique',
            'DTA': 'Dir. Technique Adjoint',
            'magasinier': 'Magasinier',
            'transporteur': 'Transporteur',
            'DG': 'Directeur Général',
            'PDG': 'Président Directeur Général',
        }
        return labels.get(self.role, self.role or 'Utilisateur')

    @property
    def can_creer_bdc(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_creer_bdc or self.role in ('DT', 'DTA', 'magasinier', 'Directeur Technique', 'Directeur Technique Adjoint', 'Magasinier'))

    @property
    def can_valider_dt(self):
        if not self.actif or self.est_spectateur:
            return False
        return bool(self.peut_valider_dt or self.role in ('DT', 'Directeur Technique'))

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
        if bdc and getattr(bdc, 'statut', None) in ('cloturee', 'annulee'):
            return False
        return bool(self.peut_annuler or self.role in ('DT', 'DTA', 'Directeur Technique', 'Directeur Technique Adjoint'))

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
    numero                   = db.Column(db.Integer, unique=True, nullable=False)
    date_creation            = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Type de bon : 'vehicule' ou 'garage'
    type_bon                 = db.Column(db.String(32), default='vehicule', nullable=False)

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

    # Envoi WhatsApp automatique
    whatsapp_envoye          = db.Column(db.Boolean, default=False)
    date_envoi_whatsapp      = db.Column(db.DateTime, nullable=True)

    # Relations
    lignes     = db.relationship('LigneBDC', backref='bon', lazy=True,
                                  cascade='all, delete-orphan', order_by='LigneBDC.ordre')
    historique = db.relationship('HistoriqueAction', backref='bon', lazy=True,
                                  cascade='all, delete-orphan',
                                  order_by='HistoriqueAction.timestamp.desc()')
    receptionniste   = db.relationship('User', foreign_keys=[receptionniste_id])
    magasinier_stock = db.relationship('User', foreign_keys=[magasinier_stock_id])
    annulateur       = db.relationship('User', foreign_keys=[annulateur_id])

    @property
    def numero_affiche(self):
        date_ref = self.date_creation or datetime.utcnow()
        return f"BDC-{date_ref.strftime('%m/%y')}-{self.numero:05d}"

    @property
    def est_garage(self):
        return self.type_bon == 'garage'

    @property
    def type_label(self):
        return "Garage (Interne)" if self.est_garage else "Véhicule"

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
            'livraison':                 'Livrée (fournisseur)',
            'mise_en_stock':             'Mise en stock',
            'recuperation_transporteur': 'Récupérée par le transporteur',
            'reception_piece':           'Réception pièce mise à jour',
            'cloture':                   'Clôture',
            'annulation':                'Annulation',
            'modification':              'Modification',
            'envoi_whatsapp':            'Envoi WhatsApp Fournisseur',
        }
        return labels.get(self.type_action, self.type_action)

    @property
    def icone(self):
        icones = {
            'creation':                  'bi-plus-circle-fill text-primary',
            'validation_dt':             'bi-check-circle-fill text-success',
            'refus_validation':          'bi-x-circle-fill text-danger',
            'livraison':                 'bi-box-seam-fill text-info',
            'mise_en_stock':             'bi-archive-fill text-success',
            'recuperation_transporteur': 'bi-truck text-purple',
            'reception_piece':           'bi-check2-square text-warning',
            'cloture':                   'bi-lock-fill text-secondary',
            'annulation':                'bi-trash-fill text-dark',
            'modification':              'bi-pencil-fill text-warning',
            'envoi_whatsapp':            'bi-whatsapp text-success',
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
