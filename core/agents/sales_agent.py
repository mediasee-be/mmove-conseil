"""
Mmove Sales Agent (Conseiller Commercial & Synthèse Experte)
Rédige la proposition commerciale percutante et personnalisée
en intégrant les métriques précises (Fréquentation, OTS, Visibilité)
et les conseils d'impact visuel M Move.
"""

import os
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

### 3. FORMATAGE STRICT DES RÉSULTATS (Règles M Move)

* **SCÉNARIO A : Identification d'un emplacement ("C'est quel panneau ?", "Panneau près de...")**
  * Affiche UNIQUEMENT le nom cliquable : `[**#ID - Ville - Localisation** ↗️](lien)` (ne mets pas de crochets autour de l'ID à l'intérieur du lien, écris directement #ID).
  * Ajoute la visibilité : `(Fréquentation : [frequentation_jour] véh./j | OTS : [ots_mensuel]/mois)`.
  * Ne cite PAS les faces techniques IN/OUT.

* **SCÉNARIO B : Recommandation / Sélection de panneaux**
  * Présente la sélection sous forme de liste à puces structurée.
  * Pour chaque panneau, TOUJOURS inclure la disponibilité dès la première ligne :
    `* [**#ID - Ville - Localisation** ↗️](lien)`
      `* 📅 **Disponible dès :** [prochaine_dispo_mois]`
      `* 🚗 **Impact :** [frequentation_jour] véh./jour (~[ots_mensuel] OTS/mois)`
      `* 📍 **Direction :** [direction]`
      `* 👁️ **Contexte :** [contexte_visibilite]`
  * Ne cite pas les acronymes de régie bruts aux clients mais formule clairement (ex: "Disponible dès Décembre 2026 (Face OUT)").

* **SCÉNARIO C : Demande de disponibilité ("Quand est-ce libre ?")**
  * L'information N°1 à mettre en valeur immédiatement est la date de disponibilité : `📅 **Disponible dès : [prochaine_dispo_mois]**`.

* **LOCALITÉS SECONDAIRES & VILLAGES (ex: Wierde, Naninne, Sclayn, Haute Bise, etc.)** :
  * Si le client demande une localité ou village précis, mets en exergue le panneau qui y est implanté directement : `🎯 **Implantation directe à [Localité]**`.
  * Présente ensuite les panneaux périphériques comme des axes stratégiques complémentaires en précisant la distance (ex: `À seulement 1,2 km`).

* **STRUCTURE MULTI-MOIS (Obligatoire si la demande porte sur plusieurs mois)** :
  * Si la recherche porte sur un trimestre ou plusieurs mois (ex: "octobre à décembre", "fin d'année") :
  * Crée des sous-titres bien visibles pour chaque mois (`### Octobre 2026`, `### Novembre 2026`, etc.).
  * Liste sous chaque mois les panneaux disponibles pour ce mois précis.

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
        # Préparer le résumé synthétique des panneaux qualifiés
        panels_context = []
        for p in candidate_panels:
            avail_months_str = ", ".join(
                [f"{m['period_human']} ({m['face']})" for m in p.get("availability", {}).get("available_months", [])]
            )
            dispo_human = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")
            panels_context.append({
                "id": p.get("id"),
                "ville": p.get("ville"),
                "localisation": p.get("localisation"),
                "province": p.get("province", ""),
                "direction": p.get("direction_in") or p.get("direction_out") or "Double sens",
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

Rédige maintenant ta réponse commerciale percutante, chaleureuse et structurée conformément aux règles M Move.
Important : Mentionne explicitement pour chaque emplacement la prochaine date de disponibilité dès le début de chaque puce !
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
        """Génère une réponse structurée locale si l'API est temporairement indisponible."""
        if not panels:
            return "Bonjour ! Aucun emplacement correspondant exactement à ces critères n'est disponible sur cette période. Souhaitez-vous élargir le rayon géographique ou explorer d'autres mois ?"

        intent = extracted.get("intent", "")
        msg_lower = (user_msg or "").lower()
        is_dispo_query = intent == "check_availability" or any(w in msg_lower for w in ["dispo", "libre", "quand", "prochaine"])
        
        loc_list = extracted.get("locations", [])
        loc_str = f" à **{', '.join(loc_list)}**" if loc_list else ""
        
        if is_dispo_query:
            intro = f"Bonjour ! Voici les **prochaines disponibilités** pour vos remorques 8m² M Move{loc_str} :\n"
        else:
            intro = f"Bonjour ! Voici notre sélection d'emplacements stratégiques 8m² M Move{loc_str} :\n"

        lines = [intro]
        for p in panels:
            dist_str = f" (à {p['distance_km']} km)" if p.get("distance_km") is not None else ""
            freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
            ots_str = f"{p.get('ots_mensuel', 0):,}".replace(",", " ")
            direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
            dispo_humaine = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")

            direct_tag = "🎯 **Implantation directe** — " if p.get("is_direct_match") else ""
            
            lines.append(
                f"* {direct_tag}[**#{p['id']} - {p['ville']} - {p['localisation']}** ↗️]({p['lien']})\n"
                f"  * 📅 **Disponible dès :** **{dispo_humaine}**\n"
                f"  * 🚗 **Trafic & Impact :** {freq_str} véh./jour (~{ots_str} OTS/mois){dist_str}\n"
                f"  * 📍 **Direction :** {direction}\n"
                f"  * 👁️ **Contexte :** {p.get('contexte_visibilite')}\n"
            )

        is_creation_query = any(w in msg_lower for w in ["créat", "creat", "visuel", "affiche", "graphi", "design"])
        if is_creation_query:
            lines.append(
                "\n💡 **Conseil M Move pour votre création :**\n"
                "À 70 km/h, l'automobiliste dispose de 3 à 5 secondes pour lire votre affiche. "
                "Privilégiez la **règle des 7 mots**, des typographies XXL à fort contraste et un visuel unique percutant !"
            )
        return "\n".join(lines)
