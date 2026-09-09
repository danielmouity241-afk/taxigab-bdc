"""
test_app.py — Test automatique de la numérotation 0001 et des bons Garage vs Véhicule
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app import app
from database import db, User, BonDeCommande, LigneBDC, HistoriqueAction

def test_workflow():
    with app.app_context():
        HistoriqueAction.query.delete()
        LigneBDC.query.delete()
        BonDeCommande.query.delete()
        db.session.commit()

    client = app.test_client()

    print("1. Connexion en tant que DT...")
    res = client.post('/login', data={'username': 'dt', 'password': 'DT@2026!'}, follow_redirects=True)
    assert res.status_code == 200
    print("   [OK] Connexion DT réussie")

    print("2. Test de création du Bon N°0001 pour le GARAGE (Usage Interne)...")
    data_garage = {
        'type_bon': 'garage',
        'demandeur_nom': 'Chef d Atelier',
        'service_departement': 'Atelier Mécanique',
        'fournisseur': 'Gabon Outillage Pro',
        'observations_generales': 'Outillage interne pour maintenance garage',
        'designation[]': ['Clé dynamométrique 1/2', 'Jeu de tournevis isolés', 'Huile compresseur atelier'],
        'quantite[]': ['2', '3', '5'],
        'obs_ligne[]': ['Facom ou équivalent', 'Norme VDE', 'Bidon 5L']
    }
    res = client.post('/bdc/nouveau', data=data_garage, follow_redirects=True)
    assert res.status_code == 200
    print("   [OK] Bon Garage créé")

    with app.app_context():
        bdc1 = BonDeCommande.query.order_by(BonDeCommande.id.asc()).first()
        assert bdc1 is not None
        assert bdc1.numero == 1
        assert bdc1.numero_affiche == '0001'
        assert bdc1.est_garage is True
        assert bdc1.transporteur in (None, '')
        print(f"   [OK] Bon N°{bdc1.numero_affiche} enregistré comme Bon Garage (est_garage={bdc1.est_garage})")
        bdc1_id = bdc1.id

    print("3. Test du PDF pour le Bon Garage N°0001...")
    res = client.get(f'/bdc/{bdc1_id}/pdf')
    assert res.status_code == 200
    assert res.mimetype == 'application/pdf'
    assert len(res.data) > 1000
    print(f"   [OK] PDF N°0001 généré avec succès ({len(res.data)} octets)")

    print("4. Test de création du Bon N°0002 pour un VÉHICULE...")
    data_vehicule = {
        'type_bon': 'vehicule',
        'demandeur_nom': 'Daniel MOUITY',
        'service_departement': 'Direction Technique',
        'fournisseur': 'CFAO Motors Gabon',
        'vehicule_nom': 'TG 433',
        'vehicule_immatriculation': 'LH-819-AA',
        'transporteur': 'Transport Express Gabon',
        'observations_generales': 'Pièces révision périodique véhicule',
        'designation[]': ['Plaquettes de frein avant'],
        'quantite[]': ['2'],
        'obs_ligne[]': ['Origine constructeur']
    }
    res = client.post('/bdc/nouveau', data=data_vehicule, follow_redirects=True)
    assert res.status_code == 200
    print("   [OK] Bon Véhicule créé")

    with app.app_context():
        bdc2 = BonDeCommande.query.filter_by(numero=2).first()
        assert bdc2 is not None
        assert bdc2.numero_affiche == '0002'
        assert bdc2.est_garage is False
        assert bdc2.vehicule_nom == 'TG 433'
        assert bdc2.transporteur == 'Transport Express Gabon'
        print(f"   [OK] Bon N°{bdc2.numero_affiche} enregistré pour le véhicule {bdc2.vehicule_nom}")

    print("5. Test de la liste des bons et du tableau de bord...")
    res = client.get('/bdc')
    assert res.status_code == 200
    assert b'0001' in res.data
    assert b'0002' in res.data
    print("   [OK] Affichage 0001 et 0002 validé dans la liste")

    print("\n=======================================================")
    print("  TOUS LES TESTS SONT VALIDES A 100% AVEC SUCCES !")
    print("=======================================================")

if __name__ == '__main__':
    test_workflow()
