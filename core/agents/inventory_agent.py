"""
M Move Inventory Agent (Agent Inventaire & Disponibilités)
Spécialiste exclusif de la vérité terrain, de l'état des remorques et des disponibilités.
Ne propose pas de plan média imposé ni de devis contractuel :
renvoie l'intégralité des remorques libres pour permettre la sélection client.
"""

import os
import re
from typing import Dict, Any, List, Optional
from core.agents.engine_tools import MmoveEngineTools, format_period_human, get_friendly_dispo_label

class InventoryAgent:
    """Agent spécialisé dans la recherche d'inventaire brut et des disponibilités réelles."""

    def __init__(self, engine: MmoveEngineTools, pdf_service: Any, sales_agent: Any):
        self.engine = engine
        self.pdf_service = pdf_service
        self.sales_agent = sales_agent

    def handle_availability_query(
        self,
        user_message: str,
        extracted_info: Dict[str, Any],
        locations: List[str],
        target_periods: List[str],
        is_explicit_expand: bool = False,
        salesperson: Optional[Dict[str, Any]] = None,
        current_radius_km: float = 5.0
    ) -> Dict[str, Any]:
        """
        Traite une requête de disponibilité ou d'inventaire brut de bout en bout :
        1. Recherche et filtrage géographique avec cercle de recherche évolutif (+5 km à chaque élargissement).
        2. Détection proactive des panneaux dans l'anneau suivant (+5 km) pour proposer l'élargissement.
        3. Génération du catalogue PDF de disponibilités interactif.
        4. Synthèse textuelle claire et engageante pour la sélection client.
        """
        target_loc_name = locations[0].title() if locations else "Wallonie"
        search_radius_km = float(current_radius_km) if current_radius_km > 0 else 5.0

        # Résolution des coordonnées du centre de recherche pour le cercle cartographique
        center_coords = self.engine.geocode(locations[0]) if locations else None
        center_lat, center_lng = center_coords if center_coords else (None, None)

        # 1. Recherche via le moteur avec le rayon actuel
        raw_candidates = self.engine.search_and_rank(
            locations=locations,
            axes=extracted_info.get("axes"),
            target_periods=target_periods,
            max_distance_km=search_radius_km,
            top_k=50,
            require_availability=True,
            sort_by_dispo=True
        )

        # 2. Filtrage : distinction Lieu Même vs Périphérie
        direct_matches = [c for c in raw_candidates if c.get("is_direct_match")]
        peripheral_matches = [c for c in raw_candidates if not c.get("is_direct_match")]

        can_expand_zone = False
        peripheral_count = 0
        peripheral_cities: List[str] = []
        next_radius_km = search_radius_km + 5.0

        if not is_explicit_expand:
            # Recherche initiale : si des panneaux sont au lieu même, les privilégier d'abord
            if direct_matches:
                candidate_panels = direct_matches
                if peripheral_matches:
                    # Des panneaux existent déjà dans le rayon de base
                    can_expand_zone = True
                    peripheral_count = len(peripheral_matches)
                    peripheral_cities = sorted(list({p.get("ville", "").title() for p in peripheral_matches if p.get("ville")}))
                    next_radius_km = search_radius_km
            else:
                candidate_panels = raw_candidates

            # Si aucun panneau périphérique dans le rayon initial, sonder l'anneau suivant (+5 km)
            if not can_expand_zone and locations:
                raw_next = self.engine.search_and_rank(
                    locations=locations,
                    axes=extracted_info.get("axes"),
                    target_periods=target_periods,
                    max_distance_km=search_radius_km + 5.0,
                    top_k=50,
                    require_availability=True,
                    sort_by_dispo=True
                )
                curr_ids = {p.get("id") for p in candidate_panels}
                next_ring = [p for p in raw_next if p.get("id") not in curr_ids and not p.get("is_direct_match")]
                if next_ring:
                    can_expand_zone = True
                    peripheral_count = len(next_ring)
                    peripheral_cities = sorted(list({p.get("ville", "").title() for p in next_ring if p.get("ville")}))
                    next_radius_km = search_radius_km + 5.0
        else:
            # Élargissement explicite demandé : intégrer tous les panneaux jusqu'au rayon élargi
            candidate_panels = raw_candidates

            # Sonder l'anneau suivant (+5 km) pour permettre un élargissement supplémentaire
            if locations:
                raw_next = self.engine.search_and_rank(
                    locations=locations,
                    axes=extracted_info.get("axes"),
                    target_periods=target_periods,
                    max_distance_km=search_radius_km + 5.0,
                    top_k=50,
                    require_availability=True,
                    sort_by_dispo=True
                )
                curr_ids = {p.get("id") for p in candidate_panels}
                next_ring = [p for p in raw_next if p.get("id") not in curr_ids and not p.get("is_direct_match")]
                if next_ring:
                    can_expand_zone = True
                    peripheral_count = len(next_ring)
                    peripheral_cities = sorted(list({p.get("ville", "").title() for p in next_ring if p.get("ville")}))
                    next_radius_km = search_radius_km + 5.0

        # Données du cercle cartographique
        search_circle = None
        if center_lat is not None and center_lng is not None:
            search_circle = {
                "lat": center_lat,
                "lng": center_lng,
                "radius_km": round(search_radius_km, 1),
                "location": target_loc_name
            }

        # 3. Génération du Catalogue PDF des disponibilités
        pdf_url = ""
        client_disp = extracted_info.get("client_name") or "Partenaire"
        try:
            pdf_path = self.pdf_service.generate_availability_pdf(
                panels=candidate_panels,
                location_name=target_loc_name,
                periods=target_periods,
                client_name=client_disp,
                salesperson=salesperson
            )
            pdf_url = f"/api/download-availability-pdf?file={os.path.basename(pdf_path)}"
        except Exception as e:
            print(f"[InventoryAgent] Erreur génération PDF Catalogue Dispos : {e}")

        # 4. Rédaction de la réponse
        period_str = ", ".join(format_period_human(p) for p in target_periods) if target_periods else "Période à préciser"
        has_period = bool(target_periods)

        lines = []
        if candidate_panels:
            count = len(candidate_panels)
            if is_explicit_expand:
                lines.append(f"📍 **{count} panneau{'x' if count > 1 else ''} 8m² disponible{'s' if count > 1 else ''} dans un rayon élargi à {int(search_radius_km)} km autour de {target_loc_name} ({period_str})** :\n")
            elif has_period:
                lines.append(f"📍 **{count} panneau{'x' if count > 1 else ''} 8m² disponible{'s' if count > 1 else ''} à {target_loc_name} ({period_str})** :\n")
            else:
                lines.append(f"📍 **{count} panneau{'x' if count > 1 else ''} 8m² répertorié{'s' if count > 1 else ''} à {target_loc_name}** :\n")

            for idx, p in enumerate(candidate_panels, start=1):
                pid = p.get("id")
                v = p.get("ville", "").title()
                loc = p.get("localisation", "")
                axe_code = p.get("code_route") or p.get("axe_routier") or ""
                axe_display = f"{axe_code} " if axe_code else ""
                direction = p.get("direction_in") or p.get("direction_out") or p.get("direction") or "Double sens"
                dist_km = p.get("distance_km")
                dist_str = f" ({dist_km:.1f} km)" if (dist_km is not None and dist_km > 0.05 and not p.get("is_direct_match")) else ""
                freq = f"{p.get('frequentation_jour', 0):,}".replace(",", " ")

                if has_period:
                    # Ne pas répéter le mois partout quand il est déjà en tête de message
                    lines.append(
                        f"**{idx}.** [#{pid} {v} ({loc}) ↗️]({p.get('lien')}) — {axe_display}dir. {direction}{dist_str} · **{freq} v/j**"
                    )
                else:
                    dispo_str = p.get("prochaine_dispo_label") or p.get("prochaine_dispo_human") or format_period_human(p.get("prochaine_dispo", ""))
                    dispo_str = re.sub(r"\s*\(Face[^\)]*\)", "", str(dispo_str), flags=re.IGNORECASE).strip()
                    lines.append(
                        f"**{idx}.** [#{pid} {v} ({loc}) ↗️]({p.get('lien')}) — {axe_display}dir. {direction}{dist_str} · **{freq} v/j** · *{dispo_str}*"
                    )

            if can_expand_zone and peripheral_cities:
                cities_display = ", ".join(peripheral_cities)
                lines.append(
                    f"\n💡 *Élargissement possible : +{peripheral_count} panneau{'x' if peripheral_count > 1 else ''} disponible{'s' if peripheral_count > 1 else ''} dans les communes voisines (rayon {int(next_radius_km)} km : {cities_display}). Cliquez sur le bouton « Élargir la zone (+5 km) » ou dites « élargis la zone » pour les ajouter au listing.*"
                )

            if pdf_url:
                lines.append(
                    f"\n📄 **[Télécharger le Catalogue des Disponibilités en PDF]({pdf_url})**"
                )

            lines.append(
                "\n*Vous pouvez cocher les faces qui vous intéressent directement dans le PDF interactif ou avec le bouton **[+ Retenir]** ci-contre, ou m'indiquer directement vos choix dans le chat pour monter votre Plan Média officiel.*"
            )
        else:
            lines.append(f"Aucun panneau disponible n'a été trouvé à **{target_loc_name}** pour la période indiquée ({period_str}).")
            if target_periods:
                lines.append(f"Souhaitez-vous vérifier les disponibilités sur un mois adjacent ou élargir le rayon à {int(next_radius_km)} km ?")

        return {
            "text": "\n".join(lines),
            "panels": candidate_panels,
            "availability_pdf_url": pdf_url,
            "can_expand_zone": can_expand_zone,
            "peripheral_count": peripheral_count,
            "peripheral_cities": peripheral_cities,
            "search_circle": search_circle,
            "current_radius_km": round(search_radius_km, 1),
            "next_radius_km": round(next_radius_km, 1),
            "agent_name": "Agent Inventaire & Disponibilités",
            "badge": "🟢 Inventaire"
        }
