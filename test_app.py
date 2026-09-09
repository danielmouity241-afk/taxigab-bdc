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
        assert bdc1.numero_affiche.startswith('BDC-')
        assert bdc1.numero_affiche.endswith('-00001')
        assert bdc1.est_garage is True
        assert bdc1.transporteur in (None, '')
        print(f"   [OK] Bon N°{bdc1.numero_affiche} enregistré comme Bon Garage (est_garage={bdc1.est_garage})")
        bdc1_id = bdc1.id

    print("3. Test du PDF standard et réception pour le Bon Garage...")
    res = client.get(f'/bdc/{bdc1_id}/pdf')
    assert res.status_code == 200
    assert res.mimetype == 'application/pdf'
    assert len(res.data) > 1000
    res_rec = client.get(f'/bdc/{bdc1_id}/pdf?avec_reception=1')
    assert res_rec.status_code == 200
    assert res_rec.mimetype == 'application/pdf'
    print(f"   [OK] PDFs Standard et Réception générés avec succès")

    print("4. Test de création du Bon N°00002 pour un VÉHICULE...")
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
        assert bdc2.numero_affiche.startswith('BDC-')
        assert bdc2.numero_affiche.endswith('-00002')
        assert bdc2.est_garage is False
        assert bdc2.vehicule_nom == 'TG 433'
        assert bdc2.transporteur == 'Transport Express Gabon'
        print(f"   [OK] Bon N°{bdc2.numero_affiche} enregistré pour le véhicule {bdc2.vehicule_nom}")

    print("5. Test de la liste des bons et du tableau de bord...")
    res = client.get('/bdc')
    assert res.status_code == 200
    assert b'00001' in res.data
    assert b'00002' in res.data
    print("   [OK] Affichage 00001 et 00002 validé dans la liste")

    print("6. Test de la réception décentralisée pièce par pièce...")
    with app.app_context():
        bdc1 = BonDeCommande.query.get(bdc1_id)
        lignes = list(bdc1.lignes)
        assert len(lignes) == 3
        l1_id, l2_id, l3_id = lignes[0].id, lignes[1].id, lignes[2].id

    # a) Marquer Ligne 1 comme LIVRÉ via l'action rapide
    res = client.post(f'/bdc/{bdc1_id}/reception_rapide/{l1_id}/livre', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        l1 = db.session.get(LigneBDC, l1_id)
        l2 = db.session.get(LigneBDC, l2_id)
        l3 = db.session.get(LigneBDC, l3_id)
        assert l1.statut_reception == 'recu'
        assert l1.quantite_recue == l1.quantite
        assert l2.statut_reception == 'non_recu'
        assert l3.statut_reception == 'non_recu'
        print(f"   [OK] Ligne 1 marquée Livrée, Lignes 2 et 3 toujours non reçues (décentralisation confirmée)")

    # b) Modifier Ligne 2 : Partiel (2/3) avec livreur tiers Tractafric
    res = client.post(f'/bdc/{bdc1_id}/reception', data={
        'ligne_id': l2_id,
        'statut_reception': 'partiel',
        'quantite_recue': '2',
        'livreur_nom': 'Tractafric Gabon',
        'note_reception': 'BL N°8849'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        l2 = db.session.get(LigneBDC, l2_id)
        assert l2.statut_reception == 'partiel'
        assert l2.quantite_recue == 2
        assert l2.livreur_nom == 'Tractafric Gabon'
        print(f"   [OK] Ligne 2 mise à jour : Partiel (2/3), livreur : {l2.livreur_nom}")

    # c) Vérifier que bdc_livrer ne modifie PAS les statuts individuels des lignes
    res = client.post(f'/bdc/{bdc1_id}/livrer', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        l1 = db.session.get(LigneBDC, l1_id)
        l2 = db.session.get(LigneBDC, l2_id)
        l3 = db.session.get(LigneBDC, l3_id)
        assert l1.statut_reception == 'recu'
        assert l2.statut_reception == 'partiel'  # Pas écrasé !
        assert l3.statut_reception == 'non_recu' # Pas écrasé !
        print(f"   [OK] Le statut global Livrée n'a pas écrasé les statuts individuels des pièces")

    # d) Tester le toggle rapide Non livré sur Ligne 1
    res = client.post(f'/bdc/{bdc1_id}/reception_rapide/{l1_id}/non_recu', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        l1 = db.session.get(LigneBDC, l1_id)
        assert l1.statut_reception == 'non_recu'
        assert l1.quantite_recue == 0
        print(f"   [OK] Ligne 1 basculée en Non livrée avec succès")

    # e) Vérifier l'affichage web view.html
    res = client.get(f'/bdc/{bdc1_id}')
    assert res.status_code == 200
    assert b'AFFECTATION V\xc3\x89HICULE' not in res.data
    assert b'Affectation :' not in res.data
    print("   [OK] Aucune mention de Affectation ou Flotte V\xc3\xa9hicule dans la page")

    print("7. Test du tableau de bord (sans Refusé) et du modal d'avertissement Caution...")
    res_dash = client.get('/dashboard')
    assert res_dash.status_code == 200
    assert b'Refus\xc3\xa9es' not in res_dash.data
    assert b'Refus\xc3\xa9' not in res_dash.data
    print("   [OK] Statut 'Refusé' complètement retiré du tableau de bord")

    res_create = client.get('/bdc/nouveau')
    assert res_create.status_code == 200
    assert b'modal-avertissement-caution' in res_create.data
    assert b'caution du transporteur' in res_create.data
    assert b'btn-confirmer-caution' in res_create.data
    print("   [OK] Modal d'avertissement rouge sur la caution du transporteur présent et actif")

    print("\n=======================================================")
    print("  TOUS LES TESTS SONT VALIDES A 100% AVEC SUCCES !")
    print("=======================================================")

if __name__ == '__main__':
    test_workflow()
