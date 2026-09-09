# TAXI GAB+ — Système de gestion des Bons de Commande

## Démarrage rapide

**Double-cliquez sur `start.bat`** — tout s'installe et démarre automatiquement.

Puis ouvrez votre navigateur sur : **http://localhost:5000**

---

## Comptes utilisateurs par défaut

| Identifiant   | Mot de passe  | Rôle                        |
|---------------|---------------|-----------------------------|
| `dt`          | `DT@2026!`    | Directeur Technique         |
| `dta`         | `DTA@2026!`   | Directeur Technique Adjoint |
| `magasinier`  | `Mag@2026!`   | Magasinier                  |
| `transporteur`| `Trans@2026!` | Transporteur                |

> ⚠️ **Changez ces mots de passe après la première connexion** (via Admin > Utilisateurs).

---

## Accès multi-postes (réseau local)

1. Lancez `start.bat` **sur le PC serveur** (le PC principal).
2. Trouvez l'adresse IP du PC serveur :
   - Ouvrez un terminal et tapez : `ipconfig`
   - Notez l'adresse IPv4 (ex: `192.168.1.100`)
3. Sur les **autres PC du réseau**, ouvrez le navigateur et allez sur :
   ```
   http://192.168.1.100:5000
   ```
4. Connectez-vous avec les identifiants ci-dessus.

---

## Fonctionnalités

### Bons de commande
- Création avec numérotation automatique (suite du N°751)
- Modèle fidèle au format TAXI GAB+ (logo, pied de page, signatures)
- **Export PDF** imprimable directement depuis le navigateur

### Workflow de validation
| Étape | Qui | Action |
|-------|-----|--------|
| 1 | DT, DTA ou Magasinier | Crée le bon |
| 2 | Système | Contrôle automatique |
| 3 | DT | Valide (obligatoire si créé par DTA/Magasinier) |
| 4 | Transporteur | Accepte ou refuse |
| 5 | Magasinier/DT | Enregistre la livraison |
| 6 | DT/DTA | Clôture le bon |

### Statuts des bons
- 🟡 **En attente** — créé, en attente de validation
- 🔵 **Validée** — validé par le DT
- 🩵 **Acceptée** — accepté par le transporteur
- 🔴 **Refusée** — refusé (avec motif)
- 🟢 **Livrée** — pièces reçues
- ⚫ **Clôturée** — traitement finalisé
- ⬛ **Annulée** — annulé avec trace conservée

### Suivi des réceptions
- Mise à jour pièce par pièce : Reçu / Partiel / Non reçu
- Quantité reçue par ligne
- Barre de progression par bon

### Historique & Traçabilité
- Journal d'audit complet (chaque action horodatée)
- Filtres : N° bon, action, utilisateur, période
- Toutes les transitions de statut enregistrées

### Tableau de bord
- KPI : aujourd'hui / semaine / mois / année
- Répartition par statut
- Alertes de validation (pour le DT)
- Dernières commandes

---

## Structure des fichiers

```
taxigab-bdc/
├── app.py              → Serveur Flask (routes)
├── database.py         → Modèles de données
├── pdf_generator.py    → Génération PDF
├── config.py           → Configuration
├── setup.py            → Installation initiale
├── requirements.txt    → Dépendances Python
├── start.bat           → Démarrage en 1 clic
├── data/
│   └── taxigab_bdc.db  → Base de données SQLite
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   └── images/logo_taxigab.png
└── templates/          → Pages HTML
```

---

## Prérequis

- **Python 3.9+** installé ([télécharger ici](https://www.python.org/downloads/))
- Connexion Internet pour la première installation des dépendances
- Fonctionne ensuite **entièrement hors ligne**

---

## Support

Système développé pour TAXI GAB+ | Version 1.0 | Septembre 2026
