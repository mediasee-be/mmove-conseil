"""
Mmove Coordinator Agent (Orchestrateur Central)
Pilote le pipeline complet :
1. Extraction NLU (ExtractorAgent)
2. Traitement Déterministe Spatial & Dispo (MmoveEngineTools)
3. Synthèse Commerciale Haute Performance (SalesAgent)
Mesure les temps d'exécution et renvoie les données enrichies pour le frontend.
"""

import os
import time
import re
from typing import Dict, Any, List, Optional
from .engine_tools import MmoveEngineTools, format_period_human, get_friendly_dispo_label
from .extractor_agent import ExtractorAgent
from .sales_agent import SalesAgent
from .sync_service import SyncManager
from .map_service import MapGeneratorService
from .pdf_service import CampaignPdfService

class ActiveCampaignContext:
    """Conserve l'état cumulatif d'une campagne en cours de discussion pour un commercial."""
    def __init__(self):
        self.client_name: Optional[str] = None
        self.locations: List[str] = []
        self.axes: List[str] = []
        self.target_periods: List[str] = []
        self.count_requested: int = 5
        self.pinned_panel_ids: List[str] = []
        self.excluded_panel_ids: List[str] = []
        self.candidate_panels: List[Dict[str, Any]] = []
        self.last_campaign_plan: Optional[Dict[str, Any]] = None
        self.search_radius_km: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_name": self.client_name,
            "locations": list(self.locations),
            "axes": list(self.axes),
            "target_periods": list(self.target_periods),
            "count_requested": self.count_requested,
            "pinned_panel_ids": list(self.pinned_panel_ids),
            "excluded_panel_ids": list(self.excluded_panel_ids),
            "has_plan": self.last_campaign_plan is not None,
            "search_radius_km": self.search_radius_km
        }

    def reset(self):
        self.client_name = None
        self.locations = []
        self.axes = []
        self.target_periods = []
        self.count_requested = 5
        self.pinned_panel_ids = []
        self.excluded_panel_ids = []
        self.candidate_panels = []
        self.last_campaign_plan = None
        self.search_radius_km = 5.0

class CoordinatorAgent:
    """Orchestrateur multi-agents pour le conseil et la recherche de remorques Mmove."""

    def __init__(self, api_key: Optional[str] = None, auto_sync: bool = True):
        self.engine = MmoveEngineTools()
        self.extractor = ExtractorAgent(api_key=api_key)
        self.sales = SalesAgent(api_key=api_key)
        self.sync = SyncManager(engine_tools=self.engine)
        self.map_service = MapGeneratorService()
        from core.agents.salesperson_service import SalespersonService
        from core.agents.dossier_service import DossierService
        from core.agents.inventory_agent import InventoryAgent
        from core.agents.campaign_agent import CampaignAgent
        from core.agents.client_agent import ClientAgent

        self.salesperson_service = SalespersonService()
        self.dossier_service = DossierService(salesperson_service=self.salesperson_service)
        self.pdf_service = CampaignPdfService()
        self.inventory_agent = InventoryAgent(engine=self.engine, pdf_service=self.pdf_service, sales_agent=self.sales)
        self.campaign_agent = CampaignAgent(engine=self.engine, pdf_service=self.pdf_service, map_service=self.map_service, sales_agent=self.sales)
        self.client_agent = ClientAgent(engine=self.engine)

        self.current_client_name: Optional[str] = None
        self.last_campaign_plan: Optional[Dict[str, Any]] = None
        self.pending_dossiers: Dict[str, Dict[str, Any]] = {}
        self.contexts: Dict[str, ActiveCampaignContext] = {}
        if auto_sync:
            self.sync.start_scheduler()

    def _get_context(self, sp_id: Optional[str]) -> ActiveCampaignContext:
        key = sp_id or "default"
        if key not in self.contexts:
            self.contexts[key] = ActiveCampaignContext()
        return self.contexts[key]

    def _reconstruct_context_from_history(self, history: List[Dict[str, Any]], ctx: ActiveCampaignContext):
        """Reconstitue le contexte de campagne actif depuis l'historique conversationnel."""
        if not history:
            return
        for turn in history:
            role = turn.get("role", "")
            text = turn.get("text") or (turn.get("parts")[0].get("text") if turn.get("parts") else "")
            if role == "user" and text:
                parsed = self.extractor.extract(text)
                if parsed.get("client_name"):
                    ctx.client_name = parsed["client_name"]
                    self.current_client_name = parsed["client_name"]
                if parsed.get("intent") == "campaign_proposal" and parsed.get("target_periods"):
                    if parsed.get("locations"):
                        ctx.locations = list(parsed["locations"])
                    ctx.target_periods = list(parsed["target_periods"])
                    if parsed.get("count_requested"):
                        ctx.count_requested = parsed["count_requested"]
                elif parsed.get("intent") == "refine_campaign":
                    act = parsed.get("refinement_action")
                    if act == "expand_zone":
                        for l in parsed.get("locations", []):
                            if l not in ctx.locations:
                                ctx.locations.append(l)
                    elif act == "pin_panel":
                        for p in parsed.get("pinned_panel_ids", []):
                            if p not in ctx.pinned_panel_ids:
                                ctx.pinned_panel_ids.append(p)
                    elif act == "exclude_panel":
                        for p in parsed.get("excluded_panel_ids", []):
                            if p not in ctx.excluded_panel_ids:
                                ctx.excluded_panel_ids.append(p)

    def reset_context(self, salesperson_id: Optional[str] = None):
        """Réinitialise complètement le contexte actif d'un conseiller (quitte le dossier en cours)."""
        ctx = self._get_context(salesperson_id)
        ctx.reset()
        self.last_campaign_plan = None
        self.current_client_name = None

    def load_dossier(self, dossier: Dict[str, Any], salesperson_id: Optional[str] = None):
        """
        Charge un dossier commercial existant en tant que contexte actif exclusif.
        Quitte et remplace intégralement tout dossier ou plan précédemment en cours.
        """
        ctx = self._get_context(salesperson_id)
        ctx.reset()

        c_name = dossier.get("client_name")
        ctx.client_name = c_name
        self.current_client_name = c_name

        plan = dossier.get("campaign_plan")
        if plan:
            ctx.last_campaign_plan = plan
            self.last_campaign_plan = plan
            ctx.target_periods = list(plan.get("periods") or dossier.get("periods") or [])
            if plan.get("summary"):
                ctx.count_requested = plan["summary"].get("faces_per_month", dossier.get("faces_count", 5))
            locs = []
            for m in plan.get("months", []):
                for p in m.get("panels", []):
                    v = p.get("ville")
                    if v and v not in locs:
                        locs.append(v)
            if not locs and dossier.get("location"):
                locs = [dossier.get("location")]
            ctx.locations = locs
        else:
            ctx.last_campaign_plan = None
            self.last_campaign_plan = None
            ctx.locations = [dossier.get("location")] if dossier.get("location") else []
            ctx.target_periods = list(dossier.get("periods") or [])
            ctx.count_requested = dossier.get("faces_count", 5)

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        client_name: Optional[str] = None,
        salesperson_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Traite un message utilisateur de bout en bout avec suivi continu de la réflexion de campagne.
        """
        start_total = time.time()
        timing = {}

        # 0. Récupération et maintenance du contexte conversationnel
        ctx = self._get_context(salesperson_id)
        lower_msg = user_message.lower()
        is_refine_clue = any(k in lower_msg for k in ["refais", "regén", "regen", "élargi", "elargi", "garde", "ok pour", "sans la", "pas la", "enlève", "enleve", "ajoute", "mets à jour", "actualise"])
        if conversation_history is not None and len(conversation_history) == 0 and not is_refine_clue:
            ctx.reset()
        elif conversation_history:
            self._reconstruct_context_from_history(conversation_history, ctx)

        # 1. Extraction NLU
        t0 = time.time()
        extracted = self.extractor.extract(
            user_message,
            conversation_history=conversation_history,
            active_context=ctx.to_dict() if (ctx.locations or ctx.target_periods) else None
        )
        timing["extraction_ms"] = round((time.time() - t0) * 1000, 1)

        intent = extracted.get("intent", "search_panels")
        target_id = extracted.get("target_id")
        candidate_panels: List[Dict[str, Any]] = []

        # Détection et enrichissement automatique des localités secondaires et hameaux
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

        # Si l'utilisateur change de ville/zone sans demander explicitement un affinement, réinitialiser les panneaux épinglés de l'ancienne zone
        if detected_locations and ctx.locations and not is_refine_clue:
            old_locs = [normalize_text(l) for l in ctx.locations]
            new_locs = [normalize_text(l) for l in detected_locations]
            if not any(nl in old_locs or any(ol in nl for ol in old_locs) for nl in new_locs):
                ctx.pinned_panel_ids = []
                ctx.excluded_panel_ids = []
                ctx.last_campaign_plan = None
                ctx.locations = list(detected_locations)

        # Les requêtes d'information de disponibilité ne doivent pas hériter des panneaux épinglés d'une campagne
        if intent in ["check_availability", "search_panels"]:
            extracted["pinned_panel_ids"] = []

        # Prise en compte du commercial connecté
        current_sp = self.salesperson_service.get(salesperson_id)

        # Prise en compte du nom de client s'il est spécifié en paramètre ou dans l'extraction
        if client_name and client_name.strip():
            self.current_client_name = client_name.strip()
            ctx.client_name = client_name.strip()
        if extracted.get("client_name"):
            self.current_client_name = extracted["client_name"]
            ctx.client_name = extracted["client_name"]

        # Traitement spécifique : Définition ou mise à jour directe du client (ex: "client : Toma", "c'est pour Marjorie Toma")
        if (intent == "set_client_name" or (
            extracted.get("client_name")
            and not extracted.get("locations")
            and not extracted.get("axes")
            and not extracted.get("target_periods")
            and not extracted.get("target_id")
            and intent not in ["campaign_proposal", "check_availability", "creative_advice", "technical_specs", "refine_campaign", "motivate_proposal", "coordinator_dialogue", "general_chat"]
            and not extracted.get("is_open_consultation")
        )):
            client_name_val = extracted.get("client_name") or self.current_client_name or "Client"
            self.current_client_name = client_name_val
            ctx.client_name = client_name_val
            target_plan = ctx.last_campaign_plan or self.last_campaign_plan
            if target_plan:
                pdf_path = self.pdf_service.generate_campaign_pdf(target_plan, client_name=client_name_val, salesperson=current_sp)
                target_plan["pdf_url"] = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
                target_plan["client_name"] = client_name_val
                first_month_panels = target_plan["months"][0]["panels"] if target_plan.get("months") else []
                clean_pdf = os.path.basename(pdf_path)
                self.pending_dossiers[clean_pdf] = {
                    "salesperson_id": current_sp.get("initials", "DR"),
                    "client_name": client_name_val,
                    "campaign_plan": target_plan,
                    "candidate_panels": first_month_panels,
                    "user_message": user_message
                }
                target_plan["dossier_id"] = None
                frontend_panels = []
                for p in first_month_panels:
                    dir_str = p.get("direction_in") or p.get("direction_out") or "Double sens"
                    frontend_panels.append({
                        "remorque": p["id"],
                        "id": p["id"],
                        "ville": p["ville"],
                        "localisation": p["localisation"],
                        "axe_routier": p.get("axe_routier", ""),
                        "direction": dir_str,
                        "distance_km": p.get("distance_km"),
                        "frequentation": p.get("frequentation_jour"),
                        "ots": p.get("ots_mensuel"),
                        "contexte_visibilite": p.get("contexte_visibilite"),
                        "lien": p["lien"],
                        "photo": p.get("photo_url"),
                        "image_url": p.get("photo_url"),
                        "lat": p.get("lat"),
                        "lng": p.get("lng")
                    })
                client_info = self.client_agent.analyze_client(client_name_val, raw_message=user_message)
                text = (
                    f"Le Plan Média a bien été personnalisé pour votre client **{client_name_val}** ! 📄\n\n"
                    f"{client_info.get('summary_text')}\n\n"
                    f"Le document PDF complet intégrant les cartes d'implantation HD et le maillage stratégique a été mis à jour au nom de **{client_name_val}**.\n\n"
                    f"Vous pouvez le télécharger directement ci-dessous."
                )
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                return {
                    "text": text,
                    "panels": frontend_panels,
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": target_plan,
                    "client_name": self.current_client_name,
                    "plan_pdf_url": target_plan.get("pdf_url"),
                    "agent_name": "Agent Intelligence Client & Chalandise",
                    "badge": "🔵 Client",
                    "client_analysis": client_info
                }
            else:
                client_info = self.client_agent.analyze_client(client_name_val, raw_message=user_message)
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                return {
                    "text": client_info["summary_text"],
                    "panels": [],
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": None,
                    "client_name": self.current_client_name,
                    "agent_name": client_info.get("agent_name", "Agent Intelligence Client & Chalandise"),
                    "badge": client_info.get("badge", "🔵 Client"),
                    "client_analysis": client_info
                }

        # 2. CONTINUITÉ DE CONVERSATION : Gestion des raffinements de campagne (refine_campaign)
        refinement_action = extracted.get("refinement_action")

        # Cas 0 : Ajout d'une ou plusieurs faces sur une campagne existante (ex: "ajoute une face chaque mois près d'éghezee")
        if intent == "refine_campaign" and refinement_action == "add_face" and ctx.last_campaign_plan:
            target_loc = extracted.get("locations", [None])[0] if extracted.get("locations") else None
            delta = extracted.get("delta_count", 1) or 1
            if target_loc and target_loc not in ctx.locations:
                ctx.locations.append(target_loc)

            res_add = self.campaign_agent.add_face_to_campaign(
                campaign_plan=ctx.last_campaign_plan,
                location=target_loc,
                delta_count=delta,
                client_name=ctx.client_name or self.current_client_name,
                salesperson=current_sp,
                active_locations=ctx.locations
            )
            ctx.last_campaign_plan = res_add["campaign_plan"]
            self.last_campaign_plan = res_add["campaign_plan"]
            if ctx.last_campaign_plan.get("summary"):
                ctx.count_requested = ctx.last_campaign_plan["summary"].get("faces_per_month", ctx.count_requested)

            # Mise en attente de sauvegarde du dossier
            if res_add.get("pdf_url"):
                clean_pdf = os.path.basename(res_add["pdf_url"].split("file=")[-1])
                self.pending_dossiers[clean_pdf] = {
                    "salesperson_id": current_sp.get("initials", "DR"),
                    "client_name": ctx.client_name or self.current_client_name or "Partenaire",
                    "campaign_plan": ctx.last_campaign_plan,
                    "candidate_panels": res_add["panels"],
                    "user_message": user_message
                }

            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
            frontend_panels = self._build_frontend_panels(res_add["panels"], user_message)
            return {
                "text": res_add["text"],
                "panels": frontend_panels,
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": ctx.last_campaign_plan,
                "client_name": self.current_client_name or ctx.client_name,
                "salesperson": current_sp,
                "plan_pdf_url": res_add.get("pdf_url"),
                "agent_name": res_add.get("agent_name", "Agent Plan Média & Stratégie"),
                "badge": res_add.get("badge", "🟠 Plan Média")
            }

        # Cas A : Élargissement géographique d'une campagne existante (ex: "élargis vers wavre")
        if intent == "refine_campaign" and refinement_action == "expand_zone" and ctx.last_campaign_plan:
            new_locs = extracted.get("locations", [])
            for loc in new_locs:
                if loc and loc not in ctx.locations:
                    ctx.locations.append(loc)
            
            # Rechercher des panneaux dans la zone étendue pour les périodes actives de la campagne
            periods_to_search = ctx.target_periods if ctx.target_periods else extracted.get("target_periods", [])
            t0 = time.time()
            candidate_panels = self.engine.search_and_rank(
                locations=new_locs,
                target_periods=periods_to_search,
                top_k=4,
                require_availability=True if periods_to_search else False
            )
            if not candidate_panels:
                candidate_panels = self.engine.search_and_rank(
                    locations=new_locs,
                    target_periods=periods_to_search,
                    top_k=4,
                    require_availability=False
                )
            timing["engine_ms"] = round((time.time() - t0) * 1000, 1)

            loc_names = ", ".join(new_locs) if new_locs else "ce secteur"
            periods_human = [format_period_human(p) for p in periods_to_search]
            periods_str = " · ".join(periods_human) if periods_human else "Prochainement"

            lines = [
                f"Pour élargir votre sélection de campagne (**{periods_str}**) vers le secteur de **{loc_names}**, voici les emplacements 8m² disponibles :\n"
            ]
            for idx, p in enumerate(candidate_panels, 1):
                freq_str = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")
                axe_display = f"{p.get('code_route') or p.get('axe_routier')} " if (p.get('code_route') or p.get('axe_routier')) else ""
                direction = p.get('direction_in') or p.get('direction_out') or "Double sens"
                friendly_dispo = p.get('prochaine_dispo_label') or p.get('prochaine_dispo_human') or format_period_human(p.get('prochaine_dispo'))
                if p.get('target_period_human') and p.get('is_available_in_target_period'):
                    friendly_dispo = f"Libre en {p['target_period_human']}"
                lines.append(f"**{idx}.** [#{p['id']} {p['ville']} ({p['localisation']}) ↗️]({p['lien']}) — {axe_display}dir. {direction} · **{freq_str} v/j** · *{friendly_dispo}*")

            lines.append("")
            lines.append("💡 **Intégration au plan média :**")
            lines.append("Indiquez-moi le ou les panneaux que vous validez (ex: *« ok pour la 108 »*), ou demandez directement *« refais ma sélection »* pour rééquilibrer automatiquement les 5 faces sur l'ensemble du bassin élargi.")
            final_text = "\n".join(lines)

            timing["synthesis_ms"] = 1.0
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
            frontend_panels = self._build_frontend_panels(candidate_panels, user_message)
            return {
                "text": final_text,
                "panels": frontend_panels,
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": ctx.last_campaign_plan,
                "client_name": self.current_client_name,
                "salesperson": current_sp
            }

        # Cas B : Validation / Épinglage d'un panneau (ex: "ok pour la 108", "garde la 108")
        if intent == "refine_campaign" and refinement_action == "pin_panel":
            pids = extracted.get("pinned_panel_ids") or ([extracted.get("target_id")] if extracted.get("target_id") else [])
            for pid in pids:
                pid_clean = str(pid).strip().replace("#", "")
                if pid_clean and pid_clean not in ctx.pinned_panel_ids:
                    ctx.pinned_panel_ids.append(pid_clean)
                if pid_clean in ctx.excluded_panel_ids:
                    ctx.excluded_panel_ids.remove(pid_clean)

            # Résolution des communes et périodes cibles
            candidate_locations = list(ctx.locations) if ctx.locations else []
            for pid in ctx.pinned_panel_ids:
                tr = self.engine.get_trailer_by_id(pid)
                if tr and tr.get("ville") and tr.get("ville") not in candidate_locations:
                    candidate_locations.append(tr.get("ville"))
            if not candidate_locations:
                candidate_locations = ["Wallonie"]

            periods = ctx.target_periods or extracted.get("target_periods") or ["2026-11"]
            count_requested = extracted.get("count_requested") or len(ctx.pinned_panel_ids)
            eff_client = extracted.get("client_name") or self.current_client_name or ctx.client_name or "Partenaire"
            if extracted.get("client_name"):
                self.current_client_name = extracted.get("client_name")

            # Génération immédiate du Plan Média certifié avec les faces retenues
            campaign_plan = self.engine.plan_multi_month_campaign(
                locations=candidate_locations,
                target_periods=periods,
                count_per_month=count_requested,
                pinned_panel_ids=ctx.pinned_panel_ids,
                excluded_panel_ids=ctx.excluded_panel_ids
            )
            ctx.last_campaign_plan = campaign_plan
            self.last_campaign_plan = campaign_plan

            # Génération du PDF officiel du Plan Média
            plan_pdf_path = self.pdf_service.generate_campaign_pdf(
                campaign_plan=campaign_plan,
                client_name=eff_client,
                salesperson=current_sp
            )
            clean_pdf_filename = os.path.basename(plan_pdf_path)
            self.pending_dossiers[clean_pdf_filename] = {
                "campaign_plan": campaign_plan,
                "client_name": eff_client,
                "salesperson": current_sp
            }

            seen_ids = set()
            candidate_panels = []
            for m in campaign_plan.get("months", []):
                for p in m.get("panels", []):
                    if str(p["id"]) not in seen_ids:
                        seen_ids.add(str(p["id"]))
                        candidate_panels.append(p)

            frontend_panels = self._build_frontend_panels(candidate_panels, user_message)

            final_text = self.sales.generate_pitch(
                user_message=user_message,
                extracted_info=extracted,
                candidate_panels=frontend_panels,
                conversation_history=conversation_history,
                campaign_plan=campaign_plan
            )

            timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)

            return {
                "text": final_text,
                "panels": frontend_panels,
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": campaign_plan,
                "client_name": eff_client,
                "salesperson": current_sp,
                "plan_pdf_url": f"/api/download-plan-pdf?file={clean_pdf_filename}"
            }

        # Cas C : Exclusion / Retrait d'un panneau (ex: "pas la 323", "enlève la 323")
        if intent == "refine_campaign" and refinement_action == "exclude_panel":
            pids = extracted.get("excluded_panel_ids") or ([extracted.get("target_id")] if extracted.get("target_id") else [])
            for pid in pids:
                pid_clean = str(pid).strip().replace("#", "")
                if pid_clean and pid_clean not in ctx.excluded_panel_ids:
                    ctx.excluded_panel_ids.append(pid_clean)
                if pid_clean in ctx.pinned_panel_ids:
                    ctx.pinned_panel_ids.remove(pid_clean)

            pid_str = f"#{pids[0]}" if pids else "demandé"
            final_text = (
                f"❌ L'emplacement **{pid_str}** a bien été retiré de votre sélection de campagne.\n\n"
                f"👉 Dites **« refais ma sélection »** pour recalculer le plan avec un autre panneau de remplacement et actualiser le document PDF."
            )
            timing["synthesis_ms"] = 1.0
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
            return {
                "text": final_text,
                "panels": [],
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": ctx.last_campaign_plan,
                "client_name": self.current_client_name,
                "salesperson": current_sp
            }

        # 3. Moteur Déterministe Spatial & Planification
        t0 = time.time()
        if intent == "check_availability" and target_id:
            trailer = self.engine.get_trailer_by_id(target_id)
            if trailer:
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
            candidate_panels = self.engine.search_and_rank(
                locations=extracted.get("locations"),
                axes=extracted.get("axes"),
                province=extracted.get("province"),
                direction=extracted.get("direction"),
                top_k=1,
                require_availability=False
            )

        # Cas Motivation de la proposition (ex: "Motive-moi ta proposition ?", "Pourquoi ce choix ?")
        if intent == "motivate_proposal":
            candidate_panels = []
            if ctx.last_campaign_plan and ctx.last_campaign_plan.get("months"):
                candidate_panels = ctx.last_campaign_plan["months"][0].get("panels", [])
            elif self.last_campaign_plan and self.last_campaign_plan.get("months"):
                candidate_panels = self.last_campaign_plan["months"][0].get("panels", [])
            elif ctx.candidate_panels:
                candidate_panels = ctx.candidate_panels

            eff_client = extracted.get("client_name") or ctx.client_name or self.current_client_name or "votre annonceur"
            campaign_plan = ctx.last_campaign_plan or self.last_campaign_plan

            frontend_panels = self._build_frontend_panels(candidate_panels, user_message) if candidate_panels else []
            final_text = self.sales.generate_proposal_motivation(
                panels=candidate_panels,
                extracted_info=extracted,
                campaign_plan=campaign_plan,
                client_name=eff_client,
                user_message=user_message
            )
            timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
            return {
                "text": final_text,
                "panels": frontend_panels,
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": campaign_plan,
                "client_name": eff_client,
                "salesperson": current_sp,
                "plan_pdf_url": campaign_plan.get("pdf_url") if campaign_plan else None,
                "dossier_id": None,
                "agent_name": "Agent Plan Média & Stratégie",
                "badge": "🟠 Plan Média"
            }

        # Cas Dialogue Coordinateur & Collaboration Agents (ex: "As-tu pris en compte l'annonceur... ?", "Que me conseilles-tu ?")
        if intent in ["coordinator_dialogue", "general_chat"]:
            return self.handle_coordinator_dialogue(
                user_message=user_message,
                extracted=extracted,
                conversation_history=conversation_history,
                ctx=ctx,
                current_sp=current_sp,
                timing=timing,
                start_total=start_total
            )

        campaign_plan = None
        # Cas D : Proposition de campagne initiale OU Régénération d'une sélection affinée
        is_regeneration = extracted.get("is_regeneration", False)
        if intent == "campaign_proposal" or is_regeneration:
            # Si régénération ou paramètres manquants dans la requête, hériter du contexte actif
            if is_regeneration or (not extracted.get("locations") and not extracted.get("target_periods") and (ctx.locations or ctx.target_periods)):
                target_periods = ctx.target_periods or extracted.get("target_periods", [])
                locations = ctx.locations if ctx.locations else (extracted.get("locations") or ["Wallonie"])
                count_req = ctx.count_requested
                pinned_ids = ctx.pinned_panel_ids
                excluded_ids = ctx.excluded_panel_ids
                loc_label = locations[0] if locations else "Wallonie"
                eff_client = ctx.client_name or self.current_client_name or f"Campagne {loc_label}"
            else:
                target_periods = extracted.get("target_periods") or ctx.target_periods
                locations = extracted.get("locations") or ctx.locations or ["Wallonie"]
                count_req = extracted.get("count_requested", 5)
                pinned_ids = extracted.get("pinned_panel_ids") or ctx.pinned_panel_ids
                excluded_ids = extracted.get("excluded_panel_ids") or ctx.excluded_panel_ids
                loc_label = locations[0] if locations else "Wallonie"
                eff_client = extracted.get("client_name") or ctx.client_name or self.current_client_name or f"Campagne {loc_label}"

            # Détection d'un profil client historique M Move (ex: Marjorie Toma, Green Robot)
            preferred_affinity_ids = []
            if eff_client:
                hist = self.client_agent.get_client_history(eff_client)
                if hist:
                    if (not extracted.get("locations") or extracted.get("locations") == ["Wallonie"]) and hist.get("preferred_locations"):
                        locations = hist["preferred_locations"]
                    # Affinité historique : suggestion préférentielle pour la rotation, jamais de forçage en doublon consécutif
                    if hist.get("preferred_panel_ids"):
                        preferred_affinity_ids = [str(p) for p in hist["preferred_panel_ids"]]

            # Détection d'une demande spécifique de maintien continu d'un panneau (ex: "garde la 324 chaque mois")
            specific_continuous_ids = []
            lower_msg = user_message.lower()
            if any(w in lower_msg for w in ["chaque mois", "tous les mois", "sur toute la durée", "sur toute la campagne", "en continu"]):
                for pid in (pinned_ids or []):
                    specific_continuous_ids.append(str(pid))

            # Mémoriser dans le contexte
            ctx.locations = list(locations)
            ctx.target_periods = list(target_periods)
            ctx.count_requested = count_req
            ctx.pinned_panel_ids = list(pinned_ids)
            ctx.excluded_panel_ids = list(excluded_ids)
            ctx.client_name = eff_client

            extracted["locations"] = locations
            extracted["target_periods"] = target_periods
            extracted["count_requested"] = count_req

            # Planification de campagne multi-mois avec rotation dynamique, axes distincts et zéro doublon consécutif
            campaign_plan = self.engine.plan_multi_month_campaign(
                locations=locations,
                target_periods=target_periods,
                count_per_month=count_req,
                axes=extracted.get("axes") or ctx.axes,
                pinned_panel_ids=pinned_ids,
                excluded_panel_ids=excluded_ids,
                preferred_affinity_ids=preferred_affinity_ids,
                specific_continuous_ids=specific_continuous_ids
            )
            # Génération des cartes géographiques haute définition par mois (1300x880)
            for m in campaign_plan.get("months", []):
                m_img = self.map_service.generate_campaign_map(m["panels"], period_str=m["period"], width=1300, height=880)
                m["map_url"] = f"/api/map/{os.path.basename(m_img)}"

            campaign_plan["client_name"] = eff_client

            # Génération du Plan Média complet au format PDF A4 Paysage
            pdf_path = self.pdf_service.generate_campaign_pdf(campaign_plan, client_name=eff_client, salesperson=current_sp)
            campaign_plan["pdf_url"] = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"

            # Panneaux de référence pour l'affichage initial
            candidate_panels = []
            if campaign_plan.get("months"):
                candidate_panels = campaign_plan["months"][0]["panels"]

            # Mise en attente de sauvegarde du dossier commercial (sauvegarde effective au téléchargement du PDF)
            clean_pdf = os.path.basename(pdf_path)
            self.pending_dossiers[clean_pdf] = {
                "salesperson_id": current_sp.get("initials", "DR"),
                "client_name": eff_client,
                "campaign_plan": campaign_plan,
                "candidate_panels": candidate_panels,
                "user_message": user_message
            }
            campaign_plan["dossier_id"] = None
            self.last_campaign_plan = campaign_plan
            ctx.last_campaign_plan = campaign_plan
            ctx.candidate_panels = candidate_panels

            timing["engine_ms"] = round((time.time() - t0) * 1000, 1)
            t_synth = time.time()
            frontend_panels = self._build_frontend_panels(candidate_panels, user_message)
            final_text = self.sales.generate_pitch(
                user_message=user_message,
                extracted_info=extracted,
                candidate_panels=frontend_panels,
                conversation_history=conversation_history,
                campaign_plan=campaign_plan
            )
            timing["synthesis_ms"] = round((time.time() - t_synth) * 1000, 1)
            timing["total_ms"] = round((time.time() - start_total) * 1000, 1)

            return {
                "text": final_text,
                "panels": frontend_panels,
                "extracted": extracted,
                "timing": timing,
                "campaign_plan": campaign_plan,
                "client_name": eff_client,
                "salesperson": current_sp,
                "plan_pdf_url": campaign_plan.get("pdf_url"),
                "dossier_id": None,
                "agent_name": "Agent Plan Média & Stratégie",
                "badge": "🟠 Plan Média"
            }

        else:
            # Recherche géographique & critères (search_panels ou check_availability par zone)
            target_periods = extracted.get("target_periods", []) or (ctx.target_periods if not ctx.last_campaign_plan else [])
            req_dispo = len(target_periods) > 0
            is_dispo_query = (
                intent == "check_availability"
                or any(w in user_message.lower() for w in ["dispo", "dispos", "disponibilit", "libre", "libres", "quand", "prochain", "prochaine", "prochaines", "date", "dates"])
            )
            count_req = extracted.get("count_requested")
            if is_dispo_query and not count_req:
                top_k = 50  # Renvoyer TOUTES les disponibilités sans limitation arbitraire
            elif count_req:
                top_k = count_req
            else:
                top_k = 50 if is_dispo_query else 5

            eff_client = extracted.get("client_name") or ctx.client_name or self.current_client_name
            is_client_ref = extracted.get("is_referring_to_active_client") or any(
                p in user_message.lower() for p in ["pour lui", "pour elle", "pour ce client", "pour cette cliente", "pour l'annonceur", "pour cet annonceur"]
            )

            # Si l'utilisateur demande les disponibilités "pour lui", mais qu'aucun annonceur n'est renseigné
            if is_dispo_query and is_client_ref and not eff_client and not extracted.get("locations") and not ctx.locations:
                timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                period_str = ""
                if target_periods:
                    from core.agents.engine_tools import format_period_human
                    period_str = f" en {format_period_human(target_periods[0])}"
                dialogue_text = (
                    f"Vous me demandez les disponibilités **« pour lui »**{period_str}, mais aucun annonceur n'est actuellement renseigné dans votre session ou votre dossier.\n\n"
                    "👉 **Pour quel annonceur ou dans quelle commune souhaitez-vous vérifier les disponibilités ?**\n"
                    "*(ex: « C'est pour Marjorie Toma », « Brico Ciney », « Greenrobot », ou une localité comme Wavre, Namur, Gembloux...)*\n\n"
                    "Dès que vous me l'indiquez, je filtrerai directement les disponibilités sur sa zone de chalandise prioritaire !"
                )
                return {
                    "text": dialogue_text,
                    "panels": [],
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": ctx.last_campaign_plan,
                    "client_name": None,
                    "salesperson": current_sp,
                    "plan_pdf_url": None,
                    "dossier_id": None,
                    "agent_name": "Coordinateur M Move Conseil",
                    "badge": "💬 Coordinateur"
                }

            # Si un annonceur est actif et qu'aucune localité explicite n'est donnée dans la demande de dispo
            if is_dispo_query and eff_client and not extracted.get("locations"):
                hist = self.client_agent.get_client_history(eff_client)
                analysis = self.client_agent.analyze_client(eff_client)
                if hist and hist.get("preferred_locations"):
                    extracted["locations"] = list(hist["preferred_locations"])
                    ctx.locations = list(hist["preferred_locations"])
                elif analysis.get("city") and analysis.get("city") != "Wallonie":
                    extracted["locations"] = [analysis["city"]]
                    ctx.locations = [analysis["city"]]

            search_locations = extracted.get("locations") or (ctx.locations if (is_dispo_query or ctx.locations) else None)
            if extracted.get("locations"):
                ctx.locations = list(extracted.get("locations"))
            if target_periods:
                ctx.target_periods = list(target_periods)

            # Si recherche de disponibilité : déléguer directement à l'Agent Inventaire & Disponibilités
            if is_dispo_query:
                is_explicit_expand = (
                    extracted.get("refinement_action") == "expand_zone"
                    or any(w in user_message.lower() for w in ["élargis", "elargis", "élargir", "elargir", "plus large", "communes voisines", "avec la périphérie", "avec la peripherie"])
                )

                # Gestion progressive du cercle de recherche (+5 km par élargissement)
                if is_explicit_expand:
                    km_match = re.search(r"(\d+)\s*km", user_message.lower())
                    delta = float(km_match.group(1)) if km_match else 5.0
                    prev_r = getattr(ctx, "search_radius_km", 5.0) or 5.0
                    ctx.search_radius_km = prev_r + delta
                else:
                    if extracted.get("locations"):
                        ctx.search_radius_km = 5.0
                    elif not getattr(ctx, "search_radius_km", None):
                        ctx.search_radius_km = 5.0

                inv_res = self.inventory_agent.handle_availability_query(
                    user_message=user_message,
                    extracted_info=extracted,
                    locations=search_locations,
                    target_periods=target_periods,
                    is_explicit_expand=is_explicit_expand,
                    salesperson=current_sp,
                    current_radius_km=ctx.search_radius_km
                )
                timing["engine_ms"] = round((time.time() - t0) * 1000, 1)
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                frontend_panels = self._build_frontend_panels(inv_res["panels"], user_message)

                return {
                    "text": inv_res["text"],
                    "panels": frontend_panels,
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": None,
                    "client_name": self.current_client_name,
                    "salesperson": current_sp,
                    "availability_pdf_url": inv_res.get("availability_pdf_url"),
                    "can_expand_zone": inv_res.get("can_expand_zone", False),
                    "peripheral_count": inv_res.get("peripheral_count", 0),
                    "peripheral_cities": inv_res.get("peripheral_cities", []),
                    "search_circle": inv_res.get("search_circle"),
                    "current_radius_km": inv_res.get("current_radius_km", ctx.search_radius_km),
                    "next_radius_km": inv_res.get("next_radius_km", ctx.search_radius_km + 5.0),
                    "target_periods": target_periods,
                    "location": (search_locations or ["Wallonie"])[0],
                    "dossier_id": None,
                    "agent_name": inv_res.get("agent_name", "Agent Inventaire & Disponibilités"),
                    "badge": inv_res.get("badge", "🟢 Inventaire")
                }

            candidate_panels = self.engine.search_and_rank(
                locations=search_locations,
                axes=extracted.get("axes"),
                target_periods=target_periods or ctx.target_periods,
                province=extracted.get("province"),
                direction=extracted.get("direction"),
                contexte_query=extracted.get("contexte_pref") or extracted.get("sector"),
                max_distance_km=25.0,
                top_k=top_k,
                require_availability=req_dispo,
                sort_by_dispo=False
            )
            can_expand_zone = False
            peripheral_count = 0
            peripheral_cities = []

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

        # Génération du Catalogue PDF des disponibilités pour sélection client
        availability_pdf_url = None
        if is_dispo_query and candidate_panels:
            loc_label = (search_locations or ["Wallonie"])[0]
            eff_client = extracted.get("client_name") or self.current_client_name or ctx.client_name or "Partenaire"
            try:
                dispo_pdf_path = self.pdf_service.generate_availability_pdf(
                    panels=candidate_panels,
                    location_name=loc_label,
                    periods=target_periods or ctx.target_periods,
                    client_name=eff_client,
                    salesperson=current_sp
                )
                clean_dispo_file = os.path.basename(dispo_pdf_path)
                availability_pdf_url = f"/api/download-availability-pdf?file={clean_dispo_file}"
            except Exception as e:
                print(f"[Coordinator] Error generating availability PDF: {e}")

        # Construction des fiches frontend enrichies
        frontend_panels = self._build_frontend_panels(candidate_panels, user_message)

        # Synthèse Commerciale Experte
        t0 = time.time()
        final_text = self.sales.generate_pitch(
            user_message=user_message,
            extracted_info=extracted,
            candidate_panels=frontend_panels,
            conversation_history=conversation_history,
            campaign_plan=campaign_plan,
            availability_pdf_url=availability_pdf_url,
            can_expand_zone=can_expand_zone,
            peripheral_count=peripheral_count,
            peripheral_cities=peripheral_cities
        )
        ctx.candidate_panels = candidate_panels
        timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)

        return {
            "text": final_text,
            "panels": frontend_panels,
            "extracted": extracted,
            "timing": timing,
            "campaign_plan": campaign_plan,
            "client_name": self.current_client_name,
            "salesperson": current_sp,
            "availability_pdf_url": availability_pdf_url,
            "plan_pdf_url": campaign_plan.get("pdf_url") if campaign_plan else None,
            "can_expand_zone": can_expand_zone,
            "peripheral_count": peripheral_count,
            "peripheral_cities": peripheral_cities,
            "target_periods": target_periods or ctx.target_periods,
            "location": (search_locations or ["Wallonie"])[0] if is_dispo_query else None,
            "dossier_id": campaign_plan.get("dossier_id") if campaign_plan else None,
            "agent_name": "Agent Plan Média & Stratégie" if campaign_plan else "Agent Inventaire & Disponibilités",
            "badge": "🟠 Plan Média" if campaign_plan else "🟢 Inventaire"
        }

    def _build_frontend_panels(self, candidate_panels: List[Dict[str, Any]], user_message: str = "") -> List[Dict[str, Any]]:
        user_mentions_face = any(w in user_message.lower() for w in ["face in", "face out", "faces in", "faces out", "face a", "face b", "face "])
        frontend_panels = []
        for p in candidate_panels:
            dir_str = p.get("direction_in") or p.get("direction_out") or "Double sens"
            avail_months = p.get("availability", {}).get("available_months", [])
            friendly_dispo = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or format_period_human(p.get("prochaine_dispo"))
            if not user_mentions_face and friendly_dispo:
                friendly_dispo = re.sub(r"\s*\(Face[^\)]*\)", "", str(friendly_dispo), flags=re.IGNORECASE).strip()

            if avail_months:
                if len(avail_months) > 1:
                    dispo_label = "Libre en " + " & ".join([m["period_human"] for m in avail_months])
                else:
                    dispo_label = f"Libre en {avail_months[0]['period_human']}"
                friendly_dispo = dispo_label
            elif p.get("target_period_human") and p.get("is_available_in_target_period"):
                dispo_label = f"Libre en {p['target_period_human']}"
                friendly_dispo = f"Libre en {p['target_period_human']}"
            else:
                friendly_dispo = friendly_dispo or "Disponible"
                dispo_label = friendly_dispo

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
                "frequentation_jour": p.get("frequentation_jour"),
                "ots": p.get("ots_mensuel"),
                "ots_mensuel": p.get("ots_mensuel"),
                "contexte_visibilite": p.get("contexte_visibilite"),
                "lien": p["lien"],
                "photo": p.get("photo_url"),
                "image_url": p.get("photo_url"),
                "is_direct_match": p.get("is_direct_match", False),
                "prochaine_dispo": dispo_label,
                "prochaine_dispo_human": friendly_dispo,
                "active": "O",
                "score": p.get("total_score"),
                "lat": p.get("lat"),
                "lng": p.get("lng")
            })
        return frontend_panels

    def save_pending_dossier_on_download(self, clean_filename: str) -> Optional[Dict[str, Any]]:
        """
        Enregistre le dossier commercial lors du téléchargement effectif du PDF.
        Ne crée pas de doublon si le dossier existe déjà pour ce PDF.
        """
        if not clean_filename:
            return None

        # 1. Vérifier si un dossier existe déjà pour ce fichier PDF
        existing = self.dossier_service.get_dossier_by_pdf(clean_filename)
        if existing:
            return existing

        # 2. Chercher dans les propositions en attente
        pending = self.pending_dossiers.get(clean_filename)
        if not pending:
            # Fallback : chercher dans les derniers plans de campagne connus
            all_plans = [self.last_campaign_plan] + [c.last_campaign_plan for c in self.contexts.values() if c.last_campaign_plan]
            for plan in all_plans:
                if plan and clean_filename in plan.get("pdf_url", ""):
                    first_panels = plan["months"][0]["panels"] if plan.get("months") else []
                    pending = {
                        "salesperson_id": plan.get("salesperson", {}).get("initials", "DR"),
                        "client_name": plan.get("client_name", "Client"),
                        "campaign_plan": plan,
                        "candidate_panels": first_panels,
                        "user_message": "Téléchargement direct du Plan Média PDF"
                    }
                    break

        if pending:
            dossier = self.dossier_service.save_dossier(
                salesperson_id=pending.get("salesperson_id", "DR"),
                client_name=pending.get("client_name", "Client"),
                campaign_plan=pending.get("campaign_plan", {}),
                candidate_panels=pending.get("candidate_panels", []),
                user_message=pending.get("user_message", "")
            )
            if pending.get("campaign_plan"):
                pending["campaign_plan"]["dossier_id"] = dossier.get("id")
            return dossier

        return None

    def handle_coordinator_dialogue(
        self,
        user_message: str,
        extracted: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[ActiveCampaignContext] = None,
        current_sp: Optional[Dict[str, Any]] = None,
        timing: Optional[Dict[str, float]] = None,
        start_total: float = 0.0
    ) -> Dict[str, Any]:
        """
        Gère le dialogue direct entre le commercial, le coordinateur M Move et ses agents spécialisés.
        Répond aux questions de méthode, de pertinence annonceur, de rôle des agents, ou de salutations,
        sans jamais renvoyer de panneaux dupliqués ni écraser les résultats visuels existants.
        """
        import time
        from core.agents.engine_tools import normalize_text, format_period_human

        if timing is None:
            timing = {}
        t0 = time.time()
        lower_msg = user_message.lower()

        eff_client = extracted.get("client_name") or (ctx.client_name if ctx else None) or self.current_client_name
        active_plan = (ctx.last_campaign_plan if ctx else None) or self.last_campaign_plan
        active_periods = (ctx.target_periods if ctx else None) or (active_plan.get("periods") if active_plan else [])
        active_locations = (ctx.locations if ctx else None) or []
        period_label = format_period_human(active_periods[0]) if active_periods else "la période demandée"

        # 1. Analyse thématique de l'interpellation
        is_client_concern = any(w in lower_msg for w in [
            "annonceur", "client", "pris en compte", "tenu compte", "toutes ces faces", "toute la wallonie",
            "pour lui", "pour elle", "pour ce client", "pourquoi ces faces", "pourquoi tout", "pourquoi tant",
            "adapté à son activité", "adapte a son activite", "adapté pour lui", "adapte pour lui",
            "pourquoi autant", "pourquoi ce choix", "pourquoi ces choix"
        ])
        is_client_info_query = any(w in lower_msg for w in [
            "qui est l'annonceur", "qui est le client", "quel est le client", "quel est l'annonceur",
            "que sais-tu sur", "que sait-on sur", "connais-tu", "profil de", "chalandise de"
        ])
        is_agent_query = any(w in lower_msg for w in [
            "agent", "agents", "équipe", "comment travaillent", "comment tu travailles", "rôle", "coordinateur"
        ])
        is_advice_query = any(w in lower_msg for w in [
            "que me conseilles-tu", "que conseilles-tu", "comment on procède", "comment procéder",
            "prochaine étape", "suite", "que faire", "qu'en penses-tu"
        ])
        is_tech_query = any(w in lower_msg for w in [
            "format", "bâche", "bache", "390x200", "390", "bat", "délai", "delai", "face in", "face out"
        ])
        is_greeting = any(w in lower_msg for w in [
            "bonjour", "bonsoir", "salut", "hello", "coucou", "merci", "super", "c'est parfait"
        ])

        # Consultation des agents spécialisés
        client_hist = self.client_agent.get_client_history(eff_client) if eff_client else None
        client_analysis = self.client_agent.analyze_client(eff_client, raw_message=user_message) if eff_client else None

        # Cas 1 : Question sur la prise en compte de l'annonceur / du client
        if is_client_concern:
            if eff_client:
                sector = (client_analysis.get("sector") if client_analysis else None) or "Activité commerciale"
                est_type = (client_analysis.get("establishment_type") if client_analysis else None) or "Commerce / Entreprise"
                trade_locs = (client_hist.get("preferred_locations") if client_hist else None) or (
                    [client_analysis["city"]] if client_analysis and client_analysis.get("city") and client_analysis["city"] != "Wallonie" else []
                )
                pref_panels = (client_hist.get("preferred_panel_ids") if client_hist else None) or []
                loc_txt = ", ".join(trade_locs) if trade_locs else "sa zone de chalandise"

                dialogue_text = (
                    f"Pour votre demande précédente *(disponibilités en {period_label})*, notre **Agent Inventaire** "
                    f"a affiché les faces libres à l'échelle régionale car aucune commune ou filtre précis n'était stipulé dans votre question.\n\n"
                    f"Cependant, en concertation avec notre **Agent Intelligence Client** pour **{eff_client}** :\n"
                    f"• **Secteur & Profil :** {sector} ({est_type})\n"
                    f"• **Bassin d'attractivité prioritaire :** {loc_txt}\n"
                )
                if pref_panels:
                    p_str = ", ".join([f"#{p}" for p in pref_panels[:5]])
                    dialogue_text += f"• **Emplacements historiques réguliers :** {p_str}\n"

                dialogue_text += (
                    f"\n💡 **Recommandation du Coordinateur :**\n"
                    f"Souhaitez-vous que je filtre immédiatement les disponibilités de **{period_label}** "
                    f"sur les **faces libres situées dans sa zone prioritaire ({loc_txt})** ?"
                )
            else:
                dialogue_text = (
                    "En toute franchise : **non, aucun annonceur n'est actuellement renseigné** dans votre dossier en cours.\n\n"
                    "Pour votre demande précédente, notre **Agent Inventaire** vous a donc présenté l'ensemble des disponibilités "
                    "sur le réseau en Wallonie afin de vous donner une visibilité panoramique complète.\n\n"
                    "Pour que notre **Agent Intelligence Client** et notre **Agent Stratégie** ciblent précisément les emplacements stratégiques :\n"
                    "👉 **Quel est le nom ou l'activité de votre client ?** *(ex: « C'est pour Marjorie Toma », « Brico Ciney », « Un cuisiniste à Wavre »...)*\n\n"
                    "Dès que vous me l'indiquez, je restreindrai aussitôt la sélection à son bassin de chalandise utile !"
                )

        # Cas 2 : Demande d'information sur le client / profil
        elif is_client_info_query:
            if eff_client:
                sector = (client_analysis.get("sector") if client_analysis else None) or "Activité commerciale"
                trade_locs = (client_hist.get("preferred_locations") if client_hist else None) or []
                pref_panels = (client_hist.get("preferred_panel_ids") if client_hist else None) or []
                dialogue_text = (
                    f"Voici les données consolidées par l'**Agent Intelligence Client** pour **{eff_client}** :\n\n"
                    f"• **Secteur d'activité :** {sector}\n"
                    f"• **Zone d'attractivité historique :** {', '.join(trade_locs) if trade_locs else 'Wallonie'}\n"
                )
                if pref_panels:
                    p_str = ", ".join([f"#{p}" for p in pref_panels[:6]])
                    dialogue_text += f"• **Faces prioritaires réservées par le passé :** {p_str}\n"
                dialogue_text += "\nSouhaitez-vous que nous montions une proposition de campagne dédiée à ce client ?"
            else:
                dialogue_text = (
                    "Aucun annonceur n'est actuellement rattaché à ce dossier.\n\n"
                    "👉 Indiquez-moi simplement le nom du client *(ex: « C'est pour Marjorie Toma »)* ou chargez un dossier existant !"
                )

        # Cas 3 : Questions sur les agents ou l'équipe
        elif is_agent_query:
            dialogue_text = (
                "Je coordonne une équipe de **4 agents spécialisés M Move** à votre service :\n\n"
                "• 📍 **Agent Inventaire & Disponibilités** : surveille en temps réel les disponibilités des 133 remorques (266 faces 8m²) et filtre selon les dates et le rayon géographique.\n"
                "• 🏢 **Agent Intelligence Client & Chalandise** : analyse le profil annonceur, ses points de vente et définit sa zone d'attractivité (10-15 km).\n"
                "• 📊 **Agent Plan Média & Stratégie** : bâtit les sélections équilibrées multi-axes, planifie les rotations mensuelles et calcule les occasions d'être vu (OTS).\n"
                "• 📄 **Agent Devis & PDF** : génère en direct les Catalogues de disponibilités et les Plans Média avec bons de réservation officiels.\n\n"
                "Comment souhaitez-vous que nous vous accompagnions ?"
            )

        # Cas 4 : Conseil méthodologique / prochaines étapes
        elif is_advice_query:
            target = f"pour **{eff_client}**" if eff_client else "pour votre prospect"
            dialogue_text = (
                f"Voici la marche à suivre conseillée par l'**Agent Stratégie** {target} :\n\n"
                f"1. **Définir la zone et l'annonceur** : préciser le point de vente et les axes routiers stratégiques (N4, E411, N25...).\n"
                f"2. **Sélectionner les faces clés** : retenir 3 à 5 faces complémentaires (axes entrants/sortants sans doublon).\n"
                f"3. **Éditer le Plan Média PDF** : télécharger la proposition officielle avec la carte d'implantation et le bon de réservation.\n\n"
                f"Voulez-vous qu'on commence par cibler une commune ou vérifier des disponibilités précises ?"
            )

        # Cas 5 : Questions techniques (format, bâche, délais)
        elif is_tech_query:
            dialogue_text = (
                "Voici les spécifications techniques certifiées M Move :\n\n"
                "• **Format d'affiche :** Bâche PVC tendue haute résistance **390 × 200 cm**.\n"
                "• **Orientation des faces :**\n"
                "  - **Face IN :** sens entrant vers le centre-ville / pôle d'activité (flux pendulaire du matin).\n"
                "  - **Face OUT :** sens sortant vers les axes périphériques (flux de retour du soir).\n"
                "• **Délais d'impression & BAT :** Fichiers HD (300 DPI à l'échelle ou vectoriel) à fournir **10 jours ouvrés** avant la date de début de campagne pour garantir la pose à date."
            )

        # Cas 6 : Salutations et politesse
        elif is_greeting:
            dialogue_text = (
                "Bonjour ! Je suis le **Coordinateur M Move Conseil**.\n\n"
                "Je pilote nos agents spécialisés (Inventaire, Stratégie et Chalandise) pour vous aider à concevoir "
                "les meilleures campagnes d'affichage 8m² pour vos annonceurs.\n\n"
                "Sur quel dossier ou quelle recherche travaillons-nous aujourd'hui ?"
            )

        # Cas 7 : Dialogue généraliste
        else:
            client_mention = f"concernant **{eff_client}**" if eff_client else "pour votre prospection"
            dialogue_text = (
                f"Je prends bien en compte votre remarque {client_mention}.\n\n"
                f"Notre équipe d'agents (Inventaire, Client et Stratégie) est prête à ajuster la proposition.\n"
                f"👉 Que souhaitez-vous faire : filtrer les disponibilités sur une zone précise, ajuster le nombre de faces, ou générer le Plan Média ?"
            )

        timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
        timing["total_ms"] = round((time.time() - start_total) * 1000, 1)

        return {
            "text": dialogue_text,
            "panels": [],  # Ne jamais dupliquer ni écraser les panneaux du listing
            "extracted": extracted,
            "timing": timing,
            "campaign_plan": active_plan,
            "client_name": eff_client,
            "salesperson": current_sp,
            "plan_pdf_url": active_plan.get("pdf_url") if active_plan else None,
            "dossier_id": None,
            "agent_name": "Coordinateur M Move Conseil",
            "badge": "💬 Coordinateur"
        }
