"""
Mmove Coordinator Agent (Orchestrateur Central)
Pilote le pipeline complet :
1. Extraction NLU (ExtractorAgent)
2. Traitement Déterministe Spatial & Dispo (MmoveEngineTools)
3. Synthèse Commerciale Haute Performance (SalesAgent)
Mesure les temps d'exécution et renvoie les données enrichies pour le frontend.
"""

import time
import re
from typing import Dict, Any, List, Optional
from .engine_tools import MmoveEngineTools, format_period_human, get_friendly_dispo_label
from .extractor_agent import ExtractorAgent
from .sales_agent import SalesAgent
from .sync_service import SyncManager

class CoordinatorAgent:
    """Orchestrateur multi-agents pour le conseil et la recherche de remorques Mmove."""

    def __init__(self, api_key: Optional[str] = None, auto_sync: bool = True):
        self.engine = MmoveEngineTools()
        self.extractor = ExtractorAgent(api_key=api_key)
        self.sales = SalesAgent(api_key=api_key)
        self.sync = SyncManager(engine_tools=self.engine)
        if auto_sync:
            self.sync.start_scheduler()

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Traite un message utilisateur de bout en bout.
        Retourne :
        {
          "text": str,
          "panels": List[Dict],
          "extracted": Dict,
          "timing": Dict
        }
        """
        start_total = time.time()
        timing = {}

        # 1. Extraction NLU
        t0 = time.time()
        extracted = self.extractor.extract(user_message)
        timing["extraction_ms"] = round((time.time() - t0) * 1000, 1)

        intent = extracted.get("intent", "search_panels")
        target_id = extracted.get("target_id")
        candidate_panels: List[Dict[str, Any]] = []

        # Spécification 1 & 2 : Détection et enrichissement automatique des localités secondaires et hameaux
        from core.agents.engine_tools import normalize_text
        detected_locations = list(extracted.get("locations") or [])
        user_norm = normalize_text(user_message)
        for t in self.engine.trailers.values():
            loc_norm = normalize_text(t.get("localisation"))
            if loc_norm and len(loc_norm) >= 3 and loc_norm in user_norm:
                if not any(loc_norm in normalize_text(d) for d in detected_locations):
                    detected_locations.append(t.get("localisation"))
        if detected_locations:
            extracted["locations"] = detected_locations

        # 2. Moteur Déterministe Instantané
        t0 = time.time()
        if intent == "check_availability" and target_id:
            # Recherche directe par ID
            trailer = self.engine.get_trailer_by_id(target_id)
            if trailer:
                # Vérifier dispo sur la période demandée ou prochaine dispo
                target_periods = extracted.get("target_periods", [])
                avail_info = self.engine.check_period_availability(trailer, target_periods)
                photo = trailer.get("photo_in") or "https://remorquepublicitaire.be/wp-content/uploads/2021/07/logo-mmove.png"
                candidate_panels.append({
                    "id": trailer["id"],
                    "ville": trailer["ville"],
                    "localisation": trailer["localisation"],
                    "province": trailer["province"],
                    "axe_routier": trailer["axe_routier"],
                    "code_route": trailer.get("code_route"),
                    "direction_in": trailer["direction_in"],
                    "direction_out": trailer["direction_out"],
                    "frequentation_jour": trailer["frequentation_jour"],
                    "ots_mensuel": trailer["ots_mensuel"],
                    "score_impact": trailer.get("score_impact", "Élevé"),
                    "contexte_visibilite": trailer.get("contexte_visibilite"),
                    "lien": trailer["lien"],
                    "distance_km": None,
                    "prochaine_dispo": trailer.get("prochaine_dispo"),
                    "prochaine_dispo_in": trailer.get("prochaine_dispo_in"),
                    "prochaine_dispo_out": trailer.get("prochaine_dispo_out"),
                    "prochaine_dispo_human": format_period_human(trailer.get("prochaine_dispo")),
                    "prochaine_dispo_label": get_friendly_dispo_label(trailer),
                    "availability": avail_info,
                    "photo_url": photo,
                    "total_score": 100.0
                })

        elif intent == "identify_panel":
            # Identification du panneau le plus proche
            candidate_panels = self.engine.search_and_rank(
                locations=extracted.get("locations"),
                axes=extracted.get("axes"),
                province=extracted.get("province"),
                direction=extracted.get("direction"),
                top_k=1,
                require_availability=False
            )

        elif intent == "campaign_proposal":
            # Recommandation de plan de campagne (multi-faces, diversité stricte d'axes, période ciblée)
            target_periods = extracted.get("target_periods", [])
            req_dispo = len(target_periods) > 0
            candidate_panels = self.engine.search_and_rank(
                locations=extracted.get("locations"),
                axes=extracted.get("axes"),
                target_periods=target_periods,
                province=extracted.get("province"),
                direction=extracted.get("direction"),
                contexte_query=extracted.get("contexte_pref") or extracted.get("sector"),
                top_k=extracted.get("count_requested", 5),
                require_availability=req_dispo,
                enforce_axis_diversity=True
            )

        else:
            # Recherche géographique & critères (search_panels ou check_availability par zone)
            target_periods = extracted.get("target_periods", [])
            req_dispo = len(target_periods) > 0
            is_dispo_query = (
                intent == "check_availability"
                or any(w in user_message.lower() for w in ["dispo", "dispos", "disponibilit", "libre", "libres", "quand", "prochain", "prochaine", "prochaines", "date", "dates"])
            )
            candidate_panels = self.engine.search_and_rank(
                locations=extracted.get("locations"),
                axes=extracted.get("axes"),
                target_periods=target_periods,
                province=extracted.get("province"),
                direction=extracted.get("direction"),
                contexte_query=extracted.get("contexte_pref") or extracted.get("sector"),
                top_k=extracted.get("count_requested", 3),
                require_availability=req_dispo,
                sort_by_dispo=is_dispo_query
            )

        timing["engine_ms"] = round((time.time() - t0) * 1000, 1)

        # 3. Vérification si une localisation ou entreprise demandée est introuvable sur la carte
        locations = extracted.get("locations", [])
        if locations and not any(p.get("distance_km") is not None or p.get("is_direct_match") for p in candidate_panels):
            loc_name = locations[0]
            timing["synthesis_ms"] = 1.0
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
            final_text = (
                f"Je n'ai pas pu localiser précisément l'entreprise ou l'adresse « {loc_name} » sur la carte.\n\n"
                f"Pourriez-vous me préciser sa commune, son code postal ou un axe routier proche (ex: Gembloux, Namur, Wavre, N4...) ? "
                f"Je pourrai ainsi vous indiquer immédiatement les panneaux les plus proches et leurs disponibilités."
            )
            return {
                "text": final_text,
                "panels": [],
                "timing_ms": timing,
                "context": {"extracted": extracted}
            }

        # Synthèse Commerciale Experte
        t0 = time.time()
        final_text = self.sales.generate_pitch(
            user_message=user_message,
            extracted_info=extracted,
            candidate_panels=candidate_panels,
            conversation_history=conversation_history
        )
        timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
        timing["total_ms"] = round((time.time() - start_total) * 1000, 1)

        # 4. Normalisation des panneaux pour le frontend (cartes interactives)
        user_mentions_face = any(w in user_message.lower() for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        frontend_panels = []
        for p in candidate_panels:
            dir_str = p.get("direction_in") or p.get("direction_out") or "Double sens"
            avail_months = p.get("availability", {}).get("available_months", [])
            friendly_dispo = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or format_period_human(p.get("prochaine_dispo"))
            if not user_mentions_face and friendly_dispo:
                friendly_dispo = re.sub(r"\s*\(Face[^\)]*\)", "", str(friendly_dispo), flags=re.IGNORECASE).strip()

            if p.get("target_period_human") and p.get("is_available_in_target_period"):
                dispo_label = f"Libre en {p['target_period_human']}"
                friendly_dispo = f"Libre en {p['target_period_human']}"
            else:
                dispo_label = ", ".join([m["period_human"] for m in avail_months]) if avail_months else friendly_dispo
            
            frontend_panels.append({
                "remorque": p["id"],
                "id": p["id"],
                "ville": p["ville"],
                "localisation": p["localisation"],
                "axe_routier": p.get("axe_routier", ""),
                "direction": dir_str,
                "face": p.get("face") if user_mentions_face else None,
                "distance_km": p.get("distance_km"),
                "frequentation": p.get("frequentation_jour"),
                "ots": p.get("ots_mensuel"),
                "contexte_visibilite": p.get("contexte_visibilite"),
                "lien": p["lien"],
                "photo": p.get("photo_url"),
                "image_url": p.get("photo_url"),
                "is_direct_match": p.get("is_direct_match", False),
                "prochaine_dispo": dispo_label,
                "prochaine_dispo_human": friendly_dispo,
                "active": "O",
                "score": p.get("total_score")
            })

        return {
            "text": final_text,
            "panels": frontend_panels,
            "extracted": extracted,
            "timing": timing
        }
