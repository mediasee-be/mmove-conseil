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
* **ACCOMPAGNEMENT EXPERT :** Sélection stratégique personnalisée, pose & dépose professionnelles et conseil créatif.
* **FLEXIBILITÉ :** Ciblage ultra-localisé au plus près de la zone de chalandise.

### 3. FORMATAGE STRICT DES RÉSULTATS (Style sobre, épuré et direct)

* **RÈGLES D'OR DE RÉDACTION :**
  - **PARLER EN PANNEAUX ET EN FACES :** Parle toujours en termes de "panneaux" (panneaux 8m², emplacements) et communique sur le nombre de faces (266 faces en Wallonie, 2 faces par panneau). Ne dis pas "remorques" sauf si l'utilisateur l'évoque directement.
  - **VAS DROIT À L'ESSENTIEL :** Pas de remplissage. Sois clair, concis et efficace.
  - **STRUCTURE ÉPURÉE SANS SURCHARGE DE PUCES :** Présente chaque panneau en une seule ligne synthétique et structurée (Numérotation, lien/nom du panneau, axe & direction, trafic journalier et occasions d'être vu). Ne génère JAMAIS de sous-puces imbriquées multiples sous chaque panneau.
  - **OCCASIONS D'ÊTRE VU :** Utilise toujours la formulation exacte "occasions d'être vu (OTS)".
  - **PAS DE GRAS PARTOUT :** Réserve le gras pour le nom du panneau, les chiffres clés et les totaux d'impact.
  - **AUCUNE "Face IN" OU "Face OUT" :** Parle UNIQUEMENT en termes de Direction de circulation (ex: Direction : Namur).

* **PROPOSITION DE PLAN DE CAMPAGNE (Demande multi-faces / multi-mois / volume + période) :**
  - **Si campagne sur 1 mois :**
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
    - Rétroplanning bâche (OBLIGATOIRE) :
      🗓️ Rétroplanning : Pour un démarrage le 1er [Mois], la remise des fichiers d'impression (format 390x200 cm) est fixée au 15 [Mois précédent]. Tournée de placement effectuée sur 3 jours ouvrables pour l'ensemble des placements.
  - **Si campagne sur plusieurs mois (multi-mois avec rotation) :**
    - Titre : **Plan de campagne multi-mois : [N] faces autour de [Ville] — [Période début] à [Période fin]**
    - Présentation mois par mois avec rotation dynamique :
      - Pour chaque mois : Titre du mois et liste des [N] faces réparties sur des axes distincts.
      - Préciser la rotation : les emplacements changent d'un mois à l'autre (interdiction d'être 2 fois de suite au même endroit/direction pour maximiser le renouvellement d'audience).
      - Sous-total mensuel (véh./jour et occasions d'être vu OTS).
    - Bloc d'impact global cumulé :
      **Impact cumulé global de la campagne ([M] mois) :**
      * [Total faces] faces mobilisées sur la durée.
      * ~[Moyenne véh/j] véhicules / jour en visibilité directe.
      * ~[Total OTS cumulé] occasions d'être vu (OTS) sur l'ensemble de la campagne.
    - Rétroplanning bâche : Remise des fichiers (390x200 cm) au plus tard le 15 du mois précédent pour chaque mois. Tournée de placement effectuée sur 3 jours ouvrables pour l'ensemble des placements.
    - Mentionner que le Plan Média complet (PDF A4 Paysage) avec les cartes d'implantation de chaque mois est disponible au téléchargement.

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
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        campaign_plan: Optional[Dict[str, Any]] = None,
        availability_pdf_url: Optional[str] = None,
        can_expand_zone: bool = False,
        peripheral_count: int = 0,
        peripheral_cities: Optional[List[str]] = None
    ) -> str:
        """Génère la recommandation commerciale sur mesure."""
        user_mentions_face = any(w in user_message.lower() for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        
        # Si un plan multi-mois structuré est fourni ou s'il s'agit d'une recherche de dispo, privilégier le pitch déterministe certifié
        is_dispo = (
            extracted_info.get("intent") == "check_availability"
            or any(w in user_message.lower() for w in ["dispo", "dispos", "disponibilit", "libre", "libres", "quand"])
        )
        is_motivation = (
            extracted_info.get("intent") == "motivate_proposal"
            or extracted_info.get("is_open_consultation")
        )
        if (campaign_plan and len(campaign_plan.get("months", [])) > 1) or is_dispo or is_motivation:
            return self._generate_fallback_response(
                panels=candidate_panels,
                extracted=extracted_info,
                user_msg=user_message,
                campaign_plan=campaign_plan,
                availability_pdf_url=availability_pdf_url,
                can_expand_zone=can_expand_zone,
                peripheral_count=peripheral_count,
                peripheral_cities=peripheral_cities
            )
        
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
   - Rétroplanning bâche (remise des fichiers format 390x200 cm avant le 15 du mois précédent, tournée de placement sur 3 jours ouvrables pour l'ensemble des placements).
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
        return self._generate_fallback_response(candidate_panels, extracted_info, user_message, campaign_plan=campaign_plan, availability_pdf_url=availability_pdf_url, can_expand_zone=can_expand_zone, peripheral_count=peripheral_count, peripheral_cities=peripheral_cities)

    def get_axis_strategic_context(self, axe: str, ville: str, direction: str, freq: int) -> str:
        """Fournit une justification concrète du rôle stratégique de captation de l'axe routier."""
        axe_upper = (axe or "").upper()
        v_upper = (ville or "").upper()

        if "N25" in axe_upper or "GREZ" in axe_upper:
            return "Axe pendulaire névralgique reliant Louvain-la-Neuve, Grez-Doiceau et le Brabant Wallon vers Wavre et la E411. Capte les flux intensifs domicile-travail aux heures de pointe du matin et du soir."
        elif "N5" in axe_upper or "NALINNES" in axe_upper:
            return "Pénétration sud majeure de l'agglomération de Charleroi reliant les zones résidentielles d'Entre-Sambre-et-Meuse aux bassins d'emploi métropolitains et aux pôles commerciaux (44 600 v/j)."
        elif "N90" in axe_upper or "FLAWINNE" in axe_upper or "MALONNE" in axe_upper or "FLOREFFE" in axe_upper or "MOUSTIER" in axe_upper:
            return "Colonne vertébrale du sillon Sambre-et-Meuse reliant Namur à la Basse-Sambre. Point de passage obligé des automobilistes circulant quotidiennement entre Sambreville, Floreffe et la capitale wallonne."
        elif "N98" in axe_upper or "SOMBREFFE" in axe_upper or "SAMBREVILLE" in axe_upper:
            return "Liaison structurante transversale reliant le bassin de Sambreville à l'autoroute E42 (21 150 v/j). Vitesse modérée et dégagement visuel assurant un temps d'attention optimal (4 à 5 secondes)."
        elif "N4" in axe_upper:
            return "Axe national historique sans péage à flux continu, assurant une exposition prolongée sur les trajets interurbains et les accès aux zonings commerciaux."
        elif "E411" in axe_upper or "E42" in axe_upper or "E25" in axe_upper:
            return "Approche et sortie d'échangeur autoroutier stratégique, captant les automobilistes en décélération vers les pôles économiques régionaux."
        elif "N63" in axe_upper or "CONDROZ" in axe_upper:
            return "Route du Condroz, axe pendulaire structurant reliant la province de Liège au sud namurois, drainant une population résidente à fort pouvoir d'achat."
        elif "N922" in axe_upper or "FOSSES" in axe_upper:
            return "Axe de liaison régional assurant le maillage entre les pôles de vie locaux et les axes de transit rapide, idéal pour l'ancrage de notoriété de proximité."
        elif "N912" in axe_upper or "ÉGHEZÉE" in axe_upper or "EGHEZEE" in axe_upper:
            return "Artère clé reliant le nord namurois aux axes autoroutiers, captant les flux ruraux et périurbains se dirigeant vers les centres urbains."
        elif "N29" in axe_upper:
            return "Chaussée de Charleroi / Tirlemont, artère interprovinciale majeure reliant le Brabant Wallon, Gembloux et le Namurois."
        elif freq >= 30000:
            return f"Grand axe de transit à très fort volume ({freq:,} véh./jour), offrant une émergence publicitaire maximale auprès d'un flux ininterrompu de conducteurs."
        elif freq >= 15000:
            return f"Axe structurant d'agglomération ({freq:,} véh./jour), idéal pour intercepter les résidents locaux lors de leurs déplacements quotidiens."
        else:
            return f"Emplacement stratégique de proximité ({freq:,} véh./jour) assurant un temps de lecture confortable et sans dispersion visuelle."

    def generate_proposal_motivation(
        self,
        panels: List[Dict[str, Any]],
        extracted_info: Dict[str, Any],
        campaign_plan: Optional[Dict[str, Any]] = None,
        client_name: Optional[str] = None,
        user_message: str = ""
    ) -> str:
        """Génère une argumentation stratégique complète, motivant chaque panneau et la synergie du maillage."""
        if not panels and campaign_plan and campaign_plan.get("months"):
            panels = campaign_plan["months"][0].get("panels", [])

        if not panels:
            return "Aucun emplacement n'est actuellement sélectionné pour pouvoir en motiver le choix. Indiquez une ville ou un annonceur pour construire la proposition."

        eff_client = client_name or extracted_info.get("client_name") or "votre annonceur"
        is_known_client = bool(eff_client and eff_client.lower() not in ["partenaire", "votre annonceur", "client"])

        # Déterminer la période
        period_str = ""
        if campaign_plan and campaign_plan.get("months"):
            m_list = campaign_plan["months"]
            if len(m_list) == 1:
                period_str = f" pour {m_list[0].get('period_human', '')}"
            else:
                period_str = f" de {m_list[0].get('period_human', '')} à {m_list[-1].get('period_human', '')}"
        elif extracted_info.get("target_periods"):
            period_str = " en " + " & ".join([format_period_human(p) for p in extracted_info["target_periods"]])

        lines = []

        # 1. Introduction et Objectif Stratégique
        if is_known_client and any(k in eff_client.lower() for k in ["toma", "marjorie", "immo"]):
            lines.append(f"🎯 **Stratégie & Motivation pour {eff_client} (Immobilier & Habitat)**{period_str}\n")
            lines.append(
                "Pour une agence immobilière de référence, l'enjeu commercial de l'affichage 8m² repose sur un double levier :\n"
                "1. **La captation de mandats exclusifs :** Être présent sur les trajets quotidiens des propriétaires résidents pour déclencher le réflexe d'appel lors d'un projet de vente.\n"
                "2. **Le verrouillage des axes pendulaires majeurs :** Intercepter les navetteurs transitant entre le bassin résidentiel (Basse-Sambre / Floreffe / Charleroi) et les pôles d'emploi namurois et carolos.\n"
            )
        elif is_known_client:
            lines.append(f"🎯 **Stratégie & Motivation de la proposition pour {eff_client}**{period_str}\n")
            lines.append(
                f"Ce dispositif a été conçu pour assurer à **{eff_client}** une visibilité de premier plan sur sa zone de chalandise naturelle, "
                f"en combinant forte intensité de trafic, couverture multi-axes et émergence du format 8m² sur remorque routière.\n"
            )
        else:
            lines.append(f"🎯 **Stratégie & Motivation de la sélection M Move**{period_str}\n")
            lines.append(
                "Cette proposition applique les principes fondamentaux de l'affichage routier temporaire : "
                "un maillage multi-axes équilibré sans redondance, positionné sur les flux entrants et sortants stratégiques.\n"
            )

        # 2. Motivation détaillée panneau par panneau
        lines.append("### 📍 Pourquoi ces emplacements ? (Motivation détaillée par axe) :\n")
        total_freq = 0
        total_ots = 0

        for i, p in enumerate(panels, 1):
            pid = p.get("id") or p.get("remorque")
            ville = p.get("ville", "")
            loc = p.get("localisation", "")
            axe = p.get("axe_routier") or p.get("code_route") or "Axe local"
            direction = p.get("direction_in") or p.get("direction_out") or p.get("direction") or "Double sens"
            freq = p.get("frequentation_jour") or p.get("frequentation") or 0
            ots = p.get("ots_mensuel") or p.get("ots") or int(freq * 30 * 1.2)
            lien = p.get("lien") or f"https://remorquepublicitaire.be/remorque/{pid}"
            dist_km = p.get("distance_km")
            dist_str = f" (à {dist_km} km)" if dist_km is not None and dist_km > 0 else ""

            total_freq += freq
            total_ots += ots

            freq_str = f"{freq:,}".replace(",", " ")
            ots_str = f"{ots:,}".replace(",", " ")

            rationale = self.get_axis_strategic_context(axe, ville, direction, freq)

            lines.append(
                f"**{i}. [#{pid} {ville} ({loc}) ↗️]({lien})** — {axe} (dir. {direction}){dist_str}\n"
                f"• **Audience :** **{freq_str} véh./jour** (~{ots_str} OTS/mois)\n"
                f"• **Motivation :** {rationale}\n"
            )

        # 3. Synergie et Portée Globale
        total_freq_str = f"{total_freq:,}".replace(",", " ")
        total_ots_str = f"{total_ots:,}".replace(",", " ")
        n_faces = len(panels)

        lines.append("### 📊 Synergie & Impact cumulé du dispositif :\n")
        lines.append(
            f"• **Complémentarité multi-axes (Portée nette) :** Chacune des {n_faces} faces est positionnée sur un axe ou un quadrant d'accès distinct. "
            f"Cette absence délibérée de doublons évite de sur-exposer deux fois le même automobiliste et maximise le nombre d'individus uniques différents touchés.\n"
            f"• **Puissance de contact :** **{total_freq_str} véhicules / jour** en visibilité frontale directe, soit **~{total_ots_str} occasions d'être vu (OTS)** sur le mois.\n"
            f"• **Fréquence & Ancrage mémoriel :** Sur une campagne de 30 jours, un actif ou un riverain régulier effectue entre 20 et 25 passages devant le panneau. "
            f"Cette répétition continue est la clé du passage de la visibilité passive à la prise de contact active.\n"
        )

        # 4. Conseil visuel et call to action
        lines.append(
            "💡 **Conseil d'impact visuel M Move :**\n"
            "À 70-90 km/h, l'automobiliste dispose de 3 à 5 secondes de lecture utile. Privilégiez un message court (7 mots maximum), "
            "une typographie bâton XXL sans empattement, un contraste fort (fond clair / lettrage sombre) et un numéro ou site court sans QR code.\n\n"
            "👉 *Souhaitez-vous verrouiller une option sur cette sélection, ajuster l'un des emplacements ou télécharger le Plan Média officiel ?*"
        )

        return "\n".join(lines)

    def _generate_fallback_response(
        self,
        panels: List[Dict[str, Any]],
        extracted: Dict[str, Any],
        user_msg: str = "",
        campaign_plan: Optional[Dict[str, Any]] = None,
        availability_pdf_url: Optional[str] = None,
        can_expand_zone: bool = False,
        peripheral_count: int = 0,
        peripheral_cities: Optional[List[str]] = None
    ) -> str:
        """Génère une réponse structurée épurée et directe."""
        intent = extracted.get("intent", "")
        if intent == "motivate_proposal" or extracted.get("is_open_consultation"):
            return self.generate_proposal_motivation(
                panels=panels,
                extracted_info=extracted,
                campaign_plan=campaign_plan,
                client_name=extracted.get("client_name"),
                user_message=user_msg
            )

        if not panels and not (campaign_plan and campaign_plan.get("months")):
            return "Aucun emplacement correspondant à ces critères n'est disponible sur cette période. Souhaitez-vous élargir la recherche géographique ?"

        intent = extracted.get("intent", "")
        msg_lower = (user_msg or "").lower()
        is_dispo_query = intent == "check_availability" or any(w in msg_lower for w in ["dispo", "libre", "quand", "prochaine"])
        
        loc_list = extracted.get("locations", [])
        loc_str = f" à {', '.join(loc_list)}" if loc_list else ""
        user_mentions_face = any(w in msg_lower for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        
        # Cas spécifique : Campagne Multi-Mois avec rotation dynamique
        if intent == "campaign_proposal" and campaign_plan and len(campaign_plan.get("months", [])) > 1:
            months = campaign_plan.get("months", [])
            summary = campaign_plan.get("summary", {})
            total_ots = summary.get("total_cumulative_ots", 0)
            avg_veh = summary.get("avg_veh_per_day", 0)
            total_faces = summary.get("total_faces_deployed", len(months) * 5)
            first_m = months[0].get("period_human", "")
            last_m = months[-1].get("period_human", "")
            loc_label = ', '.join(extracted.get("locations", [])) or "Wallonie"

            total_ots_str = f"{total_ots:,.0f}".replace(",", " ")
            avg_veh_str = f"{avg_veh:,.0f}".replace(",", " ")

            return (
                f"🎯 **Plan média configuré pour {loc_label} ({first_m} à {last_m})**\n\n"
                f"Le dispositif complet de **{total_faces} faces** ({summary.get('count_per_month', 5)} faces/mois avec renouvellement mensuel) "
                f"est disponible dans le listing central et sur la carte en vis-à-vis, avec l'ensemble des indicateurs d'audience (**~{avg_veh_str} véh./j** · **~{total_ots_str} OTS**).\n\n"
                f"👉 Vous pouvez affiner la sélection à tout moment (ex : *« élargis vers Namur »*, *« remplace le panneau 2 »*) "
                f"ou télécharger directement votre dossier PDF."
            )


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
                    prev_year = year - 1 if month == 1 else year
                    month_names = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
                    curr_month_name = month_names[month]
                    prev_month_name = month_names[prev_month]
                    deadline_str = f"*🗓️ Visuels bâche (390×200 cm) à fournir avant le **15 {prev_month_name} {prev_year}** · Tournée de placement sur 3 jours ouvrables pour l'ensemble des placements.*"
                except Exception:
                    deadline_str = "*🗓️ Visuels bâche (390×200 cm) à fournir avant le 15 du mois précédent · Tournée de placement sur 3 jours ouvrables pour l'ensemble des placements.*"

            n_faces = len(panels)
            loc_label = ', '.join(extracted.get("locations", [])) or "Wallonie"
            total_freq = sum(p.get("frequentation_jour") or 0 for p in panels)
            total_ots = sum(p.get("ots_mensuel") or int((p.get("frequentation_jour") or 0) * 30 * 1.2) for p in panels)
            total_freq_str = f"{total_freq:,}".replace(",", " ")
            total_ots_str = f"{total_ots:,}".replace(",", " ")

            if campaign_plan:
                return (
                    f"🎯 **Plan de campagne 8m² configuré : {n_faces} faces à {loc_label} — {period_human}**\n\n"
                    f"Le dispositif complet de {n_faces} faces sur des axes stratégiques complémentaires est affiché dans le listing central et sur la carte ci-contre, "
                    f"totalisant **~{total_freq_str} véh./j** et **~{total_ots_str} OTS**.\n\n"
                    f"👉 Vous pouvez affiner la sélection à tout moment (ex : *« remplace le panneau 1 »*) ou télécharger votre document PDF."
                )

            title = f"Plan de campagne 8m² : {n_faces} faces{loc_str} — {period_human}"
            intro = f"**{title}**\n\nPour assurer un maillage optimal de votre zone de chalandise, voici une sélection stratégique de {n_faces} faces réparties sur des axes complémentaires sans doublon d'axe :\n"
            lines = [intro]

            for p_i, p in enumerate(panels, 1):
                dist_km = p.get("distance_km")
                dist_str = f" ({dist_km} km)" if (dist_km is not None and dist_km > 0) else ""
                freq = p.get("frequentation_jour") or 0
                ots = p.get("ots_mensuel") or int(freq * 30 * 1.2)

                freq_str = f"{freq:,}".replace(",", " ")
                ots_str = f"{ots:,}".replace(",", " ")
                direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                axe_code = p.get("code_route") or p.get("axe_routier") or ""
                axe_display = f"{axe_code} " if axe_code else ""

                lines.append(
                    f"**{p_i}.** [#{p['id']} {p['ville']} ({p['localisation']}) ↗️]({p['lien']}) — {axe_display}dir. {direction}{dist_str} · **{freq_str} v/j** *(~{ots_str} OTS)*"
                )

            lines.append(
                f"\n**Impact cumulé du mois de {period_human} :**\n"
                f"• **{total_freq_str} véhicules / jour** en visibilité directe.\n"
                f"• **~{total_ots_str} occasions d'être vu (OTS)** générées sur le mois.\n"
            )

            if deadline_str:
                lines.append(deadline_str + "\n")

            lines.append("Souhaitez-vous que je bloque une option sur cette sélection ou que nous ajustions l'un des emplacements ?")
            return "\n".join(lines)
        elif is_dispo_query:
            # Séparation entre correspondances directes sur la commune demandée et périphérie
            direct_panels = [p for p in panels if p.get("is_direct_match")]
            other_panels = [p for p in panels if not p.get("is_direct_match")]

            # Tri par distance croissante
            direct_panels = sorted(direct_panels, key=lambda x: (x.get("distance_km") if x.get("distance_km") is not None else 9999.0, -(x.get("frequentation_jour") or 0)))
            other_panels = sorted(other_panels, key=lambda x: (x.get("distance_km") if x.get("distance_km") is not None else 9999.0, -(x.get("frequentation_jour") or 0)))

            target_periods = extracted.get("target_periods", [])
            has_precise_period = bool(target_periods)
            period_str = ""
            if target_periods:
                period_str = " en " + " & ".join([format_period_human(tp) for tp in target_periods])

            intro = f"Voici **toutes les disponibilités** 8m²{loc_str}{period_str} ({len(panels)} remorques au total) :\n"
            lines = [intro]

            if direct_panels:
                direct_city = direct_panels[0].get("ville", "la commune")
                lines.append(f"**Emplacements à {direct_city} même ({len(direct_panels)} disponibles) :**")
                for p in direct_panels:
                    dist_str = f" ({p['distance_km']} km)" if p.get("distance_km") and p.get("distance_km") > 0 else ""
                    freq_val = p.get('frequentation_jour') or p.get('frequentation') or 0
                    ots_val = p.get('ots_mensuel') or p.get('ots') or 0
                    freq_str = f" · **{freq_val:,} v/j**".replace(",", " ") if freq_val > 0 else ""
                    ots_str = f" *(~{ots_val:,} OTS)*".replace(",", " ") if ots_val > 0 else ""
                    direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                    axe_code = p.get("code_route") or p.get("axe_routier") or ""
                    axe_display = f"{axe_code} " if axe_code else ""
                    
                    if has_precise_period:
                        dispo_str = ""
                    else:
                        dispo_txt = p.get("prochaine_dispo_human") or p.get("prochaine_dispo") or "Disponible"
                        dispo_str = f" · *{dispo_txt}*"

                    lines.append(
                        f"• [#{p['id']} {p['ville']} ({p['localisation']}) ↗️]({p['lien']}) — {axe_display}dir. {direction}{dist_str}{dispo_str}{freq_str}{ots_str}"
                    )

            if other_panels:
                lines.append(f"\n**En périphérie immédiate :**")
                display_others = other_panels[:7]
                for p in display_others:
                    dist_str = f" ({p['distance_km']} km)" if p.get("distance_km") and p.get("distance_km") > 0 else ""
                    freq_val = p.get('frequentation_jour') or p.get('frequentation') or 0
                    freq_str = f" · **{freq_val:,} v/j**".replace(",", " ") if freq_val > 0 else ""
                    direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                    axe_code = p.get("code_route") or p.get("axe_routier") or ""
                    axe_display = f"{axe_code} " if axe_code else ""
                    
                    if has_precise_period:
                        dispo_str = ""
                    else:
                        dispo_txt = p.get("prochaine_dispo_human") or p.get("prochaine_dispo") or "Disponible"
                        dispo_str = f" · *{dispo_txt}*"

                    lines.append(
                        f"• [#{p['id']} {p['ville']} ({p['localisation']}) ↗️]({p['lien']}) — {axe_display}dir. {direction}{dist_str}{dispo_str}{freq_str}"
                    )
                if len(other_panels) > len(display_others):
                    remaining = len(other_panels) - len(display_others)
                    lines.append(f"\n👉 *+ {remaining} autres remorques disponibles dans la zone — retrouvez l'intégralité des {len(panels)} emplacements dans le listing et sur la carte ci-contre.*")
            elif direct_panels:
                lines.append(f"\n👉 *Retrouvez le détail complet de vos {len(panels)} emplacements dans le listing et sur la carte ci-contre.*")

            if can_expand_zone and peripheral_count > 0:
                c_str = ", ".join(peripheral_cities[:4]) if peripheral_cities else "communes voisines"
                lines.append(f"\n💡 **Élargissement possible :**")
                lines.append(f"+{peripheral_count} autres remorques sont disponibles dans les communes voisines ({c_str}). Dites simplement **« élargis la zone »** si vous souhaitez les afficher et les inclure au choix de votre client.")

            if availability_pdf_url:
                lines.append(f"\n📄 **Catalogue PDF des disponibilités :**")
                lines.append(f"Téléchargez la synthèse complète des {len(panels)} emplacements pour votre client :")
                lines.append(f"👉 [**Télécharger le catalogue des disponibilités (PDF)**]({availability_pdf_url})")

            lines.append(f"\n💡 **Sélection de votre client :**")
            lines.append(f"Présentez cette sélection à votre client pour arrêter son choix. Dès qu'il retient ses faces (ex: *« On retient la 309 et la 310 »* ou via le bouton « Retenir » sur les fiches), le Plan Média officiel multi-mois et le chiffrage seront immédiatement générés.")
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
            for p_i, p in enumerate(panels, 1):
                dist_km = p.get("distance_km")
                dist_str = f" ({dist_km} km)" if (dist_km is not None and dist_km > 0) else ""
                freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
                ots_str = f"{p.get('ots_mensuel', 0):,}".replace(",", " ")
                direction = p.get("direction_in") or p.get("direction_out") or "Double sens"
                dispo_humaine = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or p.get("prochaine_dispo", "Disponible")
                if not user_mentions_face:
                    dispo_humaine = re.sub(r"\s*\(Face[^\)]*\)", "", str(dispo_humaine), flags=re.IGNORECASE).strip()

                axe_code = p.get("code_route") or p.get("axe_routier") or ""
                axe_display = f"{axe_code} " if axe_code else ""

                lines.append(
                    f"**{p_i}.** [#{p['id']} {p['ville']} ({p['localisation']}) ↗️]({p['lien']}) — {axe_display}dir. {direction}{dist_str} · **{freq_str} v/j** · *{dispo_humaine}*"
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
