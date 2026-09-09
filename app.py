"""
app.py — Application principale Flask — Système BDC TAXI GAB+
"""
import os
from datetime import datetime, timedelta
from flask import (Flask, render_template, redirect, url_for, request,
                   flash, abort, send_file, jsonify)
from flask_login import (LoginManager, login_user, logout_user,
                          login_required, current_user)
from sqlalchemy import or_, and_, func, extract
import io

from config import Config
from database import db, User, BonDeCommande, LigneBDC, HistoriqueAction, STATUTS_BDC, STATUTS_COULEURS
from pdf_generator import generate_bdc_pdf

# ─────────────────────────────────────────
# INITIALISATION
# ─────────────────────────────────────────
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['DATA_DIR'], exist_ok=True)
    os.makedirs(os.path.join(app.config['STATIC_DIR'], 'images'), exist_ok=True)

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ─── HELPERS ──────────────────────────────────────────────────────────
    def get_next_numero():
        """Retourne le prochain numéro de BDC réinitialisé à 1 chaque début de mois."""
        now = datetime.utcnow()
        # Chercher le plus grand numéro créé dans le mois et l'année en cours
        dernier_du_mois = BonDeCommande.query.filter(
            extract('year', BonDeCommande.date_creation) == now.year,
            extract('month', BonDeCommande.date_creation) == now.month
        ).order_by(BonDeCommande.numero.desc()).first()

        if dernier_du_mois:
            return dernier_du_mois.numero + 1
        return 1  # Repart à 00001 chaque nouveau mois

    def enregistrer_action(bdc, type_action, ancien_statut=None,
                            nouveau_statut=None, details=None, user=None):
        """Enregistre une action dans le journal d'audit."""
        action = HistoriqueAction(
            bdc_id=bdc.id,
            user_id=(user or current_user).id if (user or current_user).is_authenticated else None,
            type_action=type_action,
            ancien_statut=ancien_statut,
            nouveau_statut=nouveau_statut,
            details=details,
        )
        db.session.add(action)

    def peut_valider_dt(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_valider_dt', False) or user.role == 'DT')

    def peut_creer_bdc(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_creer_bdc', False) or user.role in ('DT', 'DTA', 'magasinier'))

    def peut_annuler(user, bdc=None):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        if bdc and getattr(bdc, 'statut', None) in ('cloturee', 'annulee'):
            return False
        return bool(getattr(user, 'peut_annuler', False) or user.role in ('DT', 'DTA'))

    def peut_gerer_stock(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_gerer_stock', False) or user.role in ('DT', 'DTA', 'magasinier'))

    def peut_cloturer(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_cloturer', False) or user.role in ('DT', 'DTA'))

    def peut_recuperer(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_recuperer', False) or user.role in ('DT', 'DTA', 'magasinier', 'transporteur'))

    def peut_gerer_utilisateurs(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'peut_gerer_utilisateurs', False) or user.role == 'DT')

    @app.context_processor
    def inject_globals():
        return {
            'STATUTS_BDC': STATUTS_BDC,
            'STATUTS_COULEURS': STATUTS_COULEURS,
            'now': datetime.now(),
            'company_name': Config.COMPANY_NAME,
        }

    # ─── AUTHENTIFICATION ─────────────────────────────────────────────────
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.query.filter_by(username=username, actif=True).first()
            if user and user.check_password(password):
                login_user(user, remember=True)
                next_page = request.args.get('next')
                flash(f'Bienvenue, {user.nom_complet} !', 'success')
                return redirect(next_page or url_for('dashboard'))
            flash('Identifiant ou mot de passe incorrect.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Vous avez été déconnecté.', 'info')
        return redirect(url_for('login'))

    # ─── TABLEAU DE BORD ──────────────────────────────────────────────────
    @app.route('/dashboard')
    @login_required
    def dashboard():
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        base_query = BonDeCommande.query

        stats = {
            'today':                  base_query.filter(BonDeCommande.date_creation >= today).count(),
            'week':                   base_query.filter(BonDeCommande.date_creation >= week_start).count(),
            'month':                  base_query.filter(BonDeCommande.date_creation >= month_start).count(),
            'year':                   base_query.filter(BonDeCommande.date_creation >= year_start).count(),
            'en_attente':             base_query.filter_by(statut='en_attente').count(),
            'validee':                base_query.filter_by(statut='validee').count(),
            'refusee':                base_query.filter_by(statut='refusee').count(),
            'livree':                 base_query.filter_by(statut='livree').count(),
            'en_stock':               base_query.filter_by(statut='en_stock').count(),
            'recuperee_transporteur': base_query.filter_by(statut='recuperee_transporteur').count(),
            'cloturee':               base_query.filter_by(statut='cloturee').count(),
            'annulee':                base_query.filter_by(statut='annulee').count(),
            'total':                  base_query.count(),
        }

        # Derniers BDC
        recents = base_query.order_by(BonDeCommande.date_creation.desc()).limit(10).all()

        # Alertes : BDC en attente de validation DT (si DT connecté)
        alertes_validation = []
        if current_user.role == 'DT':
            alertes_validation = BonDeCommande.query.filter_by(statut='en_attente').all()

        return render_template('dashboard.html',
                               stats=stats,
                               recents=recents,
                               alertes_validation=alertes_validation)

    # ─── LISTE DES BDC ────────────────────────────────────────────────────
    @app.route('/bdc')
    @login_required
    def bdc_list():
        q = BonDeCommande.query

        f_statut      = request.args.get('statut', '')
        f_fournisseur = request.args.get('fournisseur', '')
        f_transporteur = request.args.get('transporteur', '')
        f_vehicule    = request.args.get('vehicule', '')
        f_piece       = request.args.get('piece', '')
        f_createur    = request.args.get('createur', '')
        f_date_debut  = request.args.get('date_debut', '')
        f_date_fin    = request.args.get('date_fin', '')
        f_numero      = request.args.get('numero', '')

        if f_statut:
            q = q.filter_by(statut=f_statut)
        if f_fournisseur:
            q = q.filter(BonDeCommande.fournisseur.ilike(f'%{f_fournisseur}%'))
        if f_transporteur:
            q = q.filter(BonDeCommande.transporteur.ilike(f'%{f_transporteur}%'))
        if f_vehicule:
            q = q.filter(or_(
                BonDeCommande.vehicule_nom.ilike(f'%{f_vehicule}%'),
                BonDeCommande.vehicule_immatriculation.ilike(f'%{f_vehicule}%')
            ))
        if f_piece:
            q = q.join(LigneBDC).filter(LigneBDC.designation.ilike(f'%{f_piece}%'))
        if f_createur:
            q = q.join(User, BonDeCommande.createur_id == User.id).filter(
                User.nom_complet.ilike(f'%{f_createur}%'))
        if f_date_debut:
            try:
                dd = datetime.strptime(f_date_debut, '%Y-%m-%d')
                q = q.filter(BonDeCommande.date_creation >= dd)
            except ValueError:
                pass
        if f_date_fin:
            try:
                df = datetime.strptime(f_date_fin, '%Y-%m-%d') + timedelta(days=1)
                q = q.filter(BonDeCommande.date_creation < df)
            except ValueError:
                pass
        if f_numero:
            try:
                q = q.filter_by(numero=int(f_numero))
            except ValueError:
                pass

        bons = q.order_by(BonDeCommande.date_creation.desc()).all()
        utilisateurs = User.query.filter(User.role.in_(['DT','DTA','magasinier'])).all()
        return render_template('bdc/list.html',
                               bons=bons,
                               statuts=STATUTS_BDC,
                               utilisateurs=utilisateurs,
                               filtres={
                                   'statut': f_statut,
                                   'fournisseur': f_fournisseur,
                                   'transporteur': f_transporteur,
                                   'vehicule': f_vehicule,
                                   'piece': f_piece,
                                   'createur': f_createur,
                                   'date_debut': f_date_debut,
                                   'date_fin': f_date_fin,
                                   'numero': f_numero,
                               })

    # ─── CRÉER UN BDC ─────────────────────────────────────────────────────
    @app.route('/bdc/nouveau', methods=['GET', 'POST'])
    @login_required
    def bdc_create():
        if not peut_creer_bdc(current_user):
            abort(403)

        if request.method == 'POST':
            type_bon        = request.form.get('type_bon', 'vehicule').strip()
            demandeur_nom   = request.form.get('demandeur_nom', '').strip()
            service         = request.form.get('service_departement', '').strip()
            fournisseur     = request.form.get('fournisseur', '').strip()
            observations    = request.form.get('observations_generales', '').strip()

            if type_bon == 'garage':
                vehicule_nom   = 'GARAGE'
                vehicule_immat = ''
                transporteur   = ''
            else:
                vehicule_nom   = request.form.get('vehicule_nom', '').strip()
                vehicule_immat = request.form.get('vehicule_immatriculation', '').strip()
                transporteur   = request.form.get('transporteur', '').strip()

            designations = request.form.getlist('designation[]')
            quantites    = request.form.getlist('quantite[]')
            obs_lignes   = request.form.getlist('obs_ligne[]')

            if not demandeur_nom:
                flash('Le nom du demandeur est obligatoire.', 'danger')
                return render_template('bdc/create.html',
                                       demandeur_defaut=current_user.nom_complet,
                                       service_defaut=current_user.role_label)

            lignes_valides = [(d.strip(), q, o.strip())
                               for d, q, o in zip(designations, quantites, obs_lignes)
                               if d.strip()]
            if not lignes_valides:
                flash('Veuillez saisir au moins une pièce.', 'danger')
                return render_template('bdc/create.html',
                                       demandeur_defaut=current_user.nom_complet,
                                       service_defaut=current_user.role_label)

            statut_initial = 'validee' if current_user.role == 'DT' else 'en_attente'

            bdc = BonDeCommande(
                numero=get_next_numero(),
                type_bon=type_bon,
                createur_id=current_user.id,
                demandeur_nom=demandeur_nom,
                service_departement=service,
                fournisseur=fournisseur,
                vehicule_nom=vehicule_nom,
                vehicule_immatriculation=vehicule_immat,
                transporteur=transporteur,
                observations_generales=observations,
                statut=statut_initial,
            )
            if current_user.role == 'DT':
                bdc.validateur_dt_id = current_user.id
                bdc.date_validation_dt = datetime.now()

            db.session.add(bdc)
            db.session.flush()

            for i, (desig, qte, obs_l) in enumerate(lignes_valides, 1):
                try:
                    qty = int(qte)
                except (ValueError, TypeError):
                    qty = 1
                ligne = LigneBDC(
                    bdc_id=bdc.id,
                    ordre=i,
                    designation=desig,
                    quantite=qty,
                    observations=obs_l,
                )
                db.session.add(ligne)

            enregistrer_action(bdc, 'creation', nouveau_statut=statut_initial,
                                details=f"Bon créé par {current_user.nom_complet} ({current_user.role_label})")
            if current_user.role == 'DT':
                enregistrer_action(bdc, 'validation_dt',
                                    ancien_statut='en_attente', nouveau_statut='validee',
                                    details='Validation automatique (créé par le DT)')

            db.session.commit()
            flash(f'Bon de commande N°{bdc.numero} créé avec succès !', 'success')
            return redirect(url_for('bdc_view', id=bdc.id))

        return render_template('bdc/create.html',
                               demandeur_defaut=current_user.nom_complet,
                               service_defaut=current_user.role_label)

    # ─── VOIR UN BDC ──────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>')
    @login_required
    def bdc_view(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        return render_template('bdc/view.html',
                               bdc=bdc,
                               peut_valider=peut_valider_dt(current_user),
                               peut_annuler=peut_annuler(current_user, bdc),
                               peut_gerer_stock=peut_gerer_stock(current_user))

    # ─── VALIDER (DT) ─────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>/valider', methods=['POST'])
    @login_required
    def bdc_valider(id):
        if not peut_valider_dt(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        if bdc.statut != 'en_attente':
            flash('Ce bon ne peut pas être validé dans son état actuel.', 'warning')
            return redirect(url_for('bdc_view', id=id))

        ancien = bdc.statut
        bdc.statut = 'validee'
        bdc.validateur_dt_id = current_user.id
        bdc.date_validation_dt = datetime.now()
        enregistrer_action(bdc, 'validation_dt', ancien_statut=ancien, nouveau_statut='validee',
                            details=f"Validé par {current_user.nom_complet}")
        db.session.commit()
        flash(f'Bon N°{bdc.numero} validé avec succès.', 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── REFUSER VALIDATION (DT) ──────────────────────────────────────────
    @app.route('/bdc/<int:id>/refuser_validation', methods=['POST'])
    @login_required
    def bdc_refuser_validation(id):
        if not peut_valider_dt(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        if bdc.statut != 'en_attente':
            flash('Ce bon ne peut pas être refusé dans son état actuel.', 'warning')
            return redirect(url_for('bdc_view', id=id))
        motif = request.form.get('motif', '').strip()
        ancien = bdc.statut
        bdc.statut = 'refusee'
        bdc.motif_refus_dt = motif
        enregistrer_action(bdc, 'refus_validation', ancien_statut=ancien, nouveau_statut='refusee',
                            details=f"Refus DT: {motif}")
        db.session.commit()
        flash(f'Bon N°{bdc.numero} refusé.', 'warning')
        return redirect(url_for('bdc_view', id=id))

    # ─── LIVRAISON PAR LE FOURNISSEUR ─────────────────────────────────────
    @app.route('/bdc/<int:id>/livrer', methods=['POST'])
    @login_required
    def bdc_livrer(id):
        if not peut_gerer_stock(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        if bdc.statut not in ('validee', 'en_attente'):
            flash('Ce bon ne peut pas être marqué comme livré dans son état actuel.', 'warning')
            return redirect(url_for('bdc_view', id=id))

        ancien = bdc.statut
        bdc.statut = 'livree'
        bdc.date_livraison = datetime.now()
        bdc.receptionniste_id = current_user.id
        # La réception reste décentralisée pièce par pièce sans forcer toutes les lignes
        enregistrer_action(bdc, 'livraison', ancien_statut=ancien, nouveau_statut='livree',
                            details=f"Statut général de commande passé à Livrée par {current_user.nom_complet}")
        db.session.commit()
        flash(f'Statut global du bon N°{bdc.numero} passé à Livrée.', 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── MISE EN STOCK (MAGASIN) ──────────────────────────────────────────
    @app.route('/bdc/<int:id>/mettre_en_stock', methods=['POST'])
    @login_required
    def bdc_mettre_en_stock(id):
        if not peut_gerer_stock(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        if bdc.statut not in ('validee', 'livree'):
            flash('Ce bon ne peut pas être mis en stock dans son état actuel.', 'warning')
            return redirect(url_for('bdc_view', id=id))

        ancien = bdc.statut
        bdc.statut = 'en_stock'
        bdc.date_en_stock = datetime.now()
        bdc.magasinier_stock_id = current_user.id
        enregistrer_action(bdc, 'mise_en_stock', ancien_statut=ancien, nouveau_statut='en_stock',
                            details=f"Pièces mises en stock par {current_user.nom_complet}")
        db.session.commit()
        flash(f'Pièces du bon N°{bdc.numero} enregistrées en stock.', 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── BON RÉCUPÉRÉ PAR LE TRANSPORTEUR ─────────────────────────────────
    @app.route('/bdc/<int:id>/recuperer_transporteur', methods=['POST'])
    @login_required
    def bdc_recuperer_transporteur(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        if bdc.statut not in ('en_stock', 'livree', 'validee', 'en_attente'):
            flash('Ce bon ne peut pas être marqué comme récupéré dans son état actuel.', 'warning')
            return redirect(url_for('bdc_view', id=id))

        recuperateur = request.form.get('nom_recuperateur', '').strip() or bdc.transporteur or current_user.nom_complet or 'Transporteur'
        ancien = bdc.statut
        bdc.statut = 'recuperee_transporteur'
        bdc.date_recuperation = datetime.now()
        bdc.nom_recuperateur = recuperateur
        enregistrer_action(bdc, 'recuperation_transporteur', ancien_statut=ancien, nouveau_statut='recuperee_transporteur',
                            details=f"Bon récupéré par le transporteur {recuperateur} (enregistré par {current_user.nom_complet})")
        db.session.commit()
        flash(f'Bon N°{bdc.numero_affiche} : marqué comme « Bon récupéré par le transporteur » ({recuperateur}).', 'info')
        return redirect(url_for('bdc_view', id=id))

    # ─── CLÔTURE ──────────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>/cloturer', methods=['POST'])
    @login_required
    def bdc_cloturer(id):
        if current_user.role not in ('DT', 'DTA'):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        ancien = bdc.statut
        bdc.statut = 'cloturee'
        bdc.date_cloture = datetime.now()
        enregistrer_action(bdc, 'cloture', ancien_statut=ancien, nouveau_statut='cloturee',
                            details=f"Clôturé par {current_user.nom_complet}")
        db.session.commit()
        flash(f'Bon N°{bdc.numero} clôturé.', 'secondary')
        return redirect(url_for('bdc_view', id=id))

    # ─── ANNULATION ───────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>/annuler', methods=['POST'])
    @login_required
    def bdc_annuler(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc or not peut_annuler(current_user, bdc):
            abort(403)
        motif = request.form.get('motif', '').strip()
        ancien = bdc.statut
        bdc.statut = 'annulee'
        bdc.date_annulation = datetime.now()
        bdc.motif_annulation = motif
        bdc.annulateur_id = current_user.id
        enregistrer_action(bdc, 'annulation', ancien_statut=ancien, nouveau_statut='annulee',
                            details=f"Annulé par {current_user.nom_complet}. Motif: {motif}")
        db.session.commit()
        flash(f'Bon N°{bdc.numero} annulé.', 'dark')
        return redirect(url_for('bdc_view', id=id))

    # ─── MISE À JOUR RÉCEPTION PIÈCE ──────────────────────────────────────
    @app.route('/bdc/<int:id>/reception', methods=['POST'])
    @login_required
    def bdc_reception(id):
        if not peut_gerer_stock(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)

        ligne_id       = request.form.get('ligne_id')
        nouveau_statut = request.form.get('statut_reception')
        qte_recue      = request.form.get('quantite_recue', 0)
        livreur_nom    = request.form.get('livreur_nom', '').strip()
        note           = request.form.get('note_reception', '').strip()

        ligne = db.session.get(LigneBDC, int(ligne_id))
        if not ligne or ligne.bdc_id != bdc.id:
            abort(400)

        ligne.statut_reception = nouveau_statut
        ligne.livreur_nom = livreur_nom or bdc.fournisseur or 'Fournisseur'
        try:
            ligne.quantite_recue = int(qte_recue)
        except (ValueError, TypeError):
            ligne.quantite_recue = 0
        ligne.date_reception = datetime.now()
        ligne.note_reception = note

        livreur_info = f" (livré par {ligne.livreur_nom})" if ligne.livreur_nom else ""
        enregistrer_action(bdc, 'reception_piece',
                            details=f"Pièce '{ligne.designation}' → {ligne.statut_reception_label}{livreur_info} "
                                    f"(par {current_user.nom_complet})")
        db.session.commit()
        flash(f'Réception de « {ligne.designation} » mise à jour avec succès.', 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── ACTION RAPIDE RÉCEPTION (LIVRÉ / NON LIVRÉ PAR PIÈCE) ────────────
    @app.route('/bdc/<int:id>/reception_rapide/<int:ligne_id>/<string:action>', methods=['POST'])
    @login_required
    def bdc_reception_rapide(id, ligne_id, action):
        if not peut_gerer_stock(current_user):
            abort(403)
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        ligne = db.session.get(LigneBDC, ligne_id)
        if not ligne or ligne.bdc_id != bdc.id:
            abort(400)

        if action == 'livre':
            ligne.statut_reception = 'recu'
            ligne.quantite_recue = ligne.quantite
            ligne.date_reception = datetime.now()
            if not ligne.livreur_nom:
                ligne.livreur_nom = bdc.fournisseur or 'Fournisseur'
            msg = f"Pièce « {ligne.designation} » marquée comme LIVRÉE ({ligne.quantite}/{ligne.quantite})."
        elif action == 'non_recu':
            ligne.statut_reception = 'non_recu'
            ligne.quantite_recue = 0
            ligne.date_reception = None
            msg = f"Pièce « {ligne.designation} » marquée comme NON LIVRÉE."
        else:
            abort(400)

        enregistrer_action(bdc, 'reception_piece',
                            details=f"Pointage rapide pièce '{ligne.designation}' → {ligne.statut_reception_label} "
                                    f"(par {current_user.nom_complet})")
        db.session.commit()
        flash(msg, 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── PDF ──────────────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>/pdf')
    @login_required
    def bdc_pdf(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        avec_reception = request.args.get('avec_reception') == '1'
        pdf_bytes = generate_bdc_pdf(bdc, Config, avec_reception=avec_reception)
        suffixe = "_reception" if avec_reception else ""
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"{bdc.numero_affiche.replace('/', '-')}{suffixe}.pdf"
        )

    # ─── NOUVELLE RUBRIQUE : FOURNISSEURS & HISTORIQUE MENSUEL ───────────
    @app.route('/fournisseurs')
    @login_required
    def fournisseurs():
        selected_fournisseur = request.args.get('fournisseur', '').strip()
        selected_mois        = request.args.get('mois', '')     # 'YYYY-MM'
        
        # Liste distincte de tous les fournisseurs ayant des bons
        fournisseurs_raw = db.session.query(BonDeCommande.fournisseur)\
            .filter(BonDeCommande.fournisseur.isnot(None), BonDeCommande.fournisseur != '')\
            .distinct().order_by(BonDeCommande.fournisseur).all()
        liste_fournisseurs = [f[0] for f in fournisseurs_raw]

        # Requête de base pour les statistiques et les bons
        q = BonDeCommande.query.filter(BonDeCommande.fournisseur.isnot(None), BonDeCommande.fournisseur != '')

        if selected_fournisseur:
            q = q.filter(BonDeCommande.fournisseur == selected_fournisseur)

        if selected_mois:
            try:
                annee, mois = map(int, selected_mois.split('-'))
                debut_mois = datetime(annee, mois, 1)
                if mois == 12:
                    fin_mois = datetime(annee + 1, 1, 1)
                else:
                    fin_mois = datetime(annee, mois + 1, 1)
                q = q.filter(BonDeCommande.date_creation >= debut_mois, BonDeCommande.date_creation < fin_mois)
            except Exception:
                pass

        bons = q.order_by(BonDeCommande.date_creation.desc()).all()

        # Synthèse par fournisseur (tableau récapitulatif mensuel)
        stats_fournisseurs = {}
        for b in bons:
            fn = b.fournisseur or 'Non renseigné'
            if fn not in stats_fournisseurs:
                stats_fournisseurs[fn] = {
                    'total_commandes': 0,
                    'total_pieces': 0,
                    'en_attente': 0,
                    'validee': 0,
                    'livree': 0,
                    'en_stock': 0,
                    'recuperee_transporteur': 0,
                    'cloturee': 0,
                    'refusee': 0,
                    'annulee': 0,
                }
            stats_fournisseurs[fn]['total_commandes'] += 1
            stats_fournisseurs[fn]['total_pieces'] += b.total_pieces
            if b.statut in stats_fournisseurs[fn]:
                stats_fournisseurs[fn][b.statut] += 1

        # Liste des mois disponibles dans la base pour le menu déroulant
        dates_raw = db.session.query(BonDeCommande.date_creation).order_by(BonDeCommande.date_creation.desc()).all()
        mois_disponibles = sorted(list({d[0].strftime('%Y-%m') for d in dates_raw if d[0]}), reverse=True)

        return render_template('fournisseurs.html',
                               liste_fournisseurs=liste_fournisseurs,
                               selected_fournisseur=selected_fournisseur,
                               selected_mois=selected_mois,
                               mois_disponibles=mois_disponibles,
                               bons=bons,
                               stats_fournisseurs=stats_fournisseurs)

    # ─── HISTORIQUE GÉNÉRAL ───────────────────────────────────────────────
    @app.route('/historique')
    @login_required
    def historique():
        q = HistoriqueAction.query.join(BonDeCommande)

        f_numero      = request.args.get('numero', '')
        f_action      = request.args.get('action', '')
        f_user        = request.args.get('user', '')
        f_fournisseur = request.args.get('fournisseur', '')
        f_date_debut  = request.args.get('date_debut', '')
        f_date_fin    = request.args.get('date_fin', '')

        if f_numero:
            try:
                q = q.filter(BonDeCommande.numero == int(f_numero))
            except ValueError:
                pass
        if f_action:
            q = q.filter(HistoriqueAction.type_action == f_action)
        if f_fournisseur:
            q = q.filter(BonDeCommande.fournisseur.ilike(f'%{f_fournisseur}%'))
        if f_user:
            q = q.join(User, HistoriqueAction.user_id == User.id).filter(
                User.nom_complet.ilike(f'%{f_user}%'))
        if f_date_debut:
            try:
                dd = datetime.strptime(f_date_debut, '%Y-%m-%d')
                q = q.filter(HistoriqueAction.timestamp >= dd)
            except ValueError:
                pass
        if f_date_fin:
            try:
                df = datetime.strptime(f_date_fin, '%Y-%m-%d') + timedelta(days=1)
                q = q.filter(HistoriqueAction.timestamp < df)
            except ValueError:
                pass

        actions = q.order_by(HistoriqueAction.timestamp.desc()).limit(500).all()
        types_actions = db.session.query(HistoriqueAction.type_action).distinct().all()
        types_actions = [t[0] for t in types_actions]

        return render_template('history.html',
                               actions=actions,
                               types_actions=types_actions,
                               filtres={'numero': f_numero, 'action': f_action,
                                        'user': f_user, 'fournisseur': f_fournisseur,
                                        'date_debut': f_date_debut, 'date_fin': f_date_fin})

    # ─── SUIVI RÉCEPTIONS ─────────────────────────────────────────────────
    @app.route('/suivi')
    @login_required
    def suivi():
        q = BonDeCommande.query.filter(BonDeCommande.statut.in_(['validee', 'livree', 'en_stock', 'recuperee_transporteur']))
        f_vehicule = request.args.get('vehicule', '')
        f_fournisseur = request.args.get('fournisseur', '')
        f_transporteur = request.args.get('transporteur', '')
        f_statut_rec = request.args.get('statut_reception', '')

        if f_vehicule:
            q = q.filter(or_(
                BonDeCommande.vehicule_nom.ilike(f'%{f_vehicule}%'),
                BonDeCommande.vehicule_immatriculation.ilike(f'%{f_vehicule}%')
            ))
        if f_fournisseur:
            q = q.filter(BonDeCommande.fournisseur.ilike(f'%{f_fournisseur}%'))
        if f_transporteur:
            q = q.filter(BonDeCommande.transporteur.ilike(f'%{f_transporteur}%'))

        bons = q.order_by(BonDeCommande.date_creation.desc()).all()

        if f_statut_rec:
            bons = [b for b in bons if any(l.statut_reception == f_statut_rec for l in b.lignes)]

        return render_template('suivi.html',
                               bons=bons,
                               filtres={'vehicule': f_vehicule,
                                        'fournisseur': f_fournisseur,
                                        'transporteur': f_transporteur,
                                        'statut_reception': f_statut_rec})

    # ─── ADMIN : UTILISATEURS ─────────────────────────────────────────────
    @app.route('/admin/utilisateurs')
    @login_required
    def admin_users():
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        users = User.query.order_by(User.nom_complet).all()
        return render_template('admin/users.html', users=users)

    @app.route('/admin/utilisateurs/nouveau', methods=['GET', 'POST'])
    @login_required
    def admin_user_create():
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        if request.method == 'POST':
            username    = request.form.get('username', '').strip()
            password    = request.form.get('password', '').strip()
            nom_complet = request.form.get('nom_complet', '').strip()
            role        = request.form.get('role', '').strip()

            if User.query.filter_by(username=username).first():
                flash('Cet identifiant existe déjà.', 'danger')
            elif not all([username, password, nom_complet, role]):
                flash('Tous les champs obligatoires doivent être renseignés.', 'danger')
            else:
                u = User(username=username, nom_complet=nom_complet, role=role)
                u.set_password(password)
                u.est_spectateur          = request.form.get('est_spectateur') == 'on'
                u.peut_creer_bdc          = request.form.get('peut_creer_bdc') == 'on'
                u.peut_valider_dt         = request.form.get('peut_valider_dt') == 'on'
                u.peut_gerer_stock        = request.form.get('peut_gerer_stock') == 'on'
                u.peut_recuperer          = request.form.get('peut_recuperer') == 'on'
                u.peut_cloturer           = request.form.get('peut_cloturer') == 'on'
                u.peut_annuler            = request.form.get('peut_annuler') == 'on'
                u.peut_gerer_utilisateurs = request.form.get('peut_gerer_utilisateurs') == 'on'
                db.session.add(u)
                db.session.commit()
                flash(f'Utilisateur {nom_complet} ({role}) créé avec succès.', 'success')
                return redirect(url_for('admin_users'))
        return render_template('admin/user_form.html', user=None)

    @app.route('/admin/utilisateurs/<int:id>/modifier', methods=['GET', 'POST'])
    @login_required
    def admin_user_edit(id):
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        user = db.session.get(User, id)
        if not user:
            abort(404)
        if request.method == 'POST':
            user.nom_complet             = request.form.get('nom_complet', '').strip()
            user.role                    = request.form.get('role', '').strip()
            user.actif                   = request.form.get('actif') == 'on'
            user.est_spectateur          = request.form.get('est_spectateur') == 'on'
            user.peut_creer_bdc          = request.form.get('peut_creer_bdc') == 'on'
            user.peut_valider_dt         = request.form.get('peut_valider_dt') == 'on'
            user.peut_gerer_stock        = request.form.get('peut_gerer_stock') == 'on'
            user.peut_recuperer          = request.form.get('peut_recuperer') == 'on'
            user.peut_cloturer           = request.form.get('peut_cloturer') == 'on'
            user.peut_annuler            = request.form.get('peut_annuler') == 'on'
            user.peut_gerer_utilisateurs = request.form.get('peut_gerer_utilisateurs') == 'on'
            new_pw = request.form.get('password', '').strip()
            if new_pw:
                user.set_password(new_pw)
            db.session.commit()
            flash(f'Utilisateur {user.nom_complet} mis à jour avec succès.', 'success')
            return redirect(url_for('admin_users'))
        return render_template('admin/user_form.html', user=user)

    @app.route('/admin/utilisateurs/<int:id>/supprimer', methods=['POST'])
    @login_required
    def admin_user_delete(id):
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        user = db.session.get(User, id)
        if not user:
            abort(404)
        if user.id == current_user.id:
            flash('Vous ne pouvez pas désactiver votre propre compte.', 'danger')
            return redirect(url_for('admin_users'))
        user.actif = False
        db.session.commit()
        flash(f'Compte {user.nom_complet} désactivé.', 'warning')
        return redirect(url_for('admin_users'))

    # Initialisation automatique des tables et comptes par défaut au démarrage
    with app.app_context():
        try:
            db.create_all()
            from sqlalchemy import text
            # Migration automatique si la colonne livreur_nom n'existe pas encore
            try:
                db.session.execute(text("ALTER TABLE lignes_bdc ADD COLUMN livreur_nom VARCHAR(128)"))
                db.session.commit()
            except Exception:
                db.session.rollback()

            # Migration automatique des colonnes de permissions sur users
            colonnes_permissions = [
                ("peut_creer_bdc", "BOOLEAN DEFAULT 0"),
                ("peut_valider_dt", "BOOLEAN DEFAULT 0"),
                ("peut_gerer_stock", "BOOLEAN DEFAULT 0"),
                ("peut_recuperer", "BOOLEAN DEFAULT 0"),
                ("peut_cloturer", "BOOLEAN DEFAULT 0"),
                ("peut_annuler", "BOOLEAN DEFAULT 0"),
                ("peut_gerer_utilisateurs", "BOOLEAN DEFAULT 0"),
                ("est_spectateur", "BOOLEAN DEFAULT 0"),
            ]
            for col_nom, col_type in colonnes_permissions:
                try:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col_nom} {col_type}"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Comptes par défaut
            default_users = [
                {'username': 'dt',          'password': 'DT@2026!',     'nom': 'Directeur Technique',         'role': 'Directeur Technique',        'admin': True},
                {'username': 'dta',         'password': 'DTA@2026!',    'nom': 'Directeur Technique Adjoint', 'role': 'Directeur Technique Adjoint', 'dta': True},
                {'username': 'magasinier',  'password': 'Mag@2026!',    'nom': 'Magasinier Principal',        'role': 'Magasinier',                 'mag': True},
                {'username': 'transporteur','password': 'Trans@2026!',  'nom': 'Transporteur',                'role': 'Transporteur',               'trans': True},
            ]
            for u_data in default_users:
                u = User.query.filter_by(username=u_data['username']).first()
                if not u:
                    u = User(
                        username=u_data['username'],
                        nom_complet=u_data['nom'],
                        role=u_data['role']
                    )
                    u.set_password(u_data['password'])
                    db.session.add(u)
                else:
                    # S'assurer que le compte est actif et réinitialiser le mot de passe par défaut
                    u.actif = True
                    u.set_password(u_data['password'])
                if u_data.get('admin'):
                    u.peut_gerer_utilisateurs = True
                    u.peut_valider_dt = True
                    u.peut_creer_bdc = True
                    u.peut_gerer_stock = True
                    u.peut_cloturer = True
                    u.peut_annuler = True
                    u.peut_recuperer = True
                elif u_data.get('dta'):
                    u.peut_creer_bdc = True
                    u.peut_annuler = True
                    u.peut_gerer_stock = True
                    u.peut_recuperer = True
                elif u_data.get('mag'):
                    u.peut_creer_bdc = True
                    u.peut_gerer_stock = True
                elif u_data.get('trans'):
                    u.peut_recuperer = True

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Erreur initialisation DB auto:", e)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
