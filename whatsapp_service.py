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


def envoyer_whatsapp_serveur(destinataire_tel, message_texte, pdf_url=None, pdf_nom=None, image_url=None):
    """
    Envoie un message WhatsApp ou l'image officielle d'un bon directement depuis le serveur.
    Si image_url est spécifié, transmet l'image haute définition directement dans le fil WhatsApp du fournisseur.
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
            if image_url:
                url = f"https://api.ultramsg.com/{instance_id}/messages/image"
                payload = {
                    'token': token,
                    'to': tel_propre,
                    'image': image_url,
                    'caption': message_texte or '',
                }
            else:
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
            with urllib.request.urlopen(req, timeout=18) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body) if res_body else {}
                if res_json.get('sent') == 'true' or res_json.get('id'):
                    msg_type = "Image du Bon de Commande transmise" if image_url else "Message transmis"
                    return True, f"{msg_type} avec succès à UltraMsg (ID: {res_json.get('id', 'OK')})"
                elif 'error' in res_json:
                    return False, f"Erreur UltraMsg : {res_json.get('error')}"
                return True, "Transmission envoyée avec succès."

        elif passerelle == 'greenapi':
            # Green-API
            chat_id = f"{tel_propre}@c.us"
            if image_url:
                url = f"https://api.green-api.com/waInstance{instance_id}/sendFileByUrl/{token}"
                payload = {
                    'chatId': chat_id,
                    'urlFile': image_url,
                    'fileName': f"{pdf_nom or 'bon_de_commande'}.jpg",
                    'caption': message_texte or ''
                }
            else:
                url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{token}"
                payload = {
                    'chatId': chat_id,
                    'message': message_texte
                }
            data_json = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers={
                'Content-Type': 'application/json',
                'User-Agent': 'TaxiGab-BDC/1.0'
            })
            with urllib.request.urlopen(req, timeout=18) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body) if res_body else {}
                if 'idMessage' in res_json:
                    msg_type = "Image du Bon" if image_url else "Message"
                    return True, f"{msg_type} transmis avec succès à Green-API (ID: {res_json.get('idMessage')})"
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
                'image_url': image_url,
                'token': token
            }
            data_json = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers={
                'Content-Type': 'application/json',
                'User-Agent': 'TaxiGab-BDC/1.0'
            })
            with urllib.request.urlopen(req, timeout=18) as response:
                return True, "Image et message transmis au webhook personnalisé avec succès."

        elif passerelle == 'simulation':
            # Mode test / simulation interne
            cible = "Image du Bon" if image_url else "Message"
            return True, f"[SIMULATION] {cible} préparé pour {tel_propre} avec succès (Passerelle en mode simulation)."

        else:
            return False, f"Passerelle '{passerelle}' non reconnue."

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        return False, f"Erreur HTTP passerelle ({e.code}) : {err_msg[:160]}"
    except urllib.error.URLError as e:
        return False, f"Erreur de connexion à la passerelle WhatsApp : {e.reason}"
    except Exception as e:
        return False, f"Erreur inattendue : {str(e)}"
