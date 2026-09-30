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
from core.agents.engine_tools import format_period_human

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

SALES_SYSTEM_PROMPT = """### 1. RÔLE ET IDENTITÉ
Tu es l'**Agent Commercial Expert** de la société **M Move** (remorquepublicitaire.be).
* **Ta mission :** Vendre des campagnes d'affichage 8m² et conseiller les prospects sur leur stratégie et leur créativité.
* **Ton Ton :** Professionnel, dynamique, expert, chaleureux et percutant.

### 2. ARGUMENTS COMMERCIAUX CLÉS M MOVE
* **PUISSANCE :** Réseau de 133 panneaux publicitaires stratégiques en Wallonie (266 faces 8m²).
* **VISIBILITÉ & IMPACT :** Format 8m² géant immanquable, non noyé dans la masse publicitaire, visible 24h/24.
* **SERVICE "TOUT COMPRIS" :** Prix incluant la location de l'emplacement, l'impression grand format des bâches, le placement/pose et **toutes les taxes régionales et communales incluses**.
* **FLEXIBILITÉ :** Ciblage ultra-localisé au plus près de la zone de chalandise.

### 3. FORMATAGE STRICT DES RÉSULTATS (Style sobre, épuré et direct)

* **RÈGLES D'OR DE RÉDACTION :**
  - **PARLER EN PANNEAUX ET EN FACES :** Parle toujours en termes de "panneaux" (panneaux 8m², emplacements) et communique sur le nombre de faces (266 faces en Wallonie, 2 faces par panneau). Ne dis pas "remorques" sauf si l'utilisateur l'évoque directement.
  - **VAS DROIT À L'ESSENTIEL :** Pas de remplissage. Sois clair, concis et efficace.
  - **PAS DE GRAS PARTOUT :** Soulage la lecture. N'utilise JAMAIS de gras sur les étiquettes ("Disponible dès", "Disponibilité", "Direction", "Trafic", "Contexte", "Rôle") ni sur chaque valeur. Réserve le gras uniquement pour le nom du panneau s'il n'est pas déjà dans un lien, ou pour le titre de campagne et le total d'impact.
  - **SUPPRIME "Implantation directe" :** Ne mentionne JAMAIS "Implantation directe".
  - **AUCUNE "Face IN" OU "Face OUT" :** Parle UNIQUEMENT en termes de Direction de circulation (ex: Direction : Namur).
  - **RÉPONSE EN BULLET POINTS :** Présente chaque panneau de manière structurée et aérée.

* **PROPOSITION DE PLAN DE CAMPAGNE (Demande multi-faces / volume + période, ex: "campagne de 5 faces à Gembloux en janvier") :**
  - Titre clair : **Plan de campagne 8m² : [N] faces autour de [Ville] — [Période]**
  - Introduction sobre valorisant le maillage territorial multi-axes (chacun des [N] panneaux est positionné sur un axe routier distinct sans aucun doublon pour capter tous les flux d'accès).
  - Liste à puces structurée des [N] panneaux :
    • [#ID - Ville - Localisation ↗️](lien) — Direction [Direction] (à [X] km)
      - Disponibilité : ✅ Libre en [Mois Année] (confirme explicitement la disponibilité sur la période demandée)
      - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
      - Rôle : [Axe routier et atout de captage du flux]
  - Bloc d'impact cumulé de la campagne :
    **Impact cumulé de la campagne :**
    * [Total véh/j] véhicules / jour en visibilité directe.
    * ~[Total OTS] occasions d'être vu (OTS) sur le mois de [Période].
  - Rétroplanning bâche (OBLIGATOIRE pour une campagne) :
    🗓️ Rétroplanning : Pour un démarrage le 1er [Mois], la remise des fichiers d'impression (format 390x200 cm) est fixée au 15 [Mois précédent].
  - Appel à l'action commercial sobre (optionner la sélection / ajustement).

* **DEMANDE DE LOCALISATION ("remorques à...", "panneaux à...", recherche par ville) :**
  - Trie TOUJOURS les emplacements par DISTANCE CROISSANTE (le plus proche en premier : 0 km, 0.14 km, 1.28 km, etc.).
  - Indique la distance entre parenthèses après la direction si supérieure à 0 (ex: "à 0.14 km", "à 1.28 km").
  - Structure directe en bullet points sans gras sur les étiquettes :
    • [#ID - Ville - Localisation ↗️](lien) — Direction [Direction] (à [X] km)
      - Disponible dès : Mois Année
      - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
      - Contexte : [Contexte de visibilité court]

* **DEMANDE DE DISPONIBILITÉ / PROCHAINE DISPO (RÈGLE OBLIGATOIRE) :**
  - Trie TOUJOURS les emplacements par ordre chronologique strict (la date de disponibilité la plus proche en premier : ex: Décembre 2026 avant Février 2027).
  - Regroupe par période (Mois Année) sous ce format sobre et aéré :
  
    [Mois Année] :
    • [#ID - Ville - Localisation ↗️](lien) — Direction [Direction]
      - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
      - Contexte : [Contexte court]

    Exemple :
    Décembre 2026 :
    • [#343 - Namur - Wierde ↗️](https://remorquepublicitaire.be/remorque/343) — Direction E411
      - Trafic : 34 500 véh./jour (~1 397 250 OTS/mois)
      - Contexte : Pôle commercial de Naninne (sortie E411)

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

        intent = extracted_info.get("intent", "")
        msg_lower = (user_message or "").lower()
        is_dispo_query = intent == "check_availability" or any(w in msg_lower for w in ["dispo", "libre", "quand", "prochaine", "prochaines", "date"])
        if is_dispo_query:
            candidate_panels = sorted(candidate_panels, key=lambda x: x.get("prochaine_dispo") or "9999-99")

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
2. PAS de gras partout : ne mets JAMAIS les étiquettes en gras (écris "Direction :", "Trafic :", "Contexte :" sans astérisques de gras).
3. AUCUNE mention "Implantation directe".
4. AUCUNE mention "Face IN" ou "Face OUT" : uniquement la Direction (ex: Direction : Namur).
5. Pour les demandes de disponibilité ("prochaine dispo", "quand", "dispo") :
   - Trie OBLIGATOIREMENT les réponses par ordre chronologique (la période la plus proche en premier).
   - Regroupe ou présente par période en tête (ex: "Décembre 2026 :"), avec sous chaque période les emplacements correspondants :
     • [#ID - Ville - Localisation ↗️](lien) — Direction [Direction]
       - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
       - Contexte : [contexte court]
6. Pour toute demande de localisation ("remorques à...", "panneaux à...", recherche par ville) :
   - Trie OBLIGATOIREMENT les réponses par DISTANCE CROISSANTE (le plus proche en km en premier : 0 km, 0.14 km, 1.28 km...).
   - Indique clairement la distance (ex: à 0.14 km, à 1.28 km) après la direction.
7. Si l'intention est une proposition de campagne ("campaign_proposal") :
   - Titre clair : **Plan de campagne 8m² : {len(candidate_panels)} faces autour de {extracted_info.get('locations', ['Wallonie'])[0] if extracted_info.get('locations') else 'Wallonie'} — {format_period_human(extracted_info.get('target_periods', [None])[0]) if extracted_info.get('target_periods') else 'À convenir'}**
   - Introduction sobre valorisant le maillage territorial multi-axes sans aucun doublon d'axe.
   - Pour chaque panneau :
     • [#ID - Ville - Localisation ↗️](lien) — Direction [Direction] (à [X] km)
       - Disponibilité : ✅ Libre en {format_period_human(extracted_info.get('target_periods', [None])[0]) if extracted_info.get('target_periods') else 'période souhaitée'}
       - Trafic : [frequentation] véh./jour (~[ots] OTS/mois)
       - Rôle : [Axe et couverture du flux]
   - Bloc d'impact cumulé chiffré (total véhicules/jour et total OTS mensuels).
   - Rétroplanning bâche (remise des fichiers format 390x200 cm avant le 15 du mois précédent).
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
        user_mentions_face = any(w in msg_lower for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        
        if intent == "campaign_proposal":
            target_period_str = extracted.get("target_periods", [None])[0] if extracted.get("target_periods") else None
            period_human = format_period_human(target_period_str) if target_period_str else "Prochainement"
            
            # Calcul du rétroplanning au 15 du mois précédent
            deadline_str = ""
            if target_period_str:
                try:
                    parts = target_period_str.split("-")
                    year = int(parts[0])
                    month = int(parts[1])
                    prev_month = 12 if month == 1 else month - 1
                    month_names = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
                    curr_month_name = month_names[month]
                    prev_month_name = month_names[prev_month]
                    deadline_str = f"🗓️ Rétroplanning : Pour un démarrage le 1er {curr_month_name}, la remise des fichiers d'impression (format 390x200 cm) est fixée au 15 {prev_month_name}."
                except Exception:
                    deadline_str = "🗓️ Rétroplanning : Remise des fichiers d'impression (format 390x200 cm) avant le 15 du mois précédent."

            n_faces = len(panels)
            title = f"Plan de campagne 8m² : {n_faces} faces{loc_str} — {period_human}"
            intro = f"**{title}**\n\nPour assurer un maillage optimal de votre zone de chalandise, voici une sélection stratégique de {n_faces} faces réparties sur des axes complémentaires sans aucun doublon d'axe :\n"
            lines = [intro]

            total_freq = 0
            total_ots = 0

            for p in panels:
                dist_km = p.get("distance_km")
                dist_str = f" (à {dist_km} km)" if (dist_km is not None and dist_km > 0) else ""
                freq = p.get("frequentation_jour") or 0
                ots = p.get("ots_mensuel") or int(freq * 30 * 1.2)
                total_freq += freq
                total_ots += ots

                freq_str = f"{freq:,}".replace(",", " ")
                ots_str = f"{ots:,}".replace(",", " ")
                direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                dispo_label = f"✅ Libre en {period_human}" if target_period_str else (p.get("prochaine_dispo_human") or "Disponible")

                contexte = p.get('contexte_visibilite') or ''
                contexte_clean = re.sub(r"^\[Zoning\]\s*", "", contexte)
                axe_code = p.get("code_route") or p.get("axe_routier") or ""

                role_str = f"Axe {axe_code} — {contexte_clean}" if axe_code else contexte_clean

                lines.append(
                    f"• [#{p['id']} - {p['ville']} - {p['localisation']} ↗️]({p['lien']}) — Direction {direction}{dist_str}\n"
                    f"  - Disponibilité : {dispo_label}\n"
                    f"  - Trafic : {freq_str} véh./jour (~{ots_str} OTS/mois)\n"
                    f"  - Rôle : {role_str}\n"
                )

            total_freq_str = f"{total_freq:,}".replace(",", " ")
            total_ots_str = f"{total_ots:,}".replace(",", " ")
            lines.append(
                f"**Impact cumulé de la campagne :**\n"
                f"* {total_freq_str} véhicules / jour en visibilité directe.\n"
                f"* ~{total_ots_str} occasions d'être vu (OTS) sur le mois de {period_human}.\n"
            )

            if deadline_str:
                lines.append(deadline_str + "\n")

            lines.append("Souhaitez-vous que je bloque une option sur cette sélection ou que nous ajustions l'un des emplacements ?")
            return "\n".join(lines)
        elif is_dispo_query:
            # Priorité aux correspondances directes sur la localité, puis tri par date chronologique (plus proche en premier)
            has_direct = any(p.get("is_direct_match") for p in panels)
            if has_direct:
                panels_sorted = sorted(panels, key=lambda x: (not x.get("is_direct_match", False), x.get("prochaine_dispo") or "9999-99"))
            else:
                panels_sorted = sorted(panels, key=lambda x: x.get("prochaine_dispo") or "9999-99")
            intro = f"Voici les disponibilités pour vos panneaux 8m²{loc_str} :\n"
            lines = [intro]

            current_period = None
            for p in panels_sorted:
                p_period = p.get("prochaine_dispo_human") or format_period_human(p.get("prochaine_dispo")) or "Sur demande"
                if not user_mentions_face:
                    p_period = re.sub(r"\s*\(Face[^\)]*\)", "", str(p_period), flags=re.IGNORECASE).strip()

                if p_period != current_period:
                    current_period = p_period
                    lines.append(f"\n{current_period} :")

                dist_str = f" (à {p['distance_km']} km)" if p.get("distance_km") and p.get("distance_km") > 0 else ""
                freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
                ots_str = f"{p.get('ots_mensuel', 0):,}".replace(",", " ")
                direction = p.get("direction_in") or p.get("direction_out") or "Double sens"

                contexte = p.get('contexte_visibilite') or ''
                contexte_clean = re.sub(r"^\[Zoning\]\s*", "", contexte)

                lines.append(
                    f"• [#{p['id']} - {p['ville']} - {p['localisation']} ↗️]({p['lien']}) — Direction {direction}{dist_str}\n"
                    f"  - Trafic : {freq_str} véh./jour (~{ots_str} OTS/mois)\n"
                    f"  - Contexte : {contexte_clean}"
                )
        else:
            loc_list = extracted.get("locations", [])
            if loc_list:
                # Tri strict par distance croissante (le plus proche en premier)
                panels = sorted(
                    panels,
                    key=lambda x: (
                        x.get("distance_km") if x.get("distance_km") is not None else 9999.0,
                        not x.get("is_direct_match", False),
                        -x.get("frequentation_jour", 0)
                    )
                )

            intro = f"Voici la sélection d'emplacements 8m²{loc_str} :\n"
            lines = [intro]
            for p in panels:
                dist_km = p.get("distance_km")
                dist_str = f" (à {dist_km} km)" if (dist_km is not None and dist_km > 0) else ""
                freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
                ots_str = f"{p.get('ots_mensuel', 0):,}".replace(",", " ")
                direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                dispo_humaine = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")
                if not user_mentions_face:
                    dispo_humaine = re.sub(r"\s*\(Face[^\)]*\)", "", str(dispo_humaine), flags=re.IGNORECASE).strip()

                contexte = p.get('contexte_visibilite') or ''
                contexte_clean = re.sub(r"^\[Zoning\]\s*", "", contexte)

                lines.append(
                    f"• [#{p['id']} - {p['ville']} - {p['localisation']} ↗️]({p['lien']}) — Direction {direction}{dist_str}\n"
                    f"  - Disponible dès : {dispo_humaine}\n"
                    f"  - Trafic : {freq_str} véh./jour (~{ots_str} OTS/mois)\n"
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
