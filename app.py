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
from pdf_generator import generate_bdc_pdf, generate_bdc_image
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

    def get_ligne_tg_whatsapp(bdc):
        if bdc.vehicule_nom and bdc.vehicule_nom.strip():
            v = bdc.vehicule_nom.strip()
            if v.isdigit():
                v = f"TG{v}"
            immat = f" ({bdc.vehicule_immatriculation.strip()})" if bdc.vehicule_immatriculation and bdc.vehicule_immatriculation.strip() else ""
            return f"TG : {v}{immat}"
        elif getattr(bdc, 'est_garage', False) or getattr(bdc, 'type_bon', None) == 'garage':
            return "Affectation : GARAGE (Usage interne)"
        return ""

    def construire_message_whatsapp(bdc, lien_public=None, avec_lien=False):
        dest_nom = bdc.fournisseur or 'Fournisseur'
        ligne_tg = get_ligne_tg_whatsapp(bdc)
        ligne_tg_bloc = f"{ligne_tg}\n\n" if ligne_tg else "\n"
        if avec_lien and lien_public:
            return (
                f"Bonjour {dest_nom},\n"
                f"{ligne_tg_bloc}"
                f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
                f"validé par la Direction Technique.\n\n"
                f"📄 Consultez votre bon officiel en ligne :\n{lien_public}\n\n"
                f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
                f"Direction Technique TAXI GAB+"
            )
        return (
            f"Bonjour {dest_nom},\n"
            f"{ligne_tg_bloc}"
            f"Veuillez trouver ci-joint le Bon de Commande officiel TAXI GAB+ N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"Merci de bien vouloir préparer les pièces mentionnées.\n\n"
            f"Direction Technique TAXI GAB+"
        )

    def construire_message_relance_whatsapp(bdc, lien_public_pdf):
        dest_nom = bdc.fournisseur or 'Fournisseur'
        ligne_tg = get_ligne_tg_whatsapp(bdc)
        ligne_tg_bloc = f"{ligne_tg}\n\n" if ligne_tg else "\n"

        pieces_manquantes_txt = ""
        for p in getattr(bdc, 'pieces_en_attente', []):
            pieces_manquantes_txt += f"• {p.quantite_restante}x {p.designation}\n"

        if not pieces_manquantes_txt.strip():
            pieces_manquantes_txt = "• (Toutes les pièces de la commande)\n"

        return (
            f"⚠️ RAPPEL DE COMMANDE — TAXI GAB+\n"
            f"Bonjour {dest_nom},\n"
            f"{ligne_tg_bloc}"
            f"Nous faisons suite au Bon de Commande officiel N° {bdc.numero_affiche} "
            f"validé par la Direction Technique.\n\n"
            f"📦 Pièces toujours en attente de livraison au garage :\n"
            f"{pieces_manquantes_txt}\n"
            f"📄 Consultez votre bon officiel en ligne :\n{lien_public_pdf}\n\n"
            f"Merci de bien vouloir nous confirmer la disponibilité et le délai de livraison de ces pièces au garage.\n\n"
            f"Direction Technique TAXI GAB+"
        )

    @app.context_processor
    def inject_globals():
        return {
            'STATUTS_BDC': STATUTS_BDC,
            'STATUTS_COULEURS': STATUTS_COULEURS,
            'now': datetime.now(),
            'company_name': Config.COMPANY_NAME,
        }

    # ─── CONTRÔLE DE SANTÉ & ANTI-VEILLE CLOUD (KEEP-ALIVE) ───────────────
    @app.route('/ping')
    @app.route('/health')
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "taxigab-bdc",
            "timestamp": datetime.utcnow().isoformat()
        }), 200

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
                    lien_public_image = f"{base_url}{url_for('bdc_public_image', code_securise=bdc.code_securise)}"
                    lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"
                    msg_wa = construire_message_whatsapp(bdc)
                    succes, detail = envoyer_whatsapp_serveur(bdc.fournisseur_whatsapp, msg_wa, pdf_url=lien_public_pdf, image_url=lien_public_image)
                    if succes:
                        bdc.whatsapp_envoye = True
                        bdc.date_envoi_whatsapp = datetime.now()
                        enregistrer_action(bdc, 'envoi_whatsapp', details=f"Image automatique après validation création DT à {bdc.fournisseur_whatsapp} ({detail})")
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
        lien_public_image = f"{base_url}{url_for('bdc_public_image', code_securise=bdc.code_securise)}"
        lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"

        msg_wa = construire_message_whatsapp(bdc)
        msg_wa_direct = construire_message_whatsapp(bdc, lien_public_image, avec_lien=True)
        phone_clean = re.sub(r'[^0-9]', '', bdc.fournisseur_whatsapp or '')
        if phone_clean:
            whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_wa_direct)}"
        else:
            whatsapp_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_wa_direct)}"

        msg_relance_wa = construire_message_relance_whatsapp(bdc, lien_public_pdf)
        if phone_clean:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_relance_wa)}"
        else:
            whatsapp_relance_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_relance_wa)}"

        return render_template('bdc/view.html',
                               bdc=bdc,
                               whatsapp_url=whatsapp_url,
                               whatsapp_relance_url=whatsapp_relance_url,
                               lien_public_pdf=lien_public_pdf,
                               lien_public_image=lien_public_image,
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

        if getattr(current_user, 'est_spectateur', False) and current_user.role not in ('PDG', 'DG', 'Président Directeur Général', 'Directeur Général'):
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
        lien_public_image = f"{base_url}{url_for('bdc_public_image', code_securise=bdc.code_securise)}"
        lien_public_pdf = f"{base_url}{url_for('bdc_public_pdf', code_securise=bdc.code_securise)}"

        msg_wa = construire_message_whatsapp(bdc)
        nom_user = current_user.nom_complet or getattr(current_user, 'username', 'Utilisateur')

        # Mode direct (ouverture manuelle de WhatsApp si paramètre ?direct=1)
        if request.args.get('direct') == '1':
            msg_wa_direct = construire_message_whatsapp(bdc, lien_public_image, avec_lien=True)
            phone_clean = re.sub(r'[^0-9]', '', bdc.fournisseur_whatsapp or '')
            whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(msg_wa_direct)}" if phone_clean else f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_wa_direct)}"
            bdc.whatsapp_envoye = True
            bdc.date_envoi_whatsapp = datetime.now()
            enregistrer_action(bdc, 'envoi_whatsapp', details=f"Bon transmis sur WhatsApp ({bdc.fournisseur_whatsapp}) par {nom_user}")
            db.session.commit()
            return redirect(whatsapp_url)

        # Mode automatique UltraMsg : Envoi DIRECT de l'image haute définition dans le chat WhatsApp du fournisseur
        succes, detail = envoyer_whatsapp_serveur(
            destinataire_tel=bdc.fournisseur_whatsapp,
            message_texte=msg_wa,
            pdf_url=lien_public_pdf,
            pdf_nom=f"BDC_{bdc.numero_affiche.replace('/', '_')}",
            image_url=lien_public_image
        )

        if succes:
            bdc.whatsapp_envoye = True
            bdc.date_envoi_whatsapp = datetime.now()
            enregistrer_action(bdc, 'envoi_whatsapp',
                               details=f"Image officielle transmise au fournisseur ({bdc.fournisseur_whatsapp}) par {nom_user} via UltraMsg ({detail})")
            db.session.commit()
            flash(f"✅ Image officielle du Bon N° {bdc.numero_affiche} transmise avec succès au fournisseur sur WhatsApp ({bdc.fournisseur_whatsapp}) !", "success")
        else:
            flash(f"⚠️ Erreur lors de l'envoi de l'image : {detail}.", "danger")

        return redirect(url_for('bdc_view', id=id))


