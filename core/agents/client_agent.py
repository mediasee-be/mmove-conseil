"""
M Move Client Agent (Agent Intelligence Client & Chalandise)
Spécialiste de l'analyse du client, de ses points de vente et de sa zone d'attractivité commerciale.
Identifie l'implantation, la zone de chalandise (10-15 km) et les flux routiers stratégiques.
"""

import os
import re
import csv
from typing import Dict, Any, List, Optional, Tuple
from core.agents.engine_tools import MmoveEngineTools, haversine_distance, normalize_text

class ClientAgent:
    """Agent spécialisé dans l'analyse de chalandise et le profilage des entreprises clientes."""

    # Référentiel des types d'établissements courants
    SECTOR_MAPPING = {
        "marjorie toma": ("Immobilier & Habitat", "Agence Immobilière (Les Maisons de Marjorie Toma)", "home"),
        "toma": ("Immobilier & Habitat", "Agence Immobilière", "home"),
        "immo": ("Immobilier & Habitat", "Agence Immobilière", "home"),
        "immobili": ("Immobilier & Habitat", "Agence Immobilière", "home"),
        "notaire": ("Services Juridiques & Notariat", "Étude Notariale", "scale"),
        "avocat": ("Services Juridiques & Droit", "Cabinet d'Avocats", "scale"),
        "optique": ("Santé & Optique", "Opticien & Lunetterie", "eye"),
        "opticien": ("Santé & Optique", "Opticien & Lunetterie", "eye"),
        "cuisine": ("Habitat & Décoration", "Cuisiniste & Aménagement", "store"),
        "cuisiniste": ("Habitat & Décoration", "Cuisiniste & Aménagement", "store"),
        "piscine": ("Habitat & Extérieurs", "Pisciniste & Équipements", "water"),
        "waterair": ("Habitat & Extérieurs", "Pisciniste & Équipements", "water"),
        "servipools": ("Habitat & Extérieurs", "Pisciniste & Équipements", "water"),
        "easyhome": ("Construction & Habitat", "Constructeur de maisons individuelles", "home"),
        "continentis": ("Transport & Logistique", "Services logistiques & stockage", "truck"),
        "dema": ("Bricolage & Équipement", "Magasin outillage & bricolage", "cart"),
        "carbelle": ("Automobile & Pneus", "Centre de montage & entretien", "car"),
        "plopsa": ("Loisirs & Tourisme", "Parc d'attractions & loisirs", "sport"),
        "grottes de han": ("Loisirs & Tourisme", "Site touristique naturel", "sport"),
        "brico": ("Bricolage & Jardin", "Magasin de bricolage", "cart"),
        "hubo": ("Bricolage & Jardin", "Magasin de bricolage", "cart"),
        "gamma": ("Bricolage & Jardin", "Magasin de bricolage", "cart"),
        "clinique": ("Santé & Médical", "Établissement hospitalier", "hospital"),
        "hopital": ("Santé & Médical", "Établissement hospitalier", "hospital"),
        "chwapi": ("Santé & Médical", "Pôle hospitalier", "hospital"),
        "auto": ("Automobile & Mobilité", "Concession automobile", "car"),
        "garage": ("Automobile & Mobilité", "Concession automobile", "car"),
        "bmw": ("Automobile & Mobilité", "Concession automobile", "car"),
        "volkswagen": ("Automobile & Mobilité", "Concession automobile", "car"),
        "toyota": ("Automobile & Mobilité", "Concession automobile", "car"),
        "declerc": ("Automobile & Mobilité", "Groupe de concessions", "car"),
        "greenrobot": ("Robotique & Énergie", "Solutions technologiques", "store"),
        "supermarche": ("Grande Distribution", "Supermarché & Drive", "cart"),
        "delhaize": ("Grande Distribution", "Supermarché", "cart"),
        "carrefour": ("Grande Distribution", "Hypermarché", "cart"),
        "colruyt": ("Grande Distribution", "Supermarché", "cart"),
        "fitness": ("Sport & Loisirs", "Club de fitness", "sport"),
        "basic-fit": ("Sport & Loisirs", "Club de fitness", "sport"),
        "promo-sport": ("Sport & Loisirs", "Centres aquatiques & sport", "sport"),
        "ecole": ("Éducation & Formation", "Établissement scolaire", "store"),
        "resto": ("Horeca & Restauration", "Restaurant / Brasserie", "store"),
    }

    def __init__(self, engine: MmoveEngineTools):
        self.engine = engine

    def get_client_history(self, client_name: str) -> Optional[Dict[str, Any]]:
        """Recherche dans le cache des réservations pour retrouver l'historique d'un client."""
        if not client_name or len(client_name.strip()) < 3:
            return None

        target = normalize_text(client_name.strip())
        cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "reservations_cache.csv")
        if not os.path.exists(cache_path):
            return None

        matches = []
        try:
            with open(cache_path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = row.get("Client", "")
                    if c and target in normalize_text(c):
                        matches.append(row)
        except Exception:
            return None

        if not matches:
            return None

        # Analyser les remorques réservées
        panel_counts: Dict[str, int] = {}
        periods = set()
        for m in matches:
            pid = str(m.get("Remorque", "")).strip()
            if pid:
                panel_counts[pid] = panel_counts.get(pid, 0) + 1
            if m.get("Période"):
                periods.add(m.get("Période"))

        # Trouver les remorques et axes correspondants
        preferred_panels = []
        preferred_locations = set()
        preferred_axes = set()

        sorted_pids = sorted(panel_counts.keys(), key=lambda p: -panel_counts[p])
        for pid in sorted_pids:
            t = self.engine.trailers.get(str(pid))
            if t:
                preferred_panels.append(t)
                if t.get("ville"):
                    preferred_locations.add(t.get("ville"))
                ax = t.get("code_route") or t.get("axe_routier")
                if ax:
                    preferred_axes.add(ax)

        return {
            "client_name": client_name,
            "total_reservations": len(matches),
            "preferred_panels": preferred_panels,
            "preferred_panel_ids": sorted_pids,
            "preferred_locations": list(preferred_locations),
            "preferred_axes": list(preferred_axes),
            "periods": sorted(list(periods))
        }

    def _extract_city_and_brand(self, text: str) -> Tuple[str, Optional[str]]:
        """Extrait la marque commerciale et la ville depuis une chaîne comme 'Brico Ciney'."""
        clean = text.strip()
        lower = clean.lower()

        # Liste de villes wallonnes majeures
        known_cities = [
            "namur", "ciney", "dinant", "ottignies", "wavre", "gembloux", "nivelles",
            "louvain-la-neuve", "lln", "marche", "andenne", "éghezée", "eghezee",
            "perwez", "jodoigne", "huy", "verviers", "liège", "liege", "charleroi",
            "mons", "tournai", "waterloo", "braine-l'alleud", "hamois", "rochefort"
        ]

        found_city = None
        for c in known_cities:
            # Chercher le mot de la ville
            pattern = r"\b" + re.escape(c) + r"\b"
            if re.search(pattern, lower):
                found_city = "Éghezée" if "eghez" in c else ("Louvain-la-Neuve" if c in ["lln", "louvain-la-neuve"] else c.title())
                # Enlever la ville du nom pour trouver la marque
                clean = re.sub(pattern, "", clean, flags=re.IGNORECASE).strip(" -:,")
                break

        brand = clean.title() if clean else text.title()
        return brand, found_city

    def analyze_client(
        self,
        client_name: str,
        raw_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyse en profondeur le client :
        - Géocodage précis du point d'implantation.
        - Identification du secteur d'activité.
        - Détermination des axes majeurs de transit vers ce point.
        - Calcul des communes de la zone de chalandise (10-15 km).
        - Recommandations stratégiques d'affichage.
        """
        combined = f"{client_name} {raw_message or ''}"
        brand, city = self._extract_city_and_brand(client_name)

        # 1. Typage d'établissement
        est_type = "Commerce & Services"
        sector_name = "Activités Commerciales"
        icon_type = "store"

        norm_combined = normalize_text(combined)
        for key, (sec, est, ic) in self.SECTOR_MAPPING.items():
            if key in norm_combined:
                sector_name = sec
                est_type = est
                icon_type = ic
                break

        # Vérification préalable dans l'historique M Move
        history = self.get_client_history(client_name)
        preferred_locations = []
        preferred_axes = []
        if history:
            preferred_locations = history.get("preferred_locations", [])
            preferred_axes = history.get("preferred_axes", [])
            if preferred_locations and (not city or city == "Wallonie"):
                city = " / ".join(preferred_locations[:3])

        # 2. Géocodage
        lat, lng = 50.4674, 4.8720  # Namur par défaut
        if history and history.get("preferred_panels"):
            lats = [p["lat"] for p in history["preferred_panels"] if p.get("lat")]
            lngs = [p["lng"] for p in history["preferred_panels"] if p.get("lng")]
            if lats and lngs:
                lat = sum(lats) / len(lats)
                lng = sum(lngs) / len(lngs)
        else:
            geocode_query = f"{brand} {city or ''}, Belgique" if city else f"{client_name}, Belgique"
            coords = self.engine.geocode(geocode_query)
            if not coords and city:
                coords = self.engine.geocode(f"{city}, Belgique")
            if coords:
                lat, lng = coords

        city = city or "Wallonie"

        # 3. Détection des axes majeurs et remorques proches
        nearby_trailers = []
        for t in self.engine.trailers.values():
            if t.get("lat") and t.get("lng"):
                d = haversine_distance(lat, lng, t["lat"], t["lng"])
                if d is not None and d <= 15.0:
                    nearby_trailers.append((d, t))

        nearby_trailers.sort(key=lambda x: x[0])

        # Axes majeurs identifiés
        seen_axes = []
        if preferred_axes:
            for ax in preferred_axes:
                m = re.search(r"\b([A-Z]\d+)\b", ax)
                code = m.group(1) if m else ax
                if code and code not in seen_axes:
                    seen_axes.append(code)
                if len(seen_axes) >= 4:
                    break

        if len(seen_axes) < 3:
            for _, t in nearby_trailers:
                ax = t.get("code_route") or t.get("axe_routier") or ""
                m = re.search(r"\b([A-Z]\d+)\b", ax)
                code = m.group(1) if m else ax
                if code and code not in seen_axes:
                    seen_axes.append(code)
                if len(seen_axes) >= 4:
                    break

        # Communes du bassin de chalandise (limitrophes <= 15 km)
        catchment_cities_set = set(preferred_locations)
        for d, t in nearby_trailers:
            v = t.get("ville", "").title()
            if v and v != city:
                catchment_cities_set.add(v)
        catchment_cities = sorted(list(catchment_cities_set))[:5]

        # Résumé textuel
        axes_str = ", ".join(seen_axes) if seen_axes else "Axes routiers locaux"
        catchment_str = ", ".join(catchment_cities) if catchment_cities else "Périphérie immédiate"

        if history:
            total_res = history.get("total_reservations", 0)
            locs_str = ", ".join(preferred_locations) if preferred_locations else city
            summary_text = (
                f"🏢 **Client Historique : {brand}**\n\n"
                f"• **Activité :** {est_type} ({sector_name})\n"
                f"• **Historique M Move :** {total_res} réservations sur le réseau\n"
                f"• **Bassin d'activité naturel :** {locs_str}\n"
                f"• **Axes prioritaires :** {axes_str}\n"
                f"• **Dispositif conseillé :** Présence continue sur les carrefours d'entrée de ville et voies d'accès au pôle d'activité pour capter les flux pendulaires."
            )
        else:
            summary_text = (
                f"🏢 **Analyse Client : {brand} à {city}**\n\n"
                f"• **Activité :** {est_type} ({sector_name})\n"
                f"• **Axes d'accès prioritaires :** {axes_str}\n"
                f"• **Bassin de chalandise naturel (10-15 km) :** {city}, {catchment_str}\n"
                f"• **Dispositif conseillé :** Couverture frontale sur les ronds-points et carrefours d'entrée de ville pour capter les flux pendulaires entrants."
            )

        return {
            "client_name": brand,
            "full_name": client_name,
            "establishment_type": est_type,
            "sector": sector_name,
            "city": city,
            "lat": lat,
            "lng": lng,
            "primary_axes": seen_axes,
            "catchment_cities": catchment_cities,
            "summary_text": summary_text,
            "history": history,
            "marker": {
                "lat": lat,
                "lng": lng,
                "label": f"{brand} ({city})",
                "icon": icon_type
            },
            "recommendations": [
                f"Cibler les remorques d'accès sur {axes_str}",
                f"Élargir aux flux pendulaires venant de {catchment_str}"
            ],
            "agent_name": "Agent Intelligence Client & Chalandise",
            "badge": "🔵 Client"
        }
