"""
Mmove Engine Tools
Moteur déterministe ultra-rapide (< 5ms) pour :
1. Recherche spatiale & géocodage (avec cache local)
2. Filtrage par axe routier, province et direction
3. Vérification des disponibilités 2026-2027 (IN / OUT)
4. Scoring multi-critères (Trafic + OTS + Proximité + Contexte)
5. Sélection Top-K des meilleures remorques
"""

import os
import json
import math
import re
import ssl
import unicodedata
from datetime import datetime
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

def normalize_text(text: Optional[str]) -> str:
    """Normalise un texte : minuscules, suppression des accents et espaces superflus."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "mmove_db.json")
GEOCACHE_PATH = os.path.join(BASE_DIR, "data", "geocache.json")

# Rayon moyen de la terre en km
EARTH_RADIUS_KM = 6371.0

# Coordonnées pré-enregistrées des principales villes / pôles belges pour latence zéro (0.0ms)
DEFAULT_GEO_CACHE = {
    "namur, belgique": (50.4674, 4.8720),
    "namur": (50.4674, 4.8720),
    "wavre, belgique": (50.7171, 4.6133),
    "wavre": (50.7171, 4.6133),
    "ottignies, belgique": (50.6657, 4.5683),
    "ottignies": (50.6657, 4.5683),
    "louvain-la-neuve, belgique": (50.6681, 4.6119),
    "louvain-la-neuve": (50.6681, 4.6119),
    "nivelles, belgique": (50.5977, 4.3235),
    "nivelles": (50.5977, 4.3235),
    "liège, belgique": (50.6326, 5.5797),
    "liege": (50.6326, 5.5797),
    "charleroi, belgique": (50.4108, 4.4446),
    "charleroi": (50.4108, 4.4446),
    "mons, belgique": (50.4542, 3.9567),
    "mons": (50.4542, 3.9567),
    "marche-en-famenne, belgique": (50.2268, 5.3442),
    "marche-en-famenne": (50.2268, 5.3442),
    "marche": (50.2268, 5.3442),
    "arlon, belgique": (49.6833, 5.8167),
    "arlon": (49.6833, 5.8167),
    "jodoigne, belgique": (50.7256, 4.8681),
    "jodoigne": (50.7256, 4.8681),
    "perwez, belgique": (50.6272, 4.8142),
    "perwez": (50.6272, 4.8142),
    "gembloux, belgique": (50.5606, 4.6936),
    "gembloux": (50.5606, 4.6936),
    "ciney, belgique": (50.2956, 5.1006),
    "ciney": (50.2956, 5.1006),
    "dinant, belgique": (50.2611, 4.9122),
    "dinant": (50.2611, 4.9122),
    "verviers, belgique": (50.5898, 5.8647),
    "verviers": (50.5898, 5.8647),
    "bastogne, belgique": (50.0035, 5.7184),
    "bastogne": (50.0035, 5.7184),
    "huy, belgique": (50.5189, 5.2333),
    "huy": (50.5189, 5.2333),
    "tournai, belgique": (50.6072, 3.3892),
    "tournai": (50.6072, 3.3892),
}

# Photos fallbacks vérifiées
PHOTO_FALLBACKS = {
    '108': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/108in.jpg',
    '112': 'https://remorquepublicitaire.be/wp-content/uploads/2023/06/remorque-publicitaire-incourt-vers-eghezee.jpg',
    '113': 'https://remorquepublicitaire.be/wp-content/uploads/2023/06/113-Perwez-Chaussee-de-Charleroi-jodoigne.jpeg',
    '114': 'https://remorquepublicitaire.be/wp-content/uploads/2026/01/114-in.jpg',
    '223': 'https://remorquepublicitaire.be/wp-content/uploads/2022/06/225-in.jpg',
    '225': 'https://remorquepublicitaire.be/wp-content/uploads/2022/06/225-in.jpg',
    '230': 'https://remorquepublicitaire.be/wp-content/uploads/2024/11/stavelot-in.jpg',
    '231': 'https://remorquepublicitaire.be/wp-content/uploads/2022/06/231-in.jpg',
    '319': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/319-Ciney-Achêne.jpg',
    '323': 'https://remorquepublicitaire.be/wp-content/uploads/2023/06/323-remorque-publicitare-sauveniere-vers-gembloux.jpg',
    '340': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/340-Namur-Naninne.jpg',
    '361': 'https://remorquepublicitaire.be/wp-content/uploads/2022/06/361-Lacs-de-lEau-dHeure-Silenrieux_direction_silenrieux.jpg',
    '363': 'https://remorquepublicitaire.be/wp-content/uploads/2025/09/remorque-erpent-namur.jpg',
    '365': 'https://remorquepublicitaire.be/wp-content/uploads/Photo/d1974317.Photo.080648.jpg',
    '407': 'https://remorquepublicitaire.be/wp-content/uploads/2023/06/REMORQUE-PUB-Anderlues-Morlanwelz.jpeg',
    '408': 'https://remorquepublicitaire.be/wp-content/uploads/2023/09/408-in.jpg',
    '409': 'https://remorquepublicitaire.be/wp-content/uploads/2024/02/affichage-publicitaire-a-buzet.jpg',
    '415': 'https://remorquepublicitaire.be/wp-content/uploads/2024/06/Peronnes-lez-Binche-in.jpg',
    '505': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/neffe-in.jpg',
    '517': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/517-Beho-Silot-vers-Luxembourg.jpg',
    '519': 'https://remorquepublicitaire.be/wp-content/uploads/Photo/fda13c0a.Photo.120648.jpg',
    '520': 'https://remorquepublicitaire.be/wp-content/uploads/2021/07/520-Vielsam-Regne.jpg',
    '525': 'https://remorquepublicitaire.be/wp-content/uploads/2022/06/525-Durbuy-Somme-Leuze2.jpg',
    '527': 'https://remorquepublicitaire.be/wp-content/uploads/2022/12/527-N4-entre-Barriere-Hinck-et-Tenneville.jpg',
    '530': 'https://remorquepublicitaire.be/wp-content/uploads/2024/02/Wolberg-in.jpg'
}

MONTH_MAP = {
    "01": "Janvier", "02": "Février", "03": "Mars", "04": "Avril",
    "05": "Mai", "06": "Juin", "07": "Juillet", "08": "Août",
    "09": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre"
}

def format_period_human(period_str: str) -> str:
    """Transforme 2026-05 en Mai 2026"""
    if not period_str or "-" not in period_str:
        return period_str or "Date non spécifiée"
    parts = period_str.split("-")
    if len(parts) >= 2 and parts[1] in MONTH_MAP:
        return f"{MONTH_MAP[parts[1]]} {parts[0]}"
    return period_str

def get_friendly_dispo_label(trailer_dict: Dict[str, Any], include_faces: bool = False) -> str:
    """Produit un libellé clair et lisible pour le client (ex: Dès Décembre 2026).
    Ne mentionne les faces que si include_faces=True.
    """
    p_any = trailer_dict.get("prochaine_dispo")
    if not p_any or p_any == "Sur demande (+1 an)":
        return "Sur demande (+1 an)"

    h_any = format_period_human(p_any)
    if not include_faces:
        return h_any

    p_in = trailer_dict.get("prochaine_dispo_in")
    p_out = trailer_dict.get("prochaine_dispo_out")

    if p_in == p_out and p_in == p_any:
        return f"{h_any} (Faces IN & OUT)"
    elif p_any == p_out and p_any != p_in:
        return f"{h_any} (Face OUT)"
    elif p_any == p_in and p_any != p_out:
        return f"{h_any} (Face IN)"
    return h_any

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """Calcul distance en kilomètres entre 2 coordonnées GPS (formule de Haversine)"""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (ValueError, TypeError):
        return None

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(EARTH_RADIUS_KM * c, 2)


class MmoveEngineTools:
    """Moteur déterministe d'analyse spatiale, de filtrage et de scoring."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.trailers: Dict[str, Dict[str, Any]] = {}
        self.geocache: Dict[str, Tuple[float, float]] = dict(DEFAULT_GEO_CACHE)
        self._load_database()
        self._load_geocache()

    def _load_database(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                self.trailers = json.load(f)
        else:
            print(f"Warning: Base de données {self.db_path} introuvable.")

    def reload(self):
        """Recharge les données de la base en mémoire vive sans temps d'arrêt."""
        self._load_database()
        self._load_geocache()
        print(f"[MmoveEngineTools] Rechargé en mémoire : {len(self.trailers)} remorques actives.")

    def _load_geocache(self):
        if os.path.exists(GEOCACHE_PATH):
            try:
                with open(GEOCACHE_PATH, "r", encoding="utf-8") as f:
                    disk_cache = json.load(f)
                    for k, v in disk_cache.items():
                        self.geocache[k] = tuple(v)
            except Exception as e:
                print(f"Warning reading geocache: {e}")

    def _save_geocache(self):
        try:
            with open(GEOCACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.geocache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning saving geocache: {e}")

    def _geocode_google(self, query: str) -> Optional[Tuple[float, float]]:
        """Interroge l'API Google Places / Google Maps Geocoding pour localiser des entreprises, commerces ou adresses en Belgique."""
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        # 1. Tentative Google Places API (Find Place Text Query : spécialement conçu pour les POI et entreprises)
        try:
            url_places = f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input={urllib.parse.quote(query + ', Belgique')}&inputtype=textquery&fields=geometry,name,formatted_address&locationbias=circle:150000@50.46,4.86&key={api_key}"
            req = urllib.request.Request(url_places)
            ssl_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=4) as res:
                data = json.loads(res.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates and "geometry" in candidates[0] and "location" in candidates[0]["geometry"]:
                    loc = candidates[0]["geometry"]["location"]
                    lat, lng = float(loc["lat"]), float(loc["lng"])
                    print(f"[GooglePlaces] '{query}' localisé : ({lat}, {lng}) - {candidates[0].get('name')} ({candidates[0].get('formatted_address')})")
                    return (lat, lng)
        except Exception as e:
            print(f"[GooglePlaces Warning] {e}")

        # 2. Tentative Google Geocoding API (adresses postales, voiries)
        try:
            url_geo = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(query)}&components=country:BE&key={api_key}"
            req = urllib.request.Request(url_geo)
            ssl_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=4) as res:
                data = json.loads(res.read().decode("utf-8"))
                results = data.get("results", [])
                if results and "geometry" in results[0] and "location" in results[0]["geometry"]:
                    loc = results[0]["geometry"]["location"]
                    lat, lng = float(loc["lat"]), float(loc["lng"])
                    print(f"[GoogleGeocode] '{query}' localisé : ({lat}, {lng}) - {results[0].get('formatted_address')}")
                    return (lat, lng)
        except Exception as e:
            print(f"[GoogleGeocode Warning] {e}")

        return None

    def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        """Résout une adresse, entreprise, commune ou localité secondaire en coordonnées (lat, lng) avec cache."""
        if not query or len(query.strip()) < 2:
            return None

        clean_q = normalize_text(query)
        if clean_q in self.geocache:
            return self.geocache[clean_q]

        clean_be = clean_q if "belgi" in clean_q else f"{clean_q}, belgique"
        if clean_be in self.geocache:
            return self.geocache[clean_be]

        # 1. Correspondance locale directe ou floue sur les communes et localités du réseau Mmove
        for t in self.trailers.values():
            t_loc = normalize_text(t.get("localisation"))
            t_ville = normalize_text(t.get("ville"))
            if clean_q == t_loc or clean_q == t_ville or clean_q in t_loc or (len(t_loc) >= 3 and t_loc in clean_q):
                if t.get("lat") and t.get("lng"):
                    coords = (t["lat"], t["lng"])
                    self.geocache[clean_q] = coords
                    self._save_geocache()
                    return coords

        # 2. Appel Google Maps / Google Places API (si clé disponible)
        google_coords = self._geocode_google(query)
        if google_coords:
            self.geocache[clean_q] = google_coords
            self.geocache[clean_be] = google_coords
            self._save_geocache()
            return google_coords

        # 3. Appel Nominatim sécurisé avec en-têtes et contexte SSL
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(clean_be)}&format=json&limit=1&countrycodes=be"
            req = urllib.request.Request(url, headers={"User-Agent": "MmoveAI/1.0 (contact@mediasee.be)"})
            ssl_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=3) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data and len(data) > 0:
                    coords = (float(data[0]["lat"]), float(data[0]["lon"]))
                    self.geocache[clean_q] = coords
                    self.geocache[clean_be] = coords
                    self._save_geocache()
                    return coords
        except Exception as e:
            print(f"Geocoding warning for {query}: {e}")

        return None

    def match_axis(self, trailer: Dict[str, Any], query_axes: List[str]) -> bool:
        """Vérifie si la remorque correspond à un des axes routiers demandés."""
        if not query_axes:
            return True

        trailer_axe = (trailer.get("axe_routier") or "").upper()
        trailer_code = (trailer.get("code_route") or "").upper()
        trailer_nom = (trailer.get("nom_route") or "").upper()

        for q in query_axes:
            clean_q = q.upper().replace(" ", "")
            # Correspondance code direct (ex: N4, E411, N25, E42)
            if clean_q in trailer_code or clean_q in trailer_axe:
                return True
            # Regex pour éviter les faux positifs (ex: N4 vs N40)
            pattern = rf"\b{re.escape(clean_q)}\b"
            if re.search(pattern, trailer_axe) or re.search(pattern, trailer_code):
                return True
            # Recherche par nom de route (ex: Ardennes, Condroz, Charleroi)
            if len(clean_q) > 4 and clean_q in trailer_nom:
                return True

        return False

    def check_period_availability(
        self, trailer: Dict[str, Any], target_periods: List[str]
    ) -> Dict[str, Any]:
        """
        Vérifie la disponibilité d'une remorque pour une ou plusieurs périodes (AAAA-MM).
        Retourne :
        - is_available_any : True si libre au moins un mois
        - is_available_all : True si libre sur tous les mois
        - available_months : Liste des mois disponibles avec la face libre ('IN', 'OUT' ou 'LES DEUX')
        - detail : Dict { "2026-05": { "IN": "DISPO", "OUT": "LOUÉ" } }
        """
        dispos = trailer.get("disponibilites", {})
        if not target_periods:
            return {
                "is_available_any": True,
                "is_available_all": True,
                "available_months": [],
                "available_faces": "IN et OUT",
                "detail": {}
            }

        available_months = []
        detail = {}
        all_ok = True

        for p in target_periods:
            p_data = dispos.get(p, {"IN": "DISPO", "OUT": "DISPO"})
            detail[p] = p_data
            status_in = p_data.get("IN") == "DISPO"
            status_out = p_data.get("OUT") == "DISPO"

            if status_in or status_out:
                face_desc = "LES DEUX FACES" if (status_in and status_out) else ("Face IN" if status_in else "Face OUT")
                available_months.append({
                    "period": p,
                    "period_human": format_period_human(p),
                    "face": face_desc,
                    "in_libre": status_in,
                    "out_libre": status_out,
                })
            else:
                all_ok = False

        return {
            "is_available_any": len(available_months) > 0,
            "is_available_all": all_ok and len(available_months) == len(target_periods),
            "available_months": available_months,
            "detail": detail,
        }

    def search_and_rank(
        self,
        locations: Optional[List[str]] = None,
        axes: Optional[List[str]] = None,
        target_periods: Optional[List[str]] = None,
        province: Optional[str] = None,
        direction: Optional[str] = None,
        contexte_query: Optional[str] = None,
        max_distance_km: float = 25.0,
        top_k: int = 5,
        require_availability: bool = True,
        sort_by_dispo: bool = False,
        enforce_axis_diversity: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Moteur de filtrage et scoring multi-critères.
        Exécute en ~2-5ms sur l'ensemble des remorques actives.
        """
        # 1. Résolution des coordonnées cibles
        target_coords: List[Tuple[float, float]] = []
        if locations:
            for loc in locations:
                coords = self.geocode(loc)
                if coords:
                    target_coords.append(coords)

        # Normalisation des périodes
        clean_periods = []
        if target_periods:
            for tp in target_periods:
                # Format AAAA-MM
                m = re.search(r"(\d{4})[-_](\d{1,2})", tp)
                if m:
                    clean_periods.append(f"{m.group(1)}-{int(m.group(2)):02d}")
                else:
                    clean_periods.append(tp)

        clean_loc_queries = [normalize_text(loc) for loc in (locations or []) if loc and len(loc.strip()) >= 2]

        candidates = []

        for rem_id, t in self.trailers.items():
            # A. Filtre d'axe routier si spécifié
            if axes and not self.match_axis(t, axes):
                continue

            # B. Filtre province si spécifiée
            if province:
                t_prov = (t.get("province") or "").lower()
                if province.lower() not in t_prov:
                    continue

            # Spécification 1 & 2 : Indexation des alias et recherche floue (Fuzzy search)
            t_ville = normalize_text(t.get("ville"))
            t_loc = normalize_text(t.get("localisation"))
            t_axe = normalize_text(t.get("axe_routier"))
            t_route = normalize_text(t.get("nom_route"))
            t_ctx = normalize_text(t.get("contexte_visibilite"))

            has_direct_physical_match = False
            has_contextual_match = False

            if clean_loc_queries:
                for q in clean_loc_queries:
                    # 1. Correspondance physique directe : ville ou localisation (ex: 'wierde' dans 'Wierde 2')
                    if q in t_loc or q in t_ville or (len(t_loc) >= 3 and t_loc in q):
                        has_direct_physical_match = True
                        break
                    # 2. Correspondance contextuelle : axe routier, nom de route ou contexte de visibilité
                    if q in t_axe or q in t_route or q in t_ctx:
                        has_contextual_match = True

            # C. Calcul de distance minimale
            min_dist = None
            if target_coords and t.get("lat") and t.get("lng"):
                dists = [haversine_distance(lat, lng, t["lat"], t["lng"]) for lat, lng in target_coords]
                valid_dists = [d for d in dists if d is not None]
                if valid_dists:
                    min_dist = min(valid_dists)

            if min_dist is None and has_direct_physical_match:
                min_dist = 0.0

            # Si des lieux sont demandés et que la remorque est hors rayon, on exclut
            # (Ne JAMAIS exclure une remorque qui matche directement par le texte ou par l'axe)
            if target_coords and min_dist is not None:
                if min_dist > max_distance_km and not has_direct_physical_match and not (axes and self.match_axis(t, axes)):
                    continue

            # D. Vérification des disponibilités
            avail_info = self.check_period_availability(t, clean_periods)
            if clean_periods and require_availability and not avail_info["is_available_any"]:
                # Non disponible sur la période demandée
                continue

            # E. Score Composite
            # 1. Score Fréquentation (0 à 100) : max Wallonie ~ 45 000 véh/j
            freq = t.get("frequentation_jour") or 15000
            freq_score = min(100.0, (freq / 40000.0) * 100.0)

            # 2. Score Proximité (0 à 100)
            if min_dist is not None:
                # 0 km = 100 pts, 25 km = 20 pts
                prox_score = max(10.0, 100.0 - (min_dist * 3.5))
            else:
                prox_score = 50.0  # Neutre si pas de POI spécifié

            # 3. Score Contexte (bonus si le contexte de visibilité matche la requête)
            context_bonus = 0.0
            t_contexte = (t.get("contexte_visibilite") or "").lower()
            if contexte_query and t_contexte:
                words = [w for w in re.split(r"\W+", contexte_query.lower()) if len(w) > 3]
                matches = sum(1 for w in words if w in t_contexte)
                context_bonus = min(30.0, matches * 15.0)

            # 4. Spécification 3 : Hiérarchisation prioritaire des localités secondaires
            locality_bonus = 0.0
            if has_direct_physical_match:
                locality_bonus = 100.0  # Assure la priorité absolue en tête de liste
            elif has_contextual_match:
                locality_bonus = 35.0

            # 5. Score Disponibilité
            dispo_score = 100.0 if avail_info.get("is_available_all") else (70.0 if avail_info.get("is_available_any") else 30.0)

            # Score global pondéré
            total_score = (prox_score * 0.35) + (freq_score * 0.25) + (dispo_score * 0.15) + context_bonus + locality_bonus

            # Image fallback
            photo = t.get("photo_in") or PHOTO_FALLBACKS.get(rem_id) or "https://remorquepublicitaire.be/wp-content/uploads/2021/07/logo-mmove.png"

            candidate_obj = {
                "id": rem_id,
                "lat": t.get("lat"),
                "lng": t.get("lng"),
                "ville": t["ville"],
                "localisation": t["localisation"],
                "province": t["province"],
                "axe_routier": t["axe_routier"],
                "code_route": t["code_route"],
                "direction_in": t["direction_in"],
                "direction_out": t["direction_out"],
                "frequentation_jour": freq,
                "ots_mensuel": t.get("ots_mensuel") or int(freq * 30 * 1.2),
                "score_impact": t.get("score_impact") or "Élevé",
                "contexte_visibilite": t.get("contexte_visibilite") or "Visibilité directe axe passant",
                "lien": t["lien"],
                "distance_km": round(min_dist, 2) if min_dist is not None else None,
                "prochaine_dispo": t.get("prochaine_dispo"),
                "prochaine_dispo_in": t.get("prochaine_dispo_in"),
                "prochaine_dispo_out": t.get("prochaine_dispo_out"),
                "prochaine_dispo_human": format_period_human(t.get("prochaine_dispo")),
                "prochaine_dispo_label": get_friendly_dispo_label(t),
                "target_period": clean_periods[0] if clean_periods else None,
                "target_period_human": format_period_human(clean_periods[0]) if clean_periods else None,
                "is_available_in_target_period": avail_info.get("is_available_any") if clean_periods else True,
                "availability": avail_info,
                "photo_url": photo,
                "is_direct_match": has_direct_physical_match,
                "total_score": round(total_score, 1),
            }
            candidates.append(candidate_obj)

        if enforce_axis_diversity:
            # Recommandation de campagne : Tri par proximité / score puis DIVERSITÉ STRICTE DES AXES (Zéro doublon d'axe)
            if clean_loc_queries or target_coords:
                candidates.sort(
                    key=lambda x: (
                        x.get("distance_km") if x.get("distance_km") is not None else 9999.0,
                        not x.get("is_direct_match", False),
                        -x["total_score"]
                    )
                )
            else:
                candidates.sort(key=lambda x: (x.get("is_direct_match", False), x["total_score"]), reverse=True)

            def get_axis_signature(item: Dict[str, Any]) -> str:
                code = (item.get("code_route") or "").upper().strip()
                if code and len(code) >= 2:
                    m = re.match(r"([A-Z]\d+)", code)
                    if m:
                        return m.group(1)
                    return code
                axe = (item.get("axe_routier") or "").upper().strip()
                m_axe = re.search(r"\b([A-Z]\d+)\b", axe)
                if m_axe:
                    return m_axe.group(1)
                clean_axe = normalize_text(axe)
                if clean_axe:
                    return clean_axe
                return item.get("id")

            selected = []
            seen_axes = set()

            # Passe 1 : Un seul panneau par axe routier distinct
            for c in candidates:
                sig = get_axis_signature(c)
                if sig not in seen_axes:
                    seen_axes.add(sig)
                    selected.append(c)
                    if len(selected) == top_k:
                        break

            # Passe 2 : S'il y a moins d'axes distincts que de panneaux demandés dans le rayon,
            # compléter avec les meilleurs restants sur des localisations différentes
            if len(selected) < top_k:
                selected_ids = {s["id"] for s in selected}
                for c in candidates:
                    if c["id"] not in selected_ids:
                        selected.append(c)
                        selected_ids.add(c["id"])
                        if len(selected) == top_k:
                            break

            return selected
        elif sort_by_dispo:
            # 1. Demande de disponibilité : Sélection géographique puis tri chronologique (plus proche dans le temps en premier)
            candidates.sort(key=lambda x: (x.get("is_direct_match", False), x["total_score"]), reverse=True)
            selected = candidates[:top_k]
            selected.sort(
                key=lambda x: (
                    not x.get("is_direct_match", False),
                    x.get("prochaine_dispo") or "9999-99",
                    x.get("distance_km") if x.get("distance_km") is not None else 9999.0,
                    -x["total_score"]
                )
            )
            return selected
        elif clean_loc_queries or target_coords:
            # 2. Demande de localisation : Tri STRICT suivant la distance croissante (le plus proche en km en premier)
            # En cas d'égalité sur la distance : priorité à la correspondance directe sur la ville puis score composite
            candidates.sort(
                key=lambda x: (
                    x.get("distance_km") if x.get("distance_km") is not None else 9999.0,
                    not x.get("is_direct_match", False),
                    -x["total_score"]
                )
            )
            return candidates[:top_k]
        else:
            # 3. Tri classique : score composite
            candidates.sort(key=lambda x: (x.get("is_direct_match", False), x["total_score"]), reverse=True)
            return candidates[:top_k]

    def get_trailer_by_id(self, trailer_id: str) -> Optional[Dict[str, Any]]:
        """Recherche directe par ID de remorque."""
        clean_id = str(trailer_id).strip().replace("#", "")
        return self.trailers.get(clean_id)

    def plan_multi_month_campaign(
        self,
        locations: Optional[List[str]] = None,
        target_periods: Optional[List[str]] = None,
        count_per_month: int = 5,
        max_distance_km: float = 30.0,
        axes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Génère une proposition de campagne publicitaire multi-mois avec rotation dynamique des faces.
        Règles :
        - Diversité stricte des axes routiers (au maximum 1 panneau par axe par mois).
        - Rotation anti-doublon consécutif : interdit de placer 2 mois de suite le client sur le même panneau/direction.
        - Calcul d'impact cumulé (OTS, véhicules/jour) et rétroplanning bâche au 15 du mois précédent.
        """
        now = datetime.now()
        cur_year = now.year
        cur_month = now.month

        # Si aucune période fournie, définir par défaut le mois prochain
        if not target_periods:
            next_m = cur_month + 1
            next_y = cur_year
            if next_m > 12:
                next_m = 1
                next_y += 1
            periods = [f"{next_y}-{next_m:02d}"]
        else:
            periods = sorted(list(dict.fromkeys(target_periods)))

        def get_axis_sig(c: Dict[str, Any]) -> str:
            cr = (c.get("code_route") or "").upper().strip()
            if cr:
                m = re.match(r"([A-Z]\d+)", cr)
                if m:
                    return m.group(1)
            ax = (c.get("axe_routier") or "").upper().strip()
            m = re.search(r"\b([NE]\d+)\b", ax)
            if m:
                return m.group(1)
            return c.get("ville", "")

        month_names = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

        month_plans = []
        used_in_prev_month = set()
        all_unique_panels = set()

        for idx, period in enumerate(periods, start=1):
            candidates = self.search_and_rank(
                locations=locations,
                axes=axes,
                target_periods=[period],
                max_distance_km=max_distance_km,
                top_k=40,
                enforce_axis_diversity=False
            )

            fresh_candidates = [c for c in candidates if str(c["id"]) not in used_in_prev_month]
            reuse_candidates = [c for c in candidates if str(c["id"]) in used_in_prev_month]

            selected = []
            seen_axes = set()

            # 1. Priorité aux candidats frais non utilisés le mois précédent avec axes distincts
            for c in fresh_candidates:
                sig = get_axis_sig(c)
                if sig not in seen_axes:
                    seen_axes.add(sig)
                    selected.append(c)
                    if len(selected) == count_per_month:
                        break

            # 2. Compléter avec les candidats frais restants si moins d'axes que de panneaux demandés
            if len(selected) < count_per_month:
                sel_ids = {s["id"] for s in selected}
                for c in fresh_candidates:
                    if c["id"] not in sel_ids:
                        selected.append(c)
                        sel_ids.add(c["id"])
                        if len(selected) == count_per_month:
                            break

            # 3. Dernier recours : piocher dans les candidats réutilisés si le bassin est restreint
            if len(selected) < count_per_month:
                sel_ids = {s["id"] for s in selected}
                for c in reuse_candidates:
                    if c["id"] not in sel_ids:
                        selected.append(c)
                        sel_ids.add(c["id"])
                        if len(selected) == count_per_month:
                            break

            used_in_prev_month = {str(s["id"]) for s in selected}
            for s in selected:
                all_unique_panels.add(str(s["id"]))

            period_human = format_period_human(period)
            
            # Calcul du rétroplanning pour ce mois
            parts = period.split("-")
            py, pm = int(parts[0]), int(parts[1])
            prev_m = 12 if pm == 1 else pm - 1
            prev_y = py - 1 if pm == 1 else py
            deadline_str = f"15 {month_names[prev_m]}"
            deadline_full = f"15 {month_names[prev_m]} {prev_y}"

            m_veh = sum(p.get("frequentation_jour", 0) for p in selected)
            m_ots = sum(p.get("ots_mensuel", int(p.get("frequentation_jour", 0) * 36)) for p in selected)

            month_plans.append({
                "period": period,
                "period_human": period_human,
                "month_index": idx,
                "panels": selected,
                "stats": {
                    "count": len(selected),
                    "veh_per_day": m_veh,
                    "ots_month": m_ots,
                },
                "deadline": deadline_str,
                "deadline_full": deadline_full
            })

        total_faces_deployed = sum(m["stats"]["count"] for m in month_plans)
        total_cumulative_ots = sum(m["stats"]["ots_month"] for m in month_plans)
        avg_veh_per_day = int(sum(m["stats"]["veh_per_day"] for m in month_plans) / max(1, len(month_plans)))

        primary_loc = locations[0].title() if locations else "Wallonie"

        return {
            "periods": periods,
            "months": month_plans,
            "summary": {
                "location": primary_loc,
                "months_count": len(month_plans),
                "faces_per_month": count_per_month,
                "total_faces_deployed": total_faces_deployed,
                "unique_panels_count": len(all_unique_panels),
                "avg_veh_per_day": avg_veh_per_day,
                "total_cumulative_ots": total_cumulative_ots,
                "first_deadline": month_plans[0]["deadline_full"] if month_plans else ""
            }
        }

