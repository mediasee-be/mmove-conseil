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
        self.last_campaign_plan: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_name": self.client_name,
            "locations": list(self.locations),
            "axes": list(self.axes),
            "target_periods": list(self.target_periods),
            "count_requested": self.count_requested,
            "pinned_panel_ids": list(self.pinned_panel_ids),
            "excluded_panel_ids": list(self.excluded_panel_ids),
            "has_plan": self.last_campaign_plan is not None
        }

    def reset(self):
        self.client_name = None
        self.locations = []
        self.axes = []
        self.target_periods = []
        self.count_requested = 5
        self.pinned_panel_ids = []
        self.excluded_panel_ids = []
        self.last_campaign_plan = None

class CoordinatorAgent:
    """Orchestrateur multi-agents pour le conseil et la recherche de remorques Mmove."""

    def __init__(self, api_key: Optional[str] = None, auto_sync: bool = True):
        self.engine = MmoveEngineTools()
        self.extractor = ExtractorAgent(api_key=api_key)
        self.sales = SalesAgent(api_key=api_key)
        self.sync = SyncManager(engine_tools=self.engine)
        self.map_service = MapGeneratorService()
        self.pdf_service = CampaignPdfService()
        from core.agents.salesperson_service import SalespersonService
        from core.agents.dossier_service import DossierService
        self.salesperson_service = SalespersonService()
        self.dossier_service = DossierService(salesperson_service=self.salesperson_service)
        self.current_client_name: Optional[str] = None
        self.last_campaign_plan: Optional[Dict[str, Any]] = None
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
                if parsed.get("intent") == "campaign_proposal" and parsed.get("target_periods"):
                    if parsed.get("locations"):
                        ctx.locations = list(parsed["locations"])
                    ctx.target_periods = list(parsed["target_periods"])
                    if parsed.get("count_requested"):
                        ctx.count_requested = parsed["count_requested"]
                    if parsed.get("client_name"):
                        ctx.client_name = parsed["client_name"]
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

        # Prise en compte du commercial connecté
        current_sp = self.salesperson_service.get(salesperson_id)

        # Prise en compte du nom de client s'il est spécifié en paramètre ou dans l'extraction
        if client_name and client_name.strip():
            self.current_client_name = client_name.strip()
            ctx.client_name = client_name.strip()
        if extracted.get("client_name"):
            self.current_client_name = extracted["client_name"]
            ctx.client_name = extracted["client_name"]

        # Traitement spécifique : Définition ou mise à jour directe du client
        if intent == "set_client_name" or (extracted.get("client_name") and not extracted.get("locations") and not extracted.get("axes") and not extracted.get("target_periods") and not extracted.get("target_id") and intent not in ["check_availability", "creative_advice", "technical_specs", "refine_campaign"]):
            client_name_val = extracted.get("client_name") or self.current_client_name or "Client"
            self.current_client_name = client_name_val
            ctx.client_name = client_name_val
            target_plan = ctx.last_campaign_plan or self.last_campaign_plan
            if target_plan:
                pdf_path = self.pdf_service.generate_campaign_pdf(target_plan, client_name=client_name_val, salesperson=current_sp)
                target_plan["pdf_url"] = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
                target_plan["client_name"] = client_name_val
                first_month_panels = target_plan["months"][0]["panels"] if target_plan.get("months") else []
                dossier = self.dossier_service.save_dossier(
                    salesperson_id=current_sp.get("initials", "DR"),
                    client_name=client_name_val,
                    campaign_plan=target_plan,
                    candidate_panels=first_month_panels,
                    user_message=user_message
                )
                target_plan["dossier_id"] = dossier.get("id")
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
                text = (
                    f"Le Plan Média a bien été personnalisé pour votre client **{client_name_val}** ! 📄\n\n"
                    f"Le document PDF complet intégrant les cartes d'implantation HD et le maillage stratégique a été mis à jour avec la date d'émission du jour.\n\n"
                    f"Vous pouvez le télécharger directement ci-dessous."
                )
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                return {
                    "text": text,
                    "panels": frontend_panels,
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": target_plan,
                    "client_name": self.current_client_name
                }
            else:
                timing["total_ms"] = round((time.time() - start_total) * 1000, 1)
                return {
                    "text": f"Le nom de votre client (**{client_name_val}**) a bien été mémorisé ! Toutes les prochaines propositions et les PDF générés lui seront personnalisés.",
                    "panels": [],
                    "extracted": extracted,
                    "timing": timing,
                    "campaign_plan": None,
                    "client_name": self.current_client_name
                }

        # 2. CONTINUITÉ DE CONVERSATION : Gestion des raffinements de campagne (refine_campaign)
        refinement_action = extracted.get("refinement_action")

        # Cas A : Élargissement géographique vers une nouvelle ville / axe (ex: "élargis vers wavre")
        if intent == "refine_campaign" and refinement_action == "expand_zone":
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

            first_pid = ctx.pinned_panel_ids[-1] if ctx.pinned_panel_ids else None
            trailer = self.engine.get_trailer_by_id(first_pid) if first_pid else None
            if trailer:
                avail_info = self.engine.check_period_availability(trailer, ctx.target_periods)
                photo = trailer.get("photo_in") or "https://remorquepublicitaire.be/wp-content/uploads/2021/07/logo-mmove.png"
                candidate_panels = [{
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
                    "prochaine_dispo_human": format_period_human(trailer.get("prochaine_dispo")),
                    "prochaine_dispo_label": get_friendly_dispo_label(trailer),
                    "availability": avail_info,
                    "photo_url": photo,
                    "is_direct_match": True,
                    "total_score": 100.0
                }]
                dir_str = trailer.get("direction_out") or trailer.get("direction_in") or "Double sens"
                freq_str = f"{trailer.get('frequentation_jour', 0):,}".replace(",", " ")
                periods_str = ", ".join([format_period_human(p) for p in ctx.target_periods]) if ctx.target_periods else "votre campagne"
                all_pinned_str = ", ".join([f"#{p}" for p in ctx.pinned_panel_ids])
                locs_str = " & ".join(ctx.locations) if ctx.locations else trailer['ville']

                final_text = (
                    f"✅ L'emplacement **#{trailer['id']} ({trailer['ville']} - {trailer['localisation']})** a bien été validé et intégré à votre sélection de campagne !\n\n"
                    f"• **Axe & Direction :** {trailer.get('axe_routier', '')} dir. {dir_str} · **{freq_str} véh./jour**\n"
                    f"• **Statut :** Garanti et prioritaire dans le plan multi-mois ({periods_str})\n"
                    f"• **Panneaux verrouillés :** {all_pinned_str} ({locs_str})\n\n"
                    f"👉 Dites simplement **« refais ma sélection »** pour actualiser le plan média complet (5 faces/mois intégrant la {trailer['id']}) et mettre à jour votre document PDF !"
                )
            else:
                final_text = f"Le panneau a bien été validé et intégré à vos priorités. Dites **« refais ma sélection »** pour actualiser votre plan média."

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

            # Planification de campagne multi-mois avec rotation dynamique, axes distincts et panneaux épinglés
            campaign_plan = self.engine.plan_multi_month_campaign(
                locations=locations,
                target_periods=target_periods,
                count_per_month=count_req,
                axes=extracted.get("axes") or ctx.axes,
                pinned_panel_ids=pinned_ids,
                excluded_panel_ids=excluded_ids
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

            # Sauvegarde automatique du dossier commercial
            dossier = self.dossier_service.save_dossier(
                salesperson_id=current_sp.get("initials", "DR"),
                client_name=eff_client,
                campaign_plan=campaign_plan,
                candidate_panels=candidate_panels,
                user_message=user_message
            )
            campaign_plan["dossier_id"] = dossier.get("id")
            self.last_campaign_plan = campaign_plan
            ctx.last_campaign_plan = campaign_plan

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
            conversation_history=conversation_history,
            campaign_plan=campaign_plan
        )
        timing["synthesis_ms"] = round((time.time() - t0) * 1000, 1)
        frontend_panels = self._build_frontend_panels(candidate_panels, user_message)
        return {
            "text": final_text,
            "panels": frontend_panels,
            "extracted": extracted,
            "timing": timing,
            "campaign_plan": campaign_plan,
            "client_name": self.current_client_name,
            "salesperson": current_sp,
            "dossier_id": campaign_plan.get("dossier_id") if campaign_plan else None
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
                "score": p.get("total_score"),
                "lat": p.get("lat"),
                "lng": p.get("lng")
            })
        return frontend_panels
