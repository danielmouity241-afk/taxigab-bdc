"""
start_online.py — Lance le serveur BDC TAXI GAB+ avec le domaine officiel https://taxigab-bdc.com
"""
import os
import sys
import subprocess
import time
import webbrowser

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = os.path.join(BASE_DIR, 'cloudflared.exe')
OFFICIAL_URL = "https://taxigab-bdc.com"
DESKTOP_LINK_FILE = r"C:\Users\hp\Desktop\SITE OFFICIEL TAXI GAB.txt"

print("=" * 65, flush=True)
print("   TAXI GAB+ — Système BDC (Domaine Officiel)", flush=True)
print("=" * 65, flush=True)
print("1. Démarrage de l'application locale...", flush=True)

# Lancer Flask
flask_proc = subprocess.Popen(
    [sys.executable, 'app.py'],
    cwd=BASE_DIR
)

time.sleep(1.5)

print("2. Connexion au domaine officiel taxigab-bdc.com...", flush=True)

# Lancer Cloudflare tunnel permanent 'taxigab'
cf_proc = subprocess.Popen(
    [CLOUDFLARED, 'tunnel', 'run', 'taxigab'],
    cwd=BASE_DIR,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

time.sleep(2)

print()
print("=" * 65, flush=True)
print("   LE SITE OFFICIEL EST EN LIGNE ET ACTIF !", flush=True)
print("=" * 65, flush=True)
print()
print(f"👉 SITE OFFICIEL (à donner à tout le monde) :", flush=True)
print(f"   {OFFICIAL_URL}", flush=True)
print()
print("   Ce lien fonctionne partout dans le monde (ordinateur,", flush=True)
print("   téléphone, tablette en 4G/5G/Wi-Fi) avec certificat sécurisé HTTPS !", flush=True)
print()

# Écrire le lien dans un fichier texte sur le Bureau
try:
    with open(DESKTOP_LINK_FILE, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("  TAXI GAB+ — SITE WEB OFFICIEL DES BONS DE COMMANDE\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Adresse officielle pour tout le monde :\n")
        f.write(f"{OFFICIAL_URL}\n\n")
        f.write("-" * 60 + "\n")
        f.write("Rappel des identifiants :\n")
        f.write("  - Directeur Technique : dt          / DT@2026!\n")
        f.write("  - Adjoint             : dta         / DTA@2026!\n")
        f.write("  - Magasinier          : magasinier  / Mag@2026!\n")
        f.write("  - Transporteur        : transporteur / Trans@2026!\n")
        f.write("=" * 60 + "\n")
except Exception:
    pass

# Ouvrir le site officiel dans le navigateur
webbrowser.open(OFFICIAL_URL)

print("-" * 65, flush=True)
print("Rappel des identifiants :", flush=True)
print("  - Directeur Technique : dt          / DT@2026!", flush=True)
print("  - Adjoint             : dta         / DTA@2026!", flush=True)
print("  - Magasinier          : magasinier  / Mag@2026!", flush=True)
print("  - Transporteur        : transporteur / Trans@2026!", flush=True)
print("=" * 65, flush=True)
print("⚠️  Ne fermez pas cette fenêtre tant que vos équipes utilisent le système.", flush=True)
print()

try:
    flask_proc.wait()
except KeyboardInterrupt:
    print("\nArrêt du système...", flush=True)
    flask_proc.terminate()
    cf_proc.terminate()
