"""
setup.py — Initialisation du système TAXI GAB+ BDC
  1. Vérifie ou extrait le logo officiel
  2. Crée la base de données SQLite
  3. Crée les utilisateurs par défaut
"""
import os
import sys
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PNG = os.path.join(BASE_DIR, 'static', 'images', 'logo_taxigab.png')

def ensure_logo():
    """Vérifie la présence du logo officiel PNG ou le copie depuis les sources."""
    print("→ Vérification du logo TAXI GAB+...")
    if os.path.exists(LOGO_PNG) and os.path.getsize(LOGO_PNG) > 0:
        print(f"  ✓ Logo existant et prêt ({os.path.getsize(LOGO_PNG)} octets) : {LOGO_PNG}")
        return True

    # Chercher dans static/images les candidats
    img_dir = os.path.join(BASE_DIR, 'static', 'images')
    candidates = [
        os.path.join(img_dir, 'logo_taxigab_sit.png'),
        os.path.join(img_dir, 'logo_taxigab_bdc.jpg'),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            shutil.copyfile(c, LOGO_PNG)
            print(f"  ✓ Logo restauré à partir de {os.path.basename(c)} -> {LOGO_PNG}")
            return True

    print("  ⚠ Aucun fichier logo trouvé, mais le système continuera avec le nom d'entreprise textuel.")
    return False

def init_db():
    """Crée les tables et les utilisateurs par défaut."""
    print("→ Initialisation de la base de données...")
    try:
        from app import app
        from database import db, User

        with app.app_context():
            db.create_all()
            print("  ✓ Tables créées.")

            # Utilisateurs par défaut
            default_users = [
                {'username': 'dt',          'password': 'DT@2026!',     'nom': 'Directeur Technique',         'role': 'DT'},
                {'username': 'dta',         'password': 'DTA@2026!',    'nom': 'Directeur Technique Adjoint', 'role': 'DTA'},
                {'username': 'magasinier',  'password': 'Mag@2026!',    'nom': 'Magasinier Principal',        'role': 'magasinier'},
                {'username': 'transporteur','password': 'Trans@2026!',  'nom': 'Transporteur',                'role': 'transporteur'},
            ]

            created = 0
            for u_data in default_users:
                if not User.query.filter_by(username=u_data['username']).first():
                    u = User(
                        username=u_data['username'],
                        nom_complet=u_data['nom'],
                        role=u_data['role']
                    )
                    u.set_password(u_data['password'])
                    db.session.add(u)
                    created += 1

            db.session.commit()
            print(f"  ✓ {created} utilisateur(s) créé(s).")
            print()
            print("  Comptes par défaut configurés :")
            print("  ┌────────────────┬──────────────────┬──────────────────────────────┐")
            print("  │ Identifiant    │ Mot de passe     │ Rôle                         │")
            print("  ├────────────────┼──────────────────┼──────────────────────────────┤")
            print("  │ dt             │ DT@2026!         │ Directeur Technique          │")
            print("  │ dta            │ DTA@2026!        │ Directeur Technique Adjoint  │")
            print("  │ magasinier     │ Mag@2026!        │ Magasinier                   │")
            print("  │ transporteur   │ Trans@2026!      │ Transporteur                 │")
            print("  └────────────────┴──────────────────┴──────────────────────────────┘")
            return True
    except Exception as e:
        print(f"  ✗ Erreur initialisation DB: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("  TAXI GAB+ — Système de gestion des bons de commande")
    print("  Initialisation du système")
    print("=" * 60)
    print()

    logo_ok = ensure_logo()
    db_ok = init_db()

    print()
    if db_ok:
        print("✅ Système TAXI GAB+ prêt à l'emploi !")
    else:
        print("✗ Erreur lors de l'initialisation.")
        sys.exit(1)
