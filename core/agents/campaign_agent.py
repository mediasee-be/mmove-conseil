"""
M Move Campaign Agent (Agent Plan Média & Stratégie)
Architecte des campagnes publicitaires multi-mois et constructeur incrémental.
RÈGLE D'OR :
Toute interaction dans le chat fait évoluer le plan média en continu (ajout de faces,
retrait, remplacement, rééquilibrage) sans jamais repartir de zéro.
"""

import os
import re
from typing import Dict, Any, List, Optional
from core.agents.engine_tools import MmoveEngineTools, format_period_human
from core.agents.map_service import MapGeneratorService
from core.agents.pdf_service import CampaignPdfService
from core.agents.sales_agent import SalesAgent

class CampaignAgent:
    """Agent spécialisé dans la conception, l'évolution incrémentale et le chiffrage des plans média multi-mois."""

    def __init__(
        self,
        engine: MmoveEngineTools,
        pdf_service: CampaignPdfService,
        map_service: MapGeneratorService,
        sales_agent: SalesAgent
    ):
        self.engine = engine
        self.pdf_service = pdf_service
        self.map_service = map_service
        self.sales = sales_agent

    def create_campaign(
        self,
        locations: List[str],
        target_periods: List[str],
        count_per_month: int = 5,
        client_name: Optional[str] = None,
        salesperson: Optional[Dict[str, Any]] = None,
        pinned_panel_ids: Optional[List[str]] = None,
        excluded_panel_ids: Optional[List[str]] = None,
        axes: Optional[List[str]] = None,
        user_message: str = ""
    ) -> Dict[str, Any]:
        """Crée une nouvelle proposition de campagne multi-mois avec rotation d'axes et livrables HD."""
        campaign_plan = self.engine.plan_multi_month_campaign(
            locations=locations,
            target_periods=target_periods,
            count_per_month=count_per_month,
            max_distance_km=30.0,
            axes=axes,
            pinned_panel_ids=pinned_panel_ids,
            excluded_panel_ids=excluded_panel_ids
        )

        client_disp = client_name or "Partenaire M Move"
        campaign_plan["client_name"] = client_disp
        campaign_plan["salesperson"] = salesperson or {}

        # Génération des cartes HD mensuelles
        for m_plan in campaign_plan.get("months", []):
            try:
                m_img = self.map_service.generate_campaign_map(
                    panels=m_plan.get("panels", []),
                    period_str=m_plan.get("period", "campaign"),
                    width=1300,
                    height=880
                )
                m_plan["map_url"] = f"/api/map/{os.path.basename(m_img)}"
                m_plan["map_hd_url"] = m_plan["map_url"]
            except Exception as e:
                print(f"[CampaignAgent] Erreur carte HD mois {m_plan.get('period')} : {e}")

        # Génération du Plan Média PDF officiel
        pdf_url = ""
        try:
            pdf_path = self.pdf_service.generate_campaign_pdf(
                campaign_plan=campaign_plan,
                client_name=client_disp,
                salesperson=salesperson
            )
            pdf_url = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
            campaign_plan["pdf_url"] = pdf_url
        except Exception as e:
            print(f"[CampaignAgent] Erreur génération PDF Plan Média : {e}")

        first_panels = campaign_plan["months"][0]["panels"] if campaign_plan.get("months") else []

        # Pitch commercial expert
        text_resp = self.sales.generate_pitch(
            user_message=user_message,
            extracted_info={
                "intent": "campaign_proposal",
                "locations": locations,
                "target_periods": target_periods,
                "count_requested": count_per_month,
                "client_name": client_disp
            },
            candidate_panels=first_panels,
            campaign_plan=campaign_plan
        )

        return {
            "text": text_resp,
            "campaign_plan": campaign_plan,
            "panels": first_panels,
            "pdf_url": pdf_url,
            "agent_name": "Agent Plan Média & Stratégie",
            "badge": "🟠 Plan Média"
        }

    def add_face_to_campaign(
        self,
        campaign_plan: Dict[str, Any],
        location: Optional[str] = None,
        delta_count: int = 1,
        client_name: Optional[str] = None,
        salesperson: Optional[Dict[str, Any]] = None,
        active_locations: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        FAIT ÉVOLUER LE PLAN MÉDIA EN COURS :
        Conserve intactes toutes les faces existantes de chaque mois, et vient ajouter
        delta_count nouvelle(s) face(s) qualifiée(s) dans la commune ciblée.
        Le plan passe par exemple de 5 à 6 faces par mois.
        """
        months = campaign_plan.get("months", [])
        if not months:
            # Fallback création si pas de mois
            locs = [location] if location else (active_locations or ["Wallonie"])
            return self.create_campaign(locs, ["2027-01"], count_per_month=delta_count, client_name=client_name, salesperson=salesperson)

        target_loc = location or (active_locations[0] if active_locations else "Wallonie")
        client_disp = client_name or campaign_plan.get("client_name") or "Partenaire M Move"
        added_panel_details = []

        # Pour chaque mois du plan : trouver delta_count panneaux additionnels disponibles avec rotation anti-doublon consécutif
        for m_idx, m_plan in enumerate(months):
            period = m_plan.get("period")
            existing_ids = {str(p["id"]) for p in m_plan.get("panels", [])}
            prev_ids = {str(p["id"]) for p in months[m_idx - 1].get("panels", [])} if m_idx > 0 else set()

            candidates = self.engine.search_and_rank(
                locations=[target_loc] if target_loc else active_locations,
                target_periods=[period],
                max_distance_km=25.0,
                top_k=30,
                require_availability=True,
                enforce_axis_diversity=False
            )

            # Priorité 1 : candidats absents de ce mois ET absents du mois immédiatement précédent (rotation garantie)
            fresh_cands = [c for c in candidates if str(c["id"]) not in existing_ids and str(c["id"]) not in prev_ids]
            # Priorité 2 : candidats réutilisés uniquement si pénurie
            reuse_cands = [c for c in candidates if str(c["id"]) not in existing_ids and str(c["id"]) in prev_ids]

            added_for_month = []
            for c in fresh_cands:
                if len(added_for_month) >= delta_count:
                    break
                added_for_month.append(c)
                existing_ids.add(str(c["id"]))

            # Si pas assez dans la ville demandée sans doublon consécutif, chercher plus large dans le réseau disponible
            if len(added_for_month) < delta_count:
                regional_cands = self.engine.search_and_rank(
                    locations=active_locations,
                    target_periods=[period],
                    max_distance_km=35.0,
                    top_k=30,
                    require_availability=True
                )
                for c in regional_cands:
                    if str(c["id"]) not in existing_ids and str(c["id"]) not in prev_ids:
                        added_for_month.append(c)
                        existing_ids.add(str(c["id"]))
                        if len(added_for_month) >= delta_count:
                            break

            # Dernier recours absolu en cas de pénurie locale extrême
            if len(added_for_month) < delta_count:
                for c in reuse_cands:
                    if str(c["id"]) not in existing_ids:
                        added_for_month.append(c)
                        existing_ids.add(str(c["id"]))
                        if len(added_for_month) >= delta_count:
                            break

            # Ajouter aux panneaux du mois
            m_plan["panels"].extend(added_for_month)
            if added_for_month:
                added_panel_details.append((period, added_for_month))

            # Recalcul des stats du mois
            m_veh = sum(p.get("frequentation_jour", 0) for p in m_plan["panels"])
            m_ots = sum(p.get("ots_mensuel", int(p.get("frequentation_jour", 0) * 36)) for p in m_plan["panels"])
            m_plan["stats"]["count"] = len(m_plan["panels"])
            m_plan["stats"]["veh_per_day"] = m_veh
            m_plan["stats"]["ots_month"] = m_ots

        # Recalcul des métriques globales
        new_count_per_month = len(months[0]["panels"]) if months else 5
        total_faces_deployed = sum(m["stats"]["count"] for m in months)
        total_cumulative_ots = sum(m["stats"]["ots_month"] for m in months)
        avg_veh_per_day = int(sum(m["stats"]["veh_per_day"] for m in months) / max(1, len(months)))

        all_unique = set()
        for m in months:
            for p in m["panels"]:
                all_unique.add(str(p["id"]))

        campaign_plan["summary"]["faces_per_month"] = new_count_per_month
        campaign_plan["summary"]["total_faces_deployed"] = total_faces_deployed
        campaign_plan["summary"]["unique_panels_count"] = len(all_unique)
        campaign_plan["summary"]["total_cumulative_ots"] = total_cumulative_ots
        campaign_plan["summary"]["avg_veh_per_day"] = avg_veh_per_day

        # Régénération des cartes HD
        for m_plan in months:
            try:
                m_img = self.map_service.generate_campaign_map(
                    panels=m_plan.get("panels", []),
                    period_str=m_plan.get("period", "campaign"),
                    width=1300,
                    height=880
                )
                m_plan["map_url"] = f"/api/map/{os.path.basename(m_img)}"
                m_plan["map_hd_url"] = m_plan["map_url"]
            except Exception as e:
                print(f"[CampaignAgent] Erreur régénération carte HD mois {m_plan.get('period')} : {e}")

        # Régénération du Plan Média PDF officiel
        pdf_url = ""
        try:
            pdf_path = self.pdf_service.generate_campaign_pdf(
                campaign_plan=campaign_plan,
                client_name=client_disp,
                salesperson=salesperson
            )
            pdf_url = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
            campaign_plan["pdf_url"] = pdf_url
        except Exception as e:
            print(f"[CampaignAgent] Erreur régénération PDF Plan Média : {e}")

        first_panels = months[0]["panels"] if months else []

        # Construction du message valorisant
        periods_str = ", ".join(format_period_human(m["period"]) for m in months)
        added_desc_items = []
        for period, p_list in added_panel_details:
            p_strs = [f"#{p['id']} ({p.get('ville', '').title()} - {p.get('localisation', '')})" for p in p_list]
            added_desc_items.append(f"• **{format_period_human(period)}** : ajout de {', '.join(p_strs)}")

        added_desc = "\n".join(added_desc_items) if added_desc_items else f"• Ajout de {delta_count} face(s) à {target_loc.title()}"

        text = (
            f"🎯 **Dispositif mis à jour avec succès : passage à {new_count_per_month} faces par mois**\n\n"
            f"Votre campagne sur **{periods_str}** intègre désormais **{total_faces_deployed} faces au total** "
            f"(impact cumulé de **{total_cumulative_ots:,} OTS** et **{avg_veh_per_day:,} contacts/jour**).\n\n"
            f"**Nouvelles implantations intégrées au dispositif :**\n{added_desc}\n\n"
            f"Toutes vos faces existantes ont été conservées intactes. "
            f"La cartographie interactive et votre **[Plan Média PDF officiel]({pdf_url})** ont été immédiatement actualisés."
        )

        return {
            "text": text,
            "campaign_plan": campaign_plan,
            "panels": first_panels,
            "pdf_url": pdf_url,
            "agent_name": "Agent Plan Média & Stratégie",
            "badge": "🟠 Plan Média"
        }

    def remove_face_from_campaign(
        self,
        campaign_plan: Dict[str, Any],
        target_id: str,
        client_name: Optional[str] = None,
        salesperson: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Retire une face spécifique du plan média actif et met à jour les livrables."""
        target_clean = str(target_id).replace("#", "").strip()
        months = campaign_plan.get("months", [])
        removed_count = 0

        for m in months:
            orig_len = len(m["panels"])
            m["panels"] = [p for p in m["panels"] if str(p["id"]) != target_clean]
            removed_count += (orig_len - len(m["panels"]))
            m["stats"]["count"] = len(m["panels"])
            m["stats"]["veh_per_day"] = sum(p.get("frequentation_jour", 0) for p in m["panels"])
            m["stats"]["ots_month"] = sum(p.get("ots_mensuel", int(p.get("frequentation_jour", 0) * 36)) for p in m["panels"])

        new_count_per_month = len(months[0]["panels"]) if months else 0
        campaign_plan["summary"]["faces_per_month"] = new_count_per_month
        campaign_plan["summary"]["total_faces_deployed"] = sum(m["stats"]["count"] for m in months)
        campaign_plan["summary"]["total_cumulative_ots"] = sum(m["stats"]["ots_month"] for m in months)

        # Régénération des cartes et PDF
        for m_plan in months:
            try:
                m_img = self.map_service.generate_campaign_map(
                    panels=m_plan.get("panels", []),
                    period_str=m_plan.get("period", "campaign"),
                    width=1300,
                    height=880
                )
                m_plan["map_url"] = f"/api/map/{os.path.basename(m_img)}"
                m_plan["map_hd_url"] = m_plan["map_url"]
            except Exception:
                pass

        pdf_url = ""
        try:
            pdf_path = self.pdf_service.generate_campaign_pdf(campaign_plan, client_disp, salesperson)
            pdf_url = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
            campaign_plan["pdf_url"] = pdf_url
        except Exception:
            pass

        first_panels = months[0]["panels"] if months else []
        text = (
            f"✅ **Remorque #{target_clean} retirée du dispositif.**\n\n"
            f"Le plan média compte désormais **{new_count_per_month} faces par mois**. "
            f"Le document PDF et la carte ont été mis à jour."
        )

        return {
            "text": text,
            "campaign_plan": campaign_plan,
            "panels": first_panels,
            "pdf_url": pdf_url,
            "agent_name": "Agent Plan Média & Stratégie",
            "badge": "🟠 Plan Média"
        }

    def replace_face_in_campaign(
        self,
        campaign_plan: Dict[str, Any],
        old_id: str,
        new_id: Optional[str] = None,
        client_name: Optional[str] = None,
        salesperson: Optional[Dict[str, Any]] = None,
        active_locations: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Remplace une remorque par une autre remorque spécifiée ou la meilleure alternative disponible."""
        old_clean = str(old_id).replace("#", "").strip()
        months = campaign_plan.get("months", [])
        replaced_details = []

        for m in months:
            panels = m["panels"]
            p_idx = next((i for i, p in enumerate(panels) if str(p["id"]) == old_clean), None)
            if p_idx is not None:
                # Trouver le remplaçant
                replacement = None
                if new_id:
                    new_clean = str(new_id).replace("#", "").strip()
                    replacement = self.engine.get_trailer_by_id(new_clean)
                else:
                    existing_ids = {str(p["id"]) for p in panels}
                    cands = self.engine.search_and_rank(
                        locations=active_locations,
                        target_periods=[m["period"]],
                        max_distance_km=30.0,
                        top_k=20,
                        require_availability=True
                    )
                    replacement = next((c for c in cands if str(c["id"]) not in existing_ids and str(c["id"]) != old_clean), None)

                if replacement:
                    panels[p_idx] = replacement
                    replaced_details.append((m["period"], replacement))

            m["stats"]["veh_per_day"] = sum(p.get("frequentation_jour", 0) for p in m["panels"])
            m["stats"]["ots_month"] = sum(p.get("ots_mensuel", int(p.get("frequentation_jour", 0) * 36)) for p in m["panels"])

        client_disp = client_name or campaign_plan.get("client_name") or "Partenaire M Move"
        for m_plan in months:
            try:
                m_img = self.map_service.generate_campaign_map(
                    panels=m_plan.get("panels", []),
                    period_str=m_plan.get("period", "campaign"),
                    width=1300,
                    height=880
                )
                m_plan["map_url"] = f"/api/map/{os.path.basename(m_img)}"
                m_plan["map_hd_url"] = m_plan["map_url"]
            except Exception:
                pass

        pdf_url = ""
        try:
            pdf_path = self.pdf_service.generate_campaign_pdf(campaign_plan, client_disp, salesperson)
            pdf_url = f"/api/download-plan-pdf?file={os.path.basename(pdf_path)}"
            campaign_plan["pdf_url"] = pdf_url
        except Exception:
            pass

        first_panels = months[0]["panels"] if months else []
        text = f"🔄 **Remplacement effectué : la remorque #{old_clean} a été remplacée.**\nVotre Plan Média PDF officiel a été actualisé."

        return {
            "text": text,
            "campaign_plan": campaign_plan,
            "panels": first_panels,
            "pdf_url": pdf_url,
            "agent_name": "Agent Plan Média & Stratégie",
            "badge": "🟠 Plan Média"
        }

    def rebalance_campaign(
        self,
        campaign_plan: Dict[str, Any],
        locations: List[str],
        count_per_month: Optional[int] = None,
        pinned_panel_ids: Optional[List[str]] = None,
        excluded_panel_ids: Optional[List[str]] = None,
        client_name: Optional[str] = None,
        salesperson: Optional[Dict[str, Any]] = None,
        user_message: str = ""
    ) -> Dict[str, Any]:
        """Régénère le plan média en respectant TOUT le périmètre cumulé (villes, quotas et épinglages)."""
        target_periods = campaign_plan.get("periods", [])
        cnt = count_per_month or campaign_plan.get("summary", {}).get("faces_per_month", 5)

        return self.create_campaign(
            locations=locations,
            target_periods=target_periods,
            count_per_month=cnt,
            client_name=client_name,
            salesperson=salesperson,
            pinned_panel_ids=pinned_panel_ids,
            excluded_panel_ids=excluded_panel_ids,
            user_message=user_message
        )
