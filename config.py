import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'taxigab-bdc-secret-2026!')
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
    LOGO_PATH = os.path.join(STATIC_DIR, 'images', 'logo_taxigab.png')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(DATA_DIR, 'taxigab_bdc.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BDC_START_NUMBER = 1  # Démarre au bon de commande 0001
    # Informations de l'entreprise (pied de page BDC)
    COMPANY_NAME = "TAXI GAB +"
    COMPANY_ADDRESS = "Libreville, OLOUMI GABON MALL, B.P 7186"
    COMPANY_TEL = "+241 62 14 05 05"
    COMPANY_NIF = "2024 0100 7748 P"
    COMPANY_RCCM = "GA-LBV-01-2024-B17-00034"
    COMPANY_FORME = "S.A.S.U"
    COMPANY_CAPITAL = "3 000 000 FCFA"
    # Réseau
    HOST = '0.0.0.0'   # Accessible depuis tous les postes du réseau
    PORT = 5000
    DEBUG = False
