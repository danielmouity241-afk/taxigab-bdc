"""
app.py — Application principale Flask — Système BDC TAXI GAB+
"""
import os
import secrets
import re
import urllib.parse
from datetime import datetime, timedelta
from flask import (Flask, render_template, redirect, url_for, request,
                   flash, abort, send_file, jsonify)
from flask_login import (LoginManager, login_user, logout_user,
                          login_required, current_user)
from sqlalchemy import or_, and_, func, extract, cast
import io

from config import Config
from database import (db, User, BonDeCommande, LigneBDC, HistoriqueAction,
                      Fournisseur, ConfigurationSysteme, STATUTS_BDC, STATUTS_COULEURS)
from pdf_generator import generate_bdc_pdf
from whatsapp_service import envoyer_whatsapp_serveur, nettoyer_telephone

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
        if user.role in ('DT', 'Directeur Technique') or getattr(user, 'is_directeur_technique', False):
            return True
        return bool(getattr(user, 'peut_valider_dt', False))

    def peut_creer_bdc(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        if user.role in ('DT', 'Directeur Technique') or getattr(user, 'is_directeur_technique', False):
            return True
        return bool(getattr(user, 'peut_creer_bdc', False))

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

    def est_directeur_technique(user):
        if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'est_spectateur', False):
            return False
        return bool(getattr(user, 'is_directeur_technique', False) or user.role in ('DT', 'Directeur Technique'))

    def peut_voir_historique(user):
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return bool(getattr(user, 'can_voir_historique', False))

    def peut_voir_archives(user):
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return bool(getattr(user, 'can_voir_archives', False))

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

        # Alertes : BDC en attente de validation DT (si DT connecté ou habilité)
        alertes_validation = []
        if peut_valider_dt(current_user):
            alertes_validation = BonDeCommande.query.filter_by(statut='en_attente').all()

        # Alertes Relances Fournisseurs (+24h sans réception complète)
        bons_en_cours = BonDeCommande.query.filter(BonDeCommande.statut.in_(['validee', 'livree', 'en_stock', 'recuperee_transporteur'])).all()
        alertes_relance_24h = [b for b in bons_en_cours if b.est_en_retard_24h]

        return render_template('dashboard.html',
                               stats=stats,
                               recents=recents,
                               alertes_validation=alertes_validation,
                               alertes_relance_24h=alertes_relance_24h)

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
            type_bon             = request.form.get('type_bon', 'vehicule').strip()
            demandeur_nom        = request.form.get('demandeur_nom', '').strip()
            service              = request.form.get('service_departement', '').strip()
            fournisseur          = request.form.get('fournisseur', '').strip()
            fournisseur_whatsapp = request.form.get('fournisseur_whatsapp', '').strip()
            observations         = request.form.get('observations_generales', '').strip()

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

            fournisseurs_carnet = Fournisseur.query.order_by(Fournisseur.nom.asc()).all()

            if not demandeur_nom:
                flash('Le nom du demandeur est obligatoire.', 'danger')
                return render_template('bdc/create.html',
                                       demandeur_defaut=current_user.nom_complet,
                                       service_defaut=current_user.role_label,
                                       fournisseurs_carnet=fournisseurs_carnet)

            lignes_valides = [(d.strip(), q, o.strip())
                               for d, q, o in zip(designations, quantites, obs_lignes)
                               if d.strip()]
            if not lignes_valides:
                flash('Veuillez saisir au moins une pièce.', 'danger')
                return render_template('bdc/create.html',
                                       demandeur_defaut=current_user.nom_complet,
                                       service_defaut=current_user.role_label,
                                       fournisseurs_carnet=fournisseurs_carnet)

            # Condition stricte : si le DT ou la personne habilitée par le DT ne valide pas la transmission du bon,
            # la validation pour la création d'un bon de commande ne peut pas se faire.
            valider_trans = request.form.get('valider_transmission') in ('1', 'true', 'on')
            est_habilite_validation = peut_valider_dt(current_user)

            if est_habilite_validation and valider_trans:
                statut_initial = 'validee'
            else:
                statut_initial = 'en_attente'

            # Créer ou mettre à jour le fournisseur dans le carnet
            if fournisseur:
                f_obj = Fournisseur.query.filter(func.lower(Fournisseur.nom) == func.lower(fournisseur)).first()
                if not f_obj:
                    f_obj = Fournisseur(nom=fournisseur, whatsapp=fournisseur_whatsapp)
                    db.session.add(f_obj)
                elif fournisseur_whatsapp and not f_obj.whatsapp:
                    f_obj.whatsapp = fournisseur_whatsapp

            bdc = BonDeCommande(
                numero=get_next_numero(),
                code_securise=secrets.token_urlsafe(16),
                type_bon=type_bon,
                createur_id=current_user.id,
                demandeur_nom=demandeur_nom,
                service_departement=service,
                fournisseur=fournisseur,
                fournisseur_whatsapp=fournisseur_whatsapp,
                vehicule_nom=vehicule_nom,
                vehicule_immatriculation=vehicule_immat,
                transporteur=transporteur,
                observations_generales=observations,
                statut=statut_initial,
            )
            if statut_initial == 'validee':
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
            if statut_initial == 'validee':
                enregistrer_action(bdc, 'validation_dt',
                                    ancien_statut='en_attente', nouveau_statut='validee',
                                    details=f"Transmission validée dès création par {current_user.nom_complet} ({current_user.role_label})")

            db.session.commit()

            # Si validé dès la création par le DT ou la personne habilitée, expédier automatiquement par WhatsApp si actif
            if statut_initial == 'validee':
                auto_wa = ConfigurationSysteme.get('whatsapp_auto_validation', 'false').lower() == 'true'
                if auto_wa and bdc.fournisseur_whatsapp:
                    base_url = request.host_url.rstrip('/')
                    if 'taxigab-bdc.com' in request.host:
                        base_url = 'https://taxigab-bdc.com'
                    lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"
                    dest_nom = bdc.fournisseur or 'Fournisseur'
                    msg_wa = (
                        f"Bonjour {dest_nom},\n\n"
                        f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
                        f"validé par la Direction Technique.\n\n"
                        f"📄 Consultez et téléchargez votre bon directement via ce lien :\n{lien_public_pdf}\n\n"
                        f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
                        f"Direction Technique TAXI GAB+"
                    )
                    succes, detail = envoyer_whatsapp_serveur(bdc.fournisseur_whatsapp, msg_wa, pdf_url=lien_public_pdf)
                    if succes:
                        bdc.whatsapp_envoye = True
                        bdc.date_envoi_whatsapp = datetime.now()
                        enregistrer_action(bdc, 'envoi_whatsapp', details=f"Automatique après validation création DT à {bdc.fournisseur_whatsapp} ({detail})")
                        db.session.commit()
                        flash(f'Bon de commande N°{bdc.numero} créé, validé et transmis automatiquement au fournisseur sur WhatsApp !', 'success')
                        return redirect(url_for('bdc_view', id=bdc.id))

                flash(f'Bon de commande N°{bdc.numero} créé et validé avec succès !', 'success')
            else:
                flash(f'Bon de commande N°{bdc.numero} créé et placé en attente : sa validation est soumise à la validation de transmission par la Direction Technique.', 'info')

            return redirect(url_for('bdc_view', id=bdc.id))

        fournisseurs_carnet = Fournisseur.query.order_by(Fournisseur.nom.asc()).all()
        return render_template('bdc/create.html',
                               demandeur_defaut=current_user.nom_complet,
                               service_defaut=current_user.role_label,
                               fournisseurs_carnet=fournisseurs_carnet)

    # ─── VOIR UN BDC ──────────────────────────────────────────────────────
    @app.route('/bdc/<int:id>')
    @login_required
    def bdc_view(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)

        if not bdc.code_securise:
            bdc.ensure_code_securise()
            db.session.commit()

        base_url = request.host_url.rstrip('/')
        if 'taxigab-bdc.com' in request.host:
            base_url = 'https://taxigab-bdc.com'
        lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"

        dest_nom = bdc.fournisseur or 'Fournisseur'
        msg_wa = (
            f"Bonjour {dest_nom},\n\n"
            f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"📄 Consultez et téléchargez votre bon directement via ce lien :\n{lien_public_pdf}\n\n"
            f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
            f"Direction Technique TAXI GAB+"
        )
        phone_clean = re.sub(r'[^0-9]', '', bdc.fournisseur_whatsapp or '')
        if phone_clean:
            whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_wa)}"
        else:
            whatsapp_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_wa)}"

        # Message de relance spécifique listant les pièces en attente
        pieces_manquantes_txt = ""
        for p in bdc.pieces_en_attente:
            pieces_manquantes_txt += f"• {p.quantite_restante}x {p.designation}\n"

        if not pieces_manquantes_txt.strip():
            pieces_manquantes_txt = "• (Toutes les pièces de la commande)\n"

        msg_relance_wa = (
            f"⚠️ RAPPEL DE COMMANDE — TAXI GAB+\n"
            f"Bonjour {dest_nom},\n\n"
            f"Nous faisons suite au Bon de Commande officiel N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"📦 Pièces toujours en attente de livraison au garage :\n"
            f"{pieces_manquantes_txt}\n"
            f"📄 Consultez votre bon officiel en ligne :\n{lien_public_pdf}\n\n"
            f"Merci de bien vouloir nous confirmer la disponibilité et le délai de livraison de ces pièces au garage.\n\n"
            f"Direction Technique TAXI GAB+"
        )
        if phone_clean:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_relance_wa)}"
        else:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_relance_wa)}"

        return render_template('bdc/view.html',
                               bdc=bdc,
                               whatsapp_url=whatsapp_url,
                               whatsapp_relance_url=whatsapp_relance_url,
                               lien_public_pdf=lien_public_pdf,
                               msg_wa=msg_wa,
                               msg_relance_wa=msg_relance_wa,
                               peut_valider=peut_valider_dt(current_user),
                               peut_annuler=peut_annuler(current_user, bdc),
                               peut_gerer_stock=peut_gerer_stock(current_user),
                               fournisseurs_carnet=Fournisseur.query.order_by(Fournisseur.nom.asc()).all())

    @app.route('/bdc/<int:id>/modifier_whatsapp', methods=['POST'])
    @login_required
    def bdc_modifier_whatsapp(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)
        num_wa = request.form.get('fournisseur_whatsapp', '').strip()
        bdc.fournisseur_whatsapp = num_wa
        if bdc.fournisseur:
            f_obj = Fournisseur.query.filter(func.lower(Fournisseur.nom) == func.lower(bdc.fournisseur)).first()
            if f_obj:
                f_obj.whatsapp = num_wa
        db.session.commit()
        flash(f'Numéro WhatsApp mis à jour : {num_wa or "Non renseigné"}', 'success')
        return redirect(url_for('bdc_view', id=id))

    # ─── ENVOYER LE BON PAR WHATSAPP (DIRECT OU SERVEUR) ───────────────────
    @app.route('/bdc/<int:id>/envoyer_whatsapp_serveur', methods=['GET', 'POST'])
    @login_required
    def bdc_envoyer_whatsapp_serveur(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)

        if getattr(current_user, 'est_spectateur', False):
            flash("Accès refusé : les comptes spectateurs ne peuvent pas effectuer d'envoi WhatsApp.", 'danger')
            return redirect(url_for('bdc_view', id=id))

        if bdc.statut not in ('validee', 'livree', 'en_stock', 'recuperee_transporteur', 'cloturee'):
            flash('Le bon doit être validé par le DT avant de pouvoir être transmis.', 'warning')
            return redirect(url_for('bdc_view', id=id))

        if not bdc.fournisseur_whatsapp:
            flash("Aucun numéro WhatsApp n'est renseigné pour ce fournisseur. Veuillez renseigner le numéro ci-dessous.", 'danger')
            return redirect(url_for('bdc_view', id=id))

        if not bdc.code_securise:
            bdc.ensure_code_securise()
            db.session.commit()

        base_url = request.host_url.rstrip('/')
        if 'taxigab-bdc.com' in request.host:
            base_url = 'https://taxigab-bdc.com'
        lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"

        dest_nom = bdc.fournisseur or 'Fournisseur'
        msg_wa = (
            f"Bonjour {dest_nom},\n\n"
            f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"📄 Consultez et téléchargez votre bon directement via ce lien :\n{lien_public_pdf}\n\n"
            f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
            f"Direction Technique TAXI GAB+"
        )

        phone_clean = re.sub(r'[^0-9]', '', bdc.fournisseur_whatsapp or '')
        if phone_clean:
            whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_wa)}"
        else:
            whatsapp_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_wa)}"

        nom_user = current_user.nom_complet or getattr(current_user, 'username', 'Utilisateur')

        # Mode direct (ouverture directe de WhatsApp sur mobile ou PC)
        if request.args.get('direct') == '1' or request.form.get('direct') == '1':
            bdc.whatsapp_envoye = True
            bdc.date_envoi_whatsapp = datetime.now()
            enregistrer_action(bdc, 'envoi_whatsapp',
                               details=f"Bon transmis sur WhatsApp ({bdc.fournisseur_whatsapp}) par {nom_user}")
            db.session.commit()
            return redirect(whatsapp_url)

        # Mode serveur (API UltraMsg / GreenAPI / Webhook)
        succes, detail = envoyer_whatsapp_serveur(bdc.fournisseur_whatsapp, msg_wa, pdf_url=lien_public_pdf)
        if succes:
            bdc.whatsapp_envoye = True
            bdc.date_envoi_whatsapp = datetime.now()
            enregistrer_action(bdc, 'envoi_whatsapp',
                               details=f"Envoyé par le serveur à {bdc.fournisseur_whatsapp} ({detail}) par {nom_user}")
            db.session.commit()
            flash(f"✅ Bon de commande transmis automatiquement avec succès au fournisseur via WhatsApp !", "success")
        else:
            flash(f"⚠️ Passerelle WhatsApp serveur : {detail}. Vous pouvez utiliser le bouton vert WhatsApp pour envoyer directement.", "warning")

        return redirect(url_for('bdc_view', id=id))

    # ─── RELANCER LE FOURNISSEUR PAR WHATSAPP (+24H OU MANUEL) ───────────
    @app.route('/bdc/<int:id>/relancer_whatsapp', methods=['GET', 'POST'])
    @login_required
    def bdc_relancer_whatsapp(id):
        bdc = db.session.get(BonDeCommande, id)
        if not bdc:
            abort(404)

        if getattr(current_user, 'est_spectateur', False):
            flash("Accès refusé : les comptes spectateurs ne peuvent pas émettre de relance.", 'danger')
            return redirect(url_for('bdc_view', id=id))

        if not bdc.fournisseur_whatsapp:
            flash("Aucun numéro WhatsApp n'est renseigné pour ce fournisseur. Veuillez renseigner le numéro ci-dessous.", 'danger')
            return redirect(url_for('bdc_view', id=id))

        if not bdc.code_securise:
            bdc.ensure_code_securise()
            db.session.commit()

        base_url = request.host_url.rstrip('/')
        if 'taxigab-bdc.com' in request.host:
            base_url = 'https://taxigab-bdc.com'
        lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"

        dest_nom = bdc.fournisseur or 'Fournisseur'
        pieces_manquantes_txt = ""
        for p in bdc.pieces_en_attente:
            pieces_manquantes_txt += f"• {p.quantite_restante}x {p.designation}\n"

        if not pieces_manquantes_txt.strip():
            pieces_manquantes_txt = "• (Toutes les pièces de la commande)\n"

        msg_relance_wa = (
            f"⚠️ RAPPEL DE COMMANDE — TAXI GAB+\n"
            f"Bonjour {dest_nom},\n\n"
            f"Nous faisons suite au Bon de Commande officiel N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"📦 Pièces toujours en attente de livraison au garage :\n"
            f"{pieces_manquantes_txt}\n"
            f"📄 Consultez votre bon officiel en ligne :\n{lien_public_pdf}\n\n"
            f"Merci de bien vouloir nous confirmer la disponibilité et le délai de livraison de ces pièces au garage.\n\n"
            f"Direction Technique TAXI GAB+"
        )

        phone_clean = re.sub(r'[^0-9]', '', bdc.fournisseur_whatsapp or '')
        if phone_clean:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_relance_wa)}"
        else:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_relance_wa)}"

        nom_user = current_user.nom_complet or getattr(current_user, 'username', 'Utilisateur')

        # Mode direct (ouverture directe WhatsApp pour mobile et desktop)
        if request.args.get('direct') == '1' or request.form.get('direct') == '1':
            bdc.nb_relances_whatsapp = (bdc.nb_relances_whatsapp or 0) + 1
            bdc.date_derniere_relance = datetime.now()
            if not bdc.whatsapp_envoye:
                bdc.whatsapp_envoye = True
                bdc.date_envoi_whatsapp = datetime.now()
            nb = bdc.nb_relances_whatsapp
            enregistrer_action(bdc, 'relance_whatsapp',
                               details=f"Relance N°{nb} ouverte sur WhatsApp ({bdc.fournisseur_whatsapp}) par {nom_user}")
            db.session.commit()
            return redirect(whatsapp_relance_url)

        # Mode serveur (via passerelle API UltraMsg / GreenAPI / Webhook)
        succes, detail = envoyer_whatsapp_serveur(bdc.fournisseur_whatsapp, msg_relance_wa, pdf_url=lien_public_pdf)
        bdc.nb_relances_whatsapp = (bdc.nb_relances_whatsapp or 0) + 1
        bdc.date_derniere_relance = datetime.now()
        if not bdc.whatsapp_envoye:
            bdc.whatsapp_envoye = True
            bdc.date_envoi_whatsapp = datetime.now()
        nb = bdc.nb_relances_whatsapp

        enregistrer_action(bdc, 'relance_whatsapp',
                           details=f"Relance N°{nb} émise à {bdc.fournisseur_whatsapp} ({detail}) par {nom_user}")
        db.session.commit()

        if succes:
            flash(f"✅ Relance N°{nb} transmise automatiquement avec succès au fournisseur sur WhatsApp !", "success")
        else:
            flash(f"ℹ️ Relance N°{nb} enregistrée dans le suivi. Passerelle serveur : {detail}. Vous pouvez envoyer directement via le bouton vert WhatsApp.", "info")

        return redirect(url_for('bdc_view', id=id))

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
        bdc.ensure_code_securise()
        enregistrer_action(bdc, 'validation_dt', ancien_statut=ancien, nouveau_statut='validee',
                            details=f"Transmission validée par {current_user.nom_complet}")
        db.session.commit()

        # Envoi automatique par le serveur si l'option est activée
        auto_wa = ConfigurationSysteme.get('whatsapp_auto_validation', 'false').lower() == 'true'
        if auto_wa and bdc.fournisseur_whatsapp:
            base_url = request.host_url.rstrip('/')
            if 'taxigab-bdc.com' in request.host:
                base_url = 'https://taxigab-bdc.com'
            lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"
            dest_nom = bdc.fournisseur or 'Fournisseur'
            msg_wa = (
                f"Bonjour {dest_nom},\n\n"
                f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
                f"validé par la Direction Technique.\n\n"
                f"📄 Consultez et téléchargez votre bon directement via ce lien :\n{lien_public_pdf}\n\n"
                f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
                f"Direction Technique TAXI GAB+"
            )
            succes, detail = envoyer_whatsapp_serveur(bdc.fournisseur_whatsapp, msg_wa, pdf_url=lien_public_pdf)
            if succes:
                bdc.whatsapp_envoye = True
                bdc.date_envoi_whatsapp = datetime.now()
                enregistrer_action(bdc, 'envoi_whatsapp', details=f"Automatique après validation DT à {bdc.fournisseur_whatsapp} ({detail})")
                db.session.commit()
                flash(f'Transmission du bon N°{bdc.numero} validée avec succès et transmise automatiquement au fournisseur sur WhatsApp !', 'success')
                return redirect(url_for('bdc_view', id=id))

        flash(f'Transmission du bon N°{bdc.numero} validée avec succès.', 'success')
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
        if bdc.statut != 'validee':
            flash("Ce bon ne peut pas être marqué comme livré car sa transmission n'a pas encore été validée par la Direction Technique.", 'warning')
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
        if bdc.statut not in ('en_stock', 'livree', 'validee'):
            flash("Ce bon ne peut pas être marqué comme récupéré car sa transmission n'a pas encore été validée par la Direction Technique.", 'warning')
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

    # ─── PDF PUBLIC SÉCURISÉ FOURNISSEUR (ACCÈS DIRECT SANS COMPTE) ───────
    @app.route('/commande/pdf/<string:code_securise>')
    def bdc_public_pdf(code_securise):
        bdc = BonDeCommande.query.filter_by(code_securise=code_securise).first()
        if not bdc:
            abort(404)

        # Si le bon est en attente de validation ou refusé/annulé, afficher la page d'attente explicative
        if bdc.statut in ('en_attente', 'refusee', 'annulee'):
            return render_template('bdc/public_waiting.html', bdc=bdc)

        # Si validé par le DT (ou statut ultérieur) : servir le PDF officiel
        pdf_bytes = generate_bdc_pdf(bdc, Config, avec_reception=False)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"{bdc.numero_affiche.replace('/', '-')}.pdf"
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

        # Carnet complet des fournisseurs enregistrés
        carnet_fournisseurs = Fournisseur.query.order_by(Fournisseur.nom.asc()).all()

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
                               stats_fournisseurs=stats_fournisseurs,
                               carnet_fournisseurs=carnet_fournisseurs)

    @app.route('/fournisseurs/ajouter', methods=['POST'])
    @login_required
    def fournisseur_ajouter():
        nom = request.form.get('nom', '').strip()
        if not nom:
            flash('Le nom du fournisseur est obligatoire.', 'danger')
            return redirect(url_for('fournisseurs'))
        f_existant = Fournisseur.query.filter(func.lower(Fournisseur.nom) == func.lower(nom)).first()
        if f_existant:
            flash(f'Le fournisseur « {nom} » existe déjà.', 'warning')
            return redirect(url_for('fournisseurs'))
        
        nouveau_f = Fournisseur(
            nom=nom,
            contact_nom=request.form.get('contact_nom', '').strip(),
            telephone=request.form.get('telephone', '').strip(),
            whatsapp=request.form.get('whatsapp', '').strip(),
            email=request.form.get('email', '').strip(),
            adresse=request.form.get('adresse', '').strip()
        )
        db.session.add(nouveau_f)
        db.session.commit()
        flash(f'Fournisseur « {nom} » enregistré dans le carnet avec succès.', 'success')
        return redirect(url_for('fournisseurs'))

    @app.route('/fournisseurs/ajouter_ajax', methods=['POST'])
    @login_required
    def fournisseur_ajouter_ajax():
        nom = request.form.get('nom', '').strip()
        whatsapp = request.form.get('whatsapp', '').strip()
        if not nom:
            return jsonify({'success': False, 'message': 'Le nom du fournisseur est obligatoire.'}), 400

        f_existant = Fournisseur.query.filter(func.lower(Fournisseur.nom) == func.lower(nom)).first()
        if f_existant:
            if whatsapp:
                f_existant.whatsapp = whatsapp
                db.session.commit()
            return jsonify({
                'success': True,
                'id': f_existant.id,
                'nom': f_existant.nom,
                'whatsapp': f_existant.whatsapp or ''
            })

        nouveau_f = Fournisseur(
            nom=nom,
            whatsapp=whatsapp,
            telephone=request.form.get('telephone', '').strip(),
            contact_nom=request.form.get('contact_nom', '').strip()
        )
        db.session.add(nouveau_f)
        db.session.commit()
        return jsonify({
            'success': True,
            'id': nouveau_f.id,
            'nom': nouveau_f.nom,
            'whatsapp': nouveau_f.whatsapp or ''
        })

    @app.route('/fournisseurs/<int:id>/modifier', methods=['POST'])
    @login_required
    def fournisseur_modifier(id):
        f_obj = db.session.get(Fournisseur, id)
        if not f_obj:
            abort(404)
        nom = request.form.get('nom', '').strip()
        if not nom:
            flash('Le nom du fournisseur est obligatoire.', 'danger')
            return redirect(url_for('fournisseurs'))
        f_obj.nom = nom
        f_obj.contact_nom = request.form.get('contact_nom', '').strip()
        f_obj.telephone = request.form.get('telephone', '').strip()
        f_obj.whatsapp = request.form.get('whatsapp', '').strip()
        f_obj.email = request.form.get('email', '').strip()
        f_obj.adresse = request.form.get('adresse', '').strip()
        db.session.commit()
        flash(f'Fiche fournisseur « {nom} » mise à jour avec succès.', 'success')
        return redirect(url_for('fournisseurs'))

    @app.route('/fournisseurs/<int:id>/supprimer', methods=['POST'])
    @login_required
    def fournisseur_supprimer(id):
        f_obj = db.session.get(Fournisseur, id)
        if not f_obj:
            abort(404)
        nom = f_obj.nom
        db.session.delete(f_obj)
        db.session.commit()
        flash(f'Fournisseur « {nom} » supprimé du carnet.', 'info')
        return redirect(url_for('fournisseurs'))

    # ─── HISTORIQUE DU MOIS EN COURS (GROUPÉ PAR BON) ─────────────────────
    @app.route('/historique')
    @login_required
    def historique():
        if not peut_voir_historique(current_user):
            abort(403)

        now = datetime.utcnow()
        # Par défaut : mois en cours
        selected_mois = request.args.get('mois', now.strftime('%Y-%m'))
        f_numero      = request.args.get('numero', '').strip()
        f_user        = request.args.get('user', '').strip()
        f_action      = request.args.get('action', '').strip()

        # Calcul de la plage de date du mois sélectionné
        try:
            annee, mois = map(int, selected_mois.split('-'))
            debut_mois = datetime(annee, mois, 1)
            if mois == 12:
                fin_mois = datetime(annee + 1, 1, 1)
            else:
                fin_mois = datetime(annee, mois + 1, 1)
        except Exception:
            annee, mois = now.year, now.month
            selected_mois = now.strftime('%Y-%m')
            debut_mois = datetime(annee, mois, 1)
            fin_mois = datetime(annee + 1, 1, 1) if mois == 12 else datetime(annee, mois + 1, 1)

        # Récupérer les actions du mois
        q_act = HistoriqueAction.query.join(BonDeCommande).filter(
            HistoriqueAction.timestamp >= debut_mois,
            HistoriqueAction.timestamp < fin_mois
        )

        if f_numero:
            try:
                q_act = q_act.filter(BonDeCommande.numero == int(f_numero))
            except ValueError:
                pass
        if f_action:
            q_act = q_act.filter(HistoriqueAction.type_action == f_action)
        if f_user:
            q_act = q_act.join(User, HistoriqueAction.user_id == User.id).filter(
                User.nom_complet.ilike(f'%{f_user}%'))

        actions = q_act.order_by(HistoriqueAction.timestamp.desc()).all()

        # Regrouper les actions par Bon de Commande
        # On extrait la liste des bons concernés
        bons_dict = {}
        for act in actions:
            bid = act.bdc_id
            if bid not in bons_dict:
                bons_dict[bid] = {
                    'bon': act.bon,
                    'actions': [],
                    'derniere_action': act.timestamp
                }
            bons_dict[bid]['actions'].append(act)

        # Trier les bons par dernière activité descendante
        bons_groupes = sorted(bons_dict.values(), key=lambda x: x['derniere_action'], reverse=True)

        # Mois disponibles dans l'historique
        dates_raw = db.session.query(HistoriqueAction.timestamp).order_by(HistoriqueAction.timestamp.desc()).all()
        mois_disponibles = sorted(list({d[0].strftime('%Y-%m') for d in dates_raw if d[0]}), reverse=True)
        if selected_mois not in mois_disponibles:
            mois_disponibles.insert(0, selected_mois)

        types_actions = db.session.query(HistoriqueAction.type_action).distinct().all()
        types_actions = [t[0] for t in types_actions]

        return render_template('history.html',
                               bons_groupes=bons_groupes,
                               selected_mois=selected_mois,
                               mois_disponibles=mois_disponibles,
                               types_actions=types_actions,
                               total_actions=len(actions),
                               filtres={'numero': f_numero, 'action': f_action, 'user': f_user, 'mois': selected_mois})

    # ─── ARCHIVES MENSUELLES INDÉPENDANTES ─────────────────────────────────
    @app.route('/archives')
    @login_required
    def archives():
        if not peut_voir_archives(current_user):
            abort(403)

        now = datetime.utcnow()
        # Liste de tous les mois archivés
        dates_raw = db.session.query(BonDeCommande.date_creation).order_by(BonDeCommande.date_creation.desc()).all()
        mois_disponibles = sorted(list({d[0].strftime('%Y-%m') for d in dates_raw if d[0]}), reverse=True)
        if not mois_disponibles:
            mois_disponibles = [now.strftime('%Y-%m')]

        selected_mois = request.args.get('mois', '')
        if not selected_mois:
            # Par défaut, le mois précédent ou le dernier mois disponible
            selected_mois = mois_disponibles[0]

        f_numero = request.args.get('numero', '').strip()
        f_date   = request.args.get('date', '').strip()
        f_statut = request.args.get('statut', '').strip()

        # Plage temporelle stricte du mois sélectionné
        try:
            annee, mois = map(int, selected_mois.split('-'))
            debut_mois = datetime(annee, mois, 1)
            fin_mois = datetime(annee + 1, 1, 1) if mois == 12 else datetime(annee, mois + 1, 1)
        except Exception:
            annee, mois = now.year, now.month
            selected_mois = now.strftime('%Y-%m')
            debut_mois = datetime(annee, mois, 1)
            fin_mois = datetime(annee + 1, 1, 1) if mois == 12 else datetime(annee, mois + 1, 1)

        q = BonDeCommande.query.filter(
            BonDeCommande.date_creation >= debut_mois,
            BonDeCommande.date_creation < fin_mois
        )

        if f_numero:
            try:
                q = q.filter(BonDeCommande.numero == int(f_numero))
            except ValueError:
                pass
        if f_statut:
            q = q.filter(BonDeCommande.statut == f_statut)
        if f_date:
            try:
                d_cible = datetime.strptime(f_date, '%Y-%m-%d').date()
                q = q.filter(cast(BonDeCommande.date_creation, db.Date) == d_cible)
            except Exception:
                pass

        bons = q.order_by(BonDeCommande.date_creation.desc()).all()

        # Statistiques d'archive pour le mois
        stats_archive = {
            'total_bons': len(bons),
            'clotures': sum(1 for b in bons if b.statut == 'cloturee'),
            'en_stock': sum(1 for b in bons if b.statut == 'en_stock'),
            'recuperees': sum(1 for b in bons if b.statut == 'recuperee_transporteur'),
            'annulees': sum(1 for b in bons if b.statut == 'annulee'),
            'total_pieces': sum(b.total_pieces for b in bons),
        }

        return render_template('archives.html',
                               bons=bons,
                               selected_mois=selected_mois,
                               mois_disponibles=mois_disponibles,
                               stats_archive=stats_archive,
                               filtres={'numero': f_numero, 'date': f_date, 'statut': f_statut, 'mois': selected_mois})

    # ─── SUIVI RÉCEPTIONS ─────────────────────────────────────────────────
    @app.route('/suivi')
    @login_required
    def suivi():
        q = BonDeCommande.query.filter(BonDeCommande.statut.in_(['validee', 'livree', 'en_stock', 'recuperee_transporteur']))
        f_vehicule = request.args.get('vehicule', '')
        f_fournisseur = request.args.get('fournisseur', '')
        f_transporteur = request.args.get('transporteur', '')
        f_statut_rec = request.args.get('statut_reception', '')
        f_relance = request.args.get('relance', '')

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

        # Liste globale de tous les bons en retard à +24h (pour bandeau d'alerte)
        bons_en_retard_24h = [b for b in bons if b.est_en_retard_24h]

        if f_relance == 'retard_24h':
            bons = [b for b in bons if b.est_en_retard_24h]
        elif f_relance == 'relance_faite':
            bons = [b for b in bons if (b.nb_relances_whatsapp or 0) > 0]

        if f_statut_rec:
            bons = [b for b in bons if any(l.statut_reception == f_statut_rec for l in b.lignes)]

        return render_template('suivi.html',
                               bons=bons,
                               bons_en_retard_24h=bons_en_retard_24h,
                               total_retard_24h=len(bons_en_retard_24h),
                               filtres={'vehicule': f_vehicule,
                                        'fournisseur': f_fournisseur,
                                        'transporteur': f_transporteur,
                                        'statut_reception': f_statut_rec,
                                        'relance': f_relance})

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
                u.peut_voir_historique    = request.form.get('peut_voir_historique') == 'on'
                u.peut_voir_archives      = request.form.get('peut_voir_archives') == 'on'
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
            user.peut_voir_historique    = request.form.get('peut_voir_historique') == 'on'
            user.peut_voir_archives      = request.form.get('peut_voir_archives') == 'on'
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
        """Supprime définitivement un utilisateur de la base de données."""
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        user = db.session.get(User, id)
        if not user:
            abort(404)
        if user.id == current_user.id:
            flash('Vous ne pouvez pas supprimer votre propre compte.', 'danger')
            return redirect(url_for('admin_users'))

        nom_supprime = user.nom_complet

        # Détacher l'utilisateur des bons créés et actions pour ne pas corrompre l'historique
        from database import BonDeCommande, HistoriqueAction
        BonDeCommande.query.filter_by(createur_id=user.id).update({'createur_id': None})
        BonDeCommande.query.filter_by(validateur_dt_id=user.id).update({'validateur_dt_id': None})
        BonDeCommande.query.filter_by(receptionniste_id=user.id).update({'receptionniste_id': None})
        BonDeCommande.query.filter_by(magasinier_stock_id=user.id).update({'magasinier_stock_id': None})
        BonDeCommande.query.filter_by(annulateur_id=user.id).update({'annulateur_id': None})
        HistoriqueAction.query.filter_by(user_id=user.id).update({'user_id': None})

        # Suppression définitive
        db.session.delete(user)
        db.session.commit()
        flash(f"L'utilisateur « {nom_supprime} » a été définitivement supprimé.", 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/utilisateurs/<int:id>/desactiver', methods=['POST'])
    @login_required
    def admin_user_toggle_status(id):
        """Active ou désactive un compte utilisateur sans le supprimer."""
        if not peut_gerer_utilisateurs(current_user):
            abort(403)
        user = db.session.get(User, id)
        if not user:
            abort(404)
        if user.id == current_user.id:
            flash('Action non autorisée sur votre propre compte.', 'danger')
            return redirect(url_for('admin_users'))
        user.actif = not user.actif
        db.session.commit()
        statut_txt = "activé" if user.actif else "désactivé"
        flash(f"Compte {user.nom_complet} {statut_txt}.", 'info')
        return redirect(url_for('admin_users'))

    # ─── CONFIGURATION PASSERELLE WHATSAPP ────────────────────────────────
    @app.route('/admin/whatsapp', methods=['GET', 'POST'])
    @login_required
    def admin_whatsapp():
        if not est_directeur_technique(current_user):
            flash("Accès réservé exclusivement au Directeur Technique.", "danger")
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'tester':
                tel_test = request.form.get('test_telephone', '').strip()
                if not tel_test:
                    flash('Veuillez renseigner un numéro de téléphone pour le test.', 'warning')
                else:
                    test_msg = (
                        "✅ Test de connexion TAXI GAB+\n\n"
                        "Votre passerelle WhatsApp serveur fonctionne parfaitement ! "
                        "Les bons de commande validés pourront désormais être expédiés automatiquement."
                    )
                    succes, detail = envoyer_whatsapp_serveur(tel_test, test_msg)
                    if succes:
                        flash(f"✅ Message test envoyé avec succès à {tel_test} ! ({detail})", "success")
                    else:
                        flash(f"❌ Résultat du test WhatsApp : {detail}", "danger")
            else:
                ConfigurationSysteme.set('whatsapp_passerelle', request.form.get('whatsapp_passerelle', 'ultramsg').strip())
                ConfigurationSysteme.set('whatsapp_instance_id', request.form.get('whatsapp_instance_id', '').strip())
                ConfigurationSysteme.set('whatsapp_token', request.form.get('whatsapp_token', '').strip())
                ConfigurationSysteme.set('whatsapp_custom_url', request.form.get('whatsapp_custom_url', '').strip())
                auto_val = 'true' if request.form.get('whatsapp_auto_validation') == 'on' else 'false'
                ConfigurationSysteme.set('whatsapp_auto_validation', auto_val)
                flash("Paramètres de la passerelle WhatsApp enregistrés avec succès.", "success")
                return redirect(url_for('admin_whatsapp'))

        configs = {
            'passerelle': ConfigurationSysteme.get('whatsapp_passerelle', 'ultramsg'),
            'instance_id': ConfigurationSysteme.get('whatsapp_instance_id', ''),
            'token': ConfigurationSysteme.get('whatsapp_token', ''),
            'custom_url': ConfigurationSysteme.get('whatsapp_custom_url', ''),
            'auto_validation': ConfigurationSysteme.get('whatsapp_auto_validation', 'true') == 'true',
        }
        return render_template('admin/whatsapp_settings.html', configs=configs)

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
                ("peut_creer_bdc", "BOOLEAN DEFAULT FALSE"),
                ("peut_valider_dt", "BOOLEAN DEFAULT FALSE"),
                ("peut_gerer_stock", "BOOLEAN DEFAULT FALSE"),
                ("peut_recuperer", "BOOLEAN DEFAULT FALSE"),
                ("peut_cloturer", "BOOLEAN DEFAULT FALSE"),
                ("peut_annuler", "BOOLEAN DEFAULT FALSE"),
                ("peut_gerer_utilisateurs", "BOOLEAN DEFAULT FALSE"),
                ("peut_voir_historique", "BOOLEAN DEFAULT FALSE"),
                ("peut_voir_archives", "BOOLEAN DEFAULT FALSE"),
                ("est_spectateur", "BOOLEAN DEFAULT FALSE"),
            ]
            for col_nom, col_type in colonnes_permissions:
                try:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col_nom} {col_type}"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Migration automatique des colonnes BDC
            colonnes_bdc = [
                ("fournisseur_whatsapp", "VARCHAR(64)"),
                ("code_securise", "VARCHAR(64)"),
                ("whatsapp_envoye", "BOOLEAN DEFAULT FALSE"),
                ("date_envoi_whatsapp", "TIMESTAMP"),
                ("nb_relances_whatsapp", "INTEGER DEFAULT 0"),
                ("date_derniere_relance", "TIMESTAMP"),
            ]
            for col_nom, col_type in colonnes_bdc:
                try:
                    db.session.execute(text(f"ALTER TABLE bons_de_commande ADD COLUMN {col_nom} {col_type}"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Paramètres par défaut de la passerelle WhatsApp
            try:
                if not ConfigurationSysteme.get('whatsapp_passerelle'):
                    ConfigurationSysteme.set('whatsapp_passerelle', 'ultramsg', 'Type de passerelle API WhatsApp')
                if not ConfigurationSysteme.get('whatsapp_instance_id'):
                    ConfigurationSysteme.set('whatsapp_instance_id', 'instance191342', 'Instance ID UltraMsg')
                if not ConfigurationSysteme.get('whatsapp_token'):
                    ConfigurationSysteme.set('whatsapp_token', 'c7t0v4viafqugtxl', 'Token UltraMsg')
                if not ConfigurationSysteme.get('whatsapp_auto_validation'):
                    ConfigurationSysteme.set('whatsapp_auto_validation', 'true', 'Envoi automatique dès validation DT')
            except Exception:
                db.session.rollback()

            # Remplir code_securise pour les bons existants qui n'en ont pas
            try:
                bons_sans_code = BonDeCommande.query.filter(
                    or_(BonDeCommande.code_securise == None, BonDeCommande.code_securise == '')
                ).all()
                for b in bons_sans_code:
                    b.code_securise = secrets.token_urlsafe(16)
                if bons_sans_code:
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
