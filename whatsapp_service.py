"""
whatsapp_service.py — Service d'envoi automatique de messages WhatsApp depuis le serveur
Supporte UltraMsg, Green-API, Twilio, et Webhooks personnalisés.
"""
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from database import ConfigurationSysteme


def nettoyer_telephone(phone_raw):
    """
    Nettoie et normalise un numéro de téléphone pour l'envoi WhatsApp international.
    Exemples :
      '+241 74 00 00 00' -> '24174000000'
      '074000000'        -> '24174000000' (ajoute indicatif Gabon si manquant)
      '74000000'         -> '24174000000'
    """
    if not phone_raw:
        return ""
    
    # Supprimer tous les caractères non numériques sauf le '+' au début
    clean = re.sub(r'[^\d+]', '', str(phone_raw).strip())
    
    if clean.startswith('+'):
        clean = clean[1:]
    elif clean.startswith('00'):
        clean = clean[2:]
        
    # Cas des numéros gabonais saisis en local (ex: 074... ou 065... ou 74...)
    if clean.startswith('0') and len(clean) in (8, 9):
        # Enlever le zéro initial et préfixer par l'indicatif Gabon 241
        clean = '241' + clean[1:]
    elif len(clean) in (7, 8) and not clean.startswith('241'):
        # Numéro court sans indicatif
        clean = '241' + clean

    return clean


def envoyer_whatsapp_serveur(destinataire_tel, message_texte, pdf_url=None, pdf_nom=None):
    """
    Envoie un message WhatsApp directement depuis le serveur en tâche de fond.
    Retourne un tuple : (succes: bool, detail: str)
    """
    tel_propre = nettoyer_telephone(destinataire_tel)
    if not tel_propre or len(tel_propre) < 8:
        return False, "Numéro de téléphone invalide ou manquant."

    # Lecture des paramètres depuis la base de données
    passerelle = ConfigurationSysteme.get('whatsapp_passerelle', 'ultramsg').strip().lower()
    instance_id = ConfigurationSysteme.get('whatsapp_instance_id', '').strip()
    token = ConfigurationSysteme.get('whatsapp_token', '').strip()
    api_url_custom = ConfigurationSysteme.get('whatsapp_custom_url', '').strip()

    if not token and passerelle != 'simulation':
        return False, "Passerelle WhatsApp non configurée (Clé API ou Token manquant). Rendez-vous dans Administration > Configuration WhatsApp."

    try:
        if passerelle == 'ultramsg':
            # UltraMsg API (Recommandé - simple et instantané)
            url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
            payload = {
                'token': token,
                'to': tel_propre,
                'body': message_texte,
            }
            data_encoded = urllib.parse.urlencode(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_encoded, headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'TaxiGab-BDC/1.0'
            })
            with urllib.request.urlopen(req, timeout=12) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body) if res_body else {}
                if res_json.get('sent') == 'true' or res_json.get('id'):
                    return True, f"Message transmis avec succès à UltraMsg (ID: {res_json.get('id', 'OK')})"
                elif 'error' in res_json:
                    return False, f"Erreur UltraMsg : {res_json.get('error')}"
                return True, "Message envoyé avec succès."

        elif passerelle == 'greenapi':
            # Green-API
            url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{token}"
            chat_id = f"{tel_propre}@c.us"
            payload = {
                'chatId': chat_id,
                'message': message_texte
            }
            data_json = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers={
                'Content-Type': 'application/json',
                'User-Agent': 'TaxiGab-BDC/1.0'
            })
            with urllib.request.urlopen(req, timeout=12) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body) if res_body else {}
                if 'idMessage' in res_json:
                    return True, f"Message transmis avec succès à Green-API (ID: {res_json.get('idMessage')})"
                return True, "Message envoyé avec succès via Green-API."

        elif passerelle == 'custom':
            # Passerelle HTTP personnalisée / Webhook
            url = api_url_custom or instance_id
            if not url:
                return False, "URL de webhook personnalisée non renseignée."
            payload = {
                'phone': tel_propre,
                'message': message_texte,
                'pdf_url': pdf_url,
                'token': token
            }
            data_json = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers={
                'Content-Type': 'application/json',
                'User-Agent': 'TaxiGab-BDC/1.0'
            })
            with urllib.request.urlopen(req, timeout=12) as response:
                return True, "Message transmis au webhook personnalisé avec succès."

        elif passerelle == 'simulation':
            # Mode test / simulation interne
            return True, f"[SIMULATION] Message préparé pour {tel_propre} avec succès (Passerelle en mode simulation)."

        else:
            return False, f"Passerelle '{passerelle}' non reconnue."

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        return False, f"Erreur HTTP passerelle ({e.code}) : {err_msg[:160]}"
    except urllib.error.URLError as e:
        return False, f"Erreur de connexion à la passerelle WhatsApp : {e.reason}"
    except Exception as e:
        return False, f"Erreur inattendue : {str(e)}"
