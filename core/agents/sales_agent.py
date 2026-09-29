"""
Mmove Sales Agent (Conseiller Commercial & Synthèse Experte)
Rédige la proposition commerciale percutante et personnalisée
en intégrant les métriques précises (Fréquentation, OTS, Visibilité)
et les conseils d'impact visuel M Move.
"""

import os
import re
import json
import ssl
import urllib.request
from typing import Dict, Any, List, Optional

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

SALES_SYSTEM_PROMPT = """### 1. RÔLE ET IDENTITÉ
Tu es l'**Agent Commercial Expert** de la société **M Move** (remorquepublicitaire.be).
* **Ta mission :** Vendre des campagnes d'affichage 8m² et conseiller les prospects sur leur stratégie et leur créativité.
* **Ton Ton :** Professionnel, dynamique, expert, chaleureux et percutant.

### 2. ARGUMENTS COMMERCIAUX CLÉS M MOVE
* **PUISSANCE :** N°1 de l'affichage mobile et remorque en Wallonie, réseau de plus de 300 faces stratégiques.
* **VISIBILITÉ & IMPACT :** Format 8m² géant immanquable, non noyé dans la masse publicitaire, visible 24h/24.
* **SERVICE "TOUT COMPRIS" :** Prix incluant la location de l'emplacement, l'impression grand format des bâches, le placement/pose et **toutes les taxes régionales et communales incluses**.
* **FLEXIBILITÉ :** Ciblage ultra-localisé au plus près de la zone de chalandise.

### 3. FORMATAGE STRICT DES RÉSULTATS (Style sobre, épuré et direct)

* **RÈGLES D'OR DE RÉDACTION :**
  - **VAS DROIT À L'ESSENTIEL :** Pas de remplissage. Sois clair, concis et efficace.
  - **PAS DE GRAS PARTOUT :** Soulage la lecture. N'utilise JAMAIS de gras sur les étiquettes ("Disponible dès", "Direction", "Trafic", "Contexte") ni sur chaque valeur. Réserve le gras uniquement pour le nom du panneau s'il n'est pas déjà dans un lien.
  - **SUPPRIME "Implantation directe" :** Ne mentionne JAMAIS "Implantation directe".
  - **AUCUNE "Face IN" OU "Face OUT" :** Parle UNIQUEMENT en termes de Direction de circulation (ex: Direction : Namur).
  - **RÉPONSE EN BULLET POINTS :** Présente chaque panneau de manière structurée et aérée.

* **STRUCTURE EXACTE PAR EMPLACEMENT :**
  • [#ID - Ville - Localisation ↗️](lien)
    - Disponible dès : Mois Année
    - Direction : [Direction]
    - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
    - Contexte : [Contexte de visibilité court]

* **DEMANDE DE DISPONIBILITÉ :**
  - Phrase d'intro sobre (ex: "Voici les disponibilités pour vos remorques à [Lieu] :").
  - Liste directe des emplacements selon le format ci-dessus.

### 4. CONSEILS CRÉATIFS & VISUELS
* **RÈGLE STRICTE :** Ne donne de conseils créatifs et visuels QUE si le prospect pose explicitement une question sur la création, le visuel, le graphisme, la conception de l'affiche ou les formats !
* Ne JAMAIS insérer de conseils créatifs lors d'une simple recherche de panneaux ou d'une demande de disponibilité (ex: "dispo à Wierde", "panneaux à Wavre") : cela surcharge inutilement l'échange.
* Si et seulement si le prospect demande des conseils sur son affiche ou sa création :
  1. **Règle des 7 mots maximum** : un message unique, court et percutant (attention de 3 à 5 secondes à 70 km/h).
  2. **Lisibilité XXL** : typographie bâton (sans-serif) lisible de loin.
  3. **Contraste fort** (ex: Jaune/Noir, Blanc/Rouge) : bannir les textes fins sur photos chargées.
  4. **Hero Shot** : une seule image forte, aucun pêle-mêle.
  5. **Call to Action direct** : fléchage clair ("À 500m à droite", "Sortie 4") ou nom/site court. **Bannir les QR codes** (inutilisables et dangereux en roulant).

### 5. SUPPORT TECHNIQUE & DÉLAIS
* Ne mentionner ces détails QUE si le client demande les spécifications techniques ou est prêt à réserver :
  * **Fichiers :** Fini 390x200 cm (Fichier avec bords perdus 392x202 cm), échelle 1/1, PDF vectoriel CMJN, 65 dpi min.
  * **Deadline :** Réception des fichiers avant le 15 du mois précédant la campagne.
  * **Envoi :** Email ou WeTransfer à `mmove@mediasee.be`.

### 6. MODE ADMINISTRATEUR / DEBUG ("Corentin")
* Si la requête indique `is_admin = true` ou que l'utilisateur s'identifie comme Corentin :
  * Sortir du rôle commercial strict.
  * Répondre techniquement, de façon transparente, en expliquant les scores, les coordonnées, les données de trafic brutes et la logique d'algorithme.
"""

class SalesAgent:
    """Agent Commercial Gemini Flash produisant la synthèse client finale."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", DEFAULT_API_KEY)
        self.model = model
        self.ssl_ctx = ssl._create_unverified_context()

    def generate_pitch(
        self,
        user_message: str,
        extracted_info: Dict[str, Any],
        candidate_panels: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Génère la recommandation commerciale sur mesure."""
        user_mentions_face = any(w in user_message.lower() for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        
        # Préparer le résumé synthétique des panneaux qualifiés
        panels_context = []
        for p in candidate_panels:
            if user_mentions_face:
                avail_months_str = ", ".join(
                    [f"{m['period_human']} ({m['face']})" for m in p.get("availability", {}).get("available_months", [])]
                )
            else:
                avail_months_str = ", ".join(
                    [f"{m['period_human']}" for m in p.get("availability", {}).get("available_months", [])]
                )

            dispo_human = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")
            if not user_mentions_face:
                dispo_human = re.sub(r"\s*\(Face[^\)]*\)", "", str(dispo_human), flags=re.IGNORECASE).strip()

            dir_str = p.get("direction_in") or p.get("direction_out") or "Double sens"

            panels_context.append({
                "id": p.get("id"),
                "ville": p.get("ville"),
                "localisation": p.get("localisation"),
                "province": p.get("province", ""),
                "direction": dir_str,
                "distance_km": p.get("distance_km"),
                "frequentation_jour": f"{p.get('frequentation_jour', 0):,}".replace(",", " "),
                "ots_mensuel": f"{p.get('ots_mensuel', 0):,}".replace(",", " "),
                "contexte_visibilite": p.get("contexte_visibilite"),
                "lien": p.get("lien", ""),
                "prochaine_dispo_mois": dispo_human,
                "mois_disponibles_periode": avail_months_str or f"Disponible dès {dispo_human}",
                "is_direct_match": p.get("is_direct_match", False),
                "photo_url": p.get("photo_url")
            })

        user_prompt_content = f"""
Demande du prospect : "{user_message}"

Critères extraits :
- Intention : {extracted_info.get('intent')}
- Période souhaitée : {extracted_info.get('target_periods') or 'Non spécifiée'}
- Lieux / Pôles cibles : {extracted_info.get('locations') or 'Wallonie globale'}
- Axes routiers : {extracted_info.get('axes') or 'Tous'}
- Secteur d'activité : {extracted_info.get('sector') or 'Général'}
- Mode Admin : {extracted_info.get('is_admin', False)}

Sélection des Meilleurs Panneaux Qualifiés ({len(candidate_panels)} retenus) :
{json.dumps(panels_context, ensure_ascii=False, indent=2)}

Rédige maintenant ta réponse commerciale selon les règles strictes suivantes :
1. Va droit à l'essentiel, sous forme de bullet points clairs, sobres et aérés.
2. PAS de gras partout : ne mets JAMAIS les étiquettes en gras (écris "Disponible dès :", "Direction :", "Trafic :", "Contexte :" sans astérisques de gras).
3. AUCUNE mention "Implantation directe".
4. AUCUNE mention "Face IN" ou "Face OUT" : uniquement la Direction (ex: Direction : Namur).
"""

        # Construction de l'historique de conversation
        formatted_contents = []
        if conversation_history:
            for turn in conversation_history[-4:]:  # 4 derniers tours max pour éviter toute surcharge
                role = "user" if turn.get("role") == "user" else "model"
                text = turn.get("text") or (turn.get("parts")[0].get("text") if turn.get("parts") else "")
                if text:
                    formatted_contents.append({"role": role, "parts": [{"text": text}]})

        formatted_contents.append({"role": "user", "parts": [{"text": user_prompt_content}]})

        payload = {
            "system_instruction": {
                "parts": [{"text": SALES_SYSTEM_PROMPT}]
            },
            "contents": formatted_contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 1500,
            }
        }

        candidate_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        data_bytes = json.dumps(payload).encode("utf-8")

        for mod in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    text_out = res_body["candidates"][0]["content"]["parts"][0]["text"]
                    return text_out
            except Exception as e:
                pass

        # Fallback local
        return self._generate_fallback_response(candidate_panels, extracted_info, user_message)

    def _generate_fallback_response(self, panels: List[Dict[str, Any]], extracted: Dict[str, Any], user_msg: str = "") -> str:
        """Génère une réponse structurée épurée et directe."""
        if not panels:
            return "Aucun emplacement correspondant à ces critères n'est disponible sur cette période. Souhaitez-vous élargir la recherche géographique ?"

        intent = extracted.get("intent", "")
        msg_lower = (user_msg or "").lower()
        is_dispo_query = intent == "check_availability" or any(w in msg_lower for w in ["dispo", "libre", "quand", "prochaine"])
        
        loc_list = extracted.get("locations", [])
        loc_str = f" à {', '.join(loc_list)}" if loc_list else ""
        
        if is_dispo_query:
            intro = f"Voici les disponibilités pour vos remorques 8m²{loc_str} :\n"
        else:
            intro = f"Voici la sélection d'emplacements 8m²{loc_str} :\n"

        lines = [intro]
        for p in panels:
            dist_str = f" (à {p['distance_km']} km)" if p.get("distance_km") and p.get("distance_km") > 0 else ""
            freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
            ots_str = f"{p.get('ots_mensuel', 0):,}".replace(",", " ")
            direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
            dispo_humaine = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")
            user_mentions_face = any(w in msg_lower for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
            if not user_mentions_face:
                dispo_humaine = re.sub(r"\s*\(Face[^\)]*\)", "", str(dispo_humaine), flags=re.IGNORECASE).strip()

            contexte = p.get('contexte_visibilite') or ''
            contexte_clean = re.sub(r"^\[Zoning\]\s*", "", contexte)

            lines.append(
                f"• [#{p['id']} - {p['ville']} - {p['localisation']} ↗️]({p['lien']})\n"
                f"  - Disponible dès : {dispo_humaine}\n"
                f"  - Direction : {direction}\n"
                f"  - Trafic : {freq_str} véh./jour (~{ots_str} OTS/mois){dist_str}\n"
                f"  - Contexte : {contexte_clean}\n"
            )

        is_creation_query = any(w in msg_lower for w in ["créat", "creat", "visuel", "affiche", "graphi", "design"])
        if is_creation_query:
            lines.append(
                "\n💡 Conseil pour votre création :\n"
                "• 7 mots maximum pour être lu à 70 km/h\n"
                "• Typographie bâton XXL sans empattement\n"
                "• Contraste élevé (fond/texte) et un seul visuel fort\n"
                "• Pas de QR code en bord de route"
            )
        return "\n".join(lines)
