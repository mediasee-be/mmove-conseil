"""
Build Mmove Consolidated Database (Google Sheets Direct Sync)
Synchronise directement les données en temps réel depuis Google Sheets :
1. Réservations & Disponibilités :
   https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/edit?gid=1394058063
   Règle : Si la colonne Client est vide, alors c'est DISPO.
2. Inventaire des remorques & Métriques :
   https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/edit?gid=2093954666

Génère data/mmove_db.json avec cache local de secours pour résilience maximale.
"""

import os
import csv
import io
import json
import ssl
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DB = os.path.join(DATA_DIR, "mmove_db.json")

SHEET_RESERVATIONS_URL = "https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=1394058063"
SHEET_PANELS_URL = "https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=2093954666"

CACHE_RESERVATIONS_PATH = os.path.join(DATA_DIR, "reservations_cache.csv")
CACHE_PANELS_PATH = os.path.join(DATA_DIR, "trailers_cache.csv")
FALLBACK_CSV_PATH = os.path.join(BASE_DIR, "core", "mmove_network_enriched.csv")

def fetch_csv_with_cache(url: str, cache_path: str, fallback_path: str = None) -> str:
    """
    Télécharge le CSV depuis Google Sheets.
    En cas de succès, met à jour le cache local.
    En cas d'échec (hors-ligne), utilise le cache local ou le fichier fallback.
    """
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MDS-AI-Sync/2.0)"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            if len(content) > 1000 and "Remorque" in content:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return content
    except Exception as e:
        print(f"[BuildDB] Avertissement: échec téléchargement Google Sheets ({e}). Tentative cache local...")

    # Utilisation du cache local
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()

    # Utilisation du fallback
    if fallback_path and os.path.exists(fallback_path):
        with open(fallback_path, "r", encoding="utf-8") as f:
            return f.read()

    raise RuntimeError(f"Impossible de charger les données (aucun cache disponible pour {cache_path})")

def parse_reservations(csv_content: str) -> dict:
    """
    Parse les réservations Google Sheet.
    RÈGLE : Si la colonne Client est vide (et non bloqué), alors c'est DISPO.
    Retourne { trailer_id: { "YYYY-MM": { "IN": "DISPO"|"LOUÉ", "OUT": "DISPO"|"LOUÉ" } } }
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    schedules = {}

    for r in reader:
        raw_rem = (r.get("Remorque") or "").strip()
        if not raw_rem:
            continue
        try:
            rem_id = str(int(float(raw_rem)))
        except (ValueError, TypeError):
            rem_id = raw_rem

        period = (r.get("Période") or r.get("Periode") or "").strip()
        face = (r.get("Face") or "").strip().upper()
        client = (r.get("Client") or "").strip()
        remarque = (r.get("Remarque") or "").strip().upper()

        # RÈGLE D'OR MÉTIER M MOVE
        is_dispo = (not client) and ("BLOQ" not in remarque)
        status = "DISPO" if is_dispo else "LOUÉ"

        if rem_id not in schedules:
            schedules[rem_id] = {}
        if period not in schedules[rem_id]:
            schedules[rem_id][period] = {"IN": "DISPO", "OUT": "DISPO"}

        if face in ["IN", "OUT"]:
            schedules[rem_id][period][face] = status

    return schedules

def calculate_next_dispo(availability_dict: dict, current_month: str = None) -> dict:
    """
    Calcule la prochaine disponibilité à partir du mois courant ou futur.
    """
    if current_month is None:
        current_month = datetime.now().strftime("%Y-%m")

    # On ne regarde que les périodes présentes ou futures
    future_periods = sorted([p for p in availability_dict.keys() if p >= current_month])
    
    # Si aucune période future renseignée, fallback sur toutes les périodes triées
    sorted_periods = future_periods if future_periods else sorted(availability_dict.keys())

    next_in = None
    next_out = None
    next_any = None

    for p in sorted_periods:
        st = availability_dict[p]
        if next_in is None and st.get("IN") == "DISPO":
            next_in = p
        if next_out is None and st.get("OUT") == "DISPO":
            next_out = p
        if next_any is None and (st.get("IN") == "DISPO" or st.get("OUT") == "DISPO"):
            next_any = p

    return {
        "prochaine_dispo_in": next_in or "Sur demande (+1 an)",
        "prochaine_dispo_out": next_out or "Sur demande (+1 an)",
        "prochaine_dispo": next_any or "Sur demande (+1 an)"
    }

def build_database() -> dict:
    """
    Consolide la base de données M Move à partir des flux Google Sheets.
    """
    print("[BuildDB] Connexion aux Google Sheets M Move...")
    res_content = fetch_csv_with_cache(SHEET_RESERVATIONS_URL, CACHE_RESERVATIONS_PATH)
    schedules = parse_reservations(res_content)
    print(f"[BuildDB] Calendriers chargés pour {len(schedules)} remorques.")

    pan_content = fetch_csv_with_cache(SHEET_PANELS_URL, CACHE_PANELS_PATH, FALLBACK_CSV_PATH)
    reader_pan = csv.DictReader(io.StringIO(pan_content))
    
    trailers = {}
    current_month = datetime.now().strftime("%Y-%m")

    for r in reader_pan:
        active_val = (r.get("Active") or "").strip().upper()
        if active_val != "Y":
            continue  # RÈGLE ABSOLUE : uniquement remorques actives

        raw_rem = (r.get("Remorque") or "").strip()
        try:
            rem_id = str(int(float(raw_rem)))
        except (ValueError, TypeError):
            rem_id = raw_rem

        if not rem_id or rem_id == "0":
            continue

        # Coordonnées GPS
        gps_str = (r.get("GPS") or "").strip()
        lat, lng = None, None
        if gps_str and "," in gps_str:
            try:
                parts = gps_str.split(",")
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
            except (ValueError, IndexError):
                pass

        # Fréquentation
        freq_raw = (r.get("Frequentation_Moyenne_veh_jour") or "").strip()
        freq_val = None
        if freq_raw:
            try:
                freq_val = int(float(freq_raw.replace(" ", "").replace(",", ".")))
            except ValueError:
                freq_val = None

        # Vues mensuelles OTS
        ots_raw = (r.get("Vues_Mensuelles_OTS") or "").strip()
        try:
            ots_val = int(float(ots_raw.replace(" ", "").replace(",", "."))) if ots_raw else (int(freq_val * 30 * 1.2) if freq_val else None)
        except ValueError:
            ots_val = int(freq_val * 30 * 1.2) if freq_val else None

        avail = schedules.get(rem_id, {})
        next_dispos = calculate_next_dispo(avail, current_month)

        trailers[rem_id] = {
            "id": rem_id,
            "ville": (r.get("Ville-remorque") or "").strip(),
            "localisation": (r.get("Localisation-remorque") or "").strip(),
            "province": (r.get("Province") or "").strip(),
            "axe_routier": (r.get("Axe-remorque") or "").strip(),
            "code_route": (r.get("Code_Route") or "").strip(),
            "nom_route": (r.get("Nom_Route") or "").strip(),
            "direction_in": (r.get("Direction-remorque") or "").strip(),
            "direction_out": (r.get("Direction-out") or "").strip(),
            "lat": lat,
            "lng": lng,
            "active": "Y",
            "frequentation_jour": freq_val,
            "ots_mensuel": ots_val,
            "score_impact": (r.get("Score_Impact_Temps_Exposition") or "").strip(),
            "contexte_visibilite": (r.get("Contexte_Visibilite") or "").strip(),
            "photo_in": (r.get("Photo-IN") or "").strip(),
            "photo_out": (r.get("Photo-OUT") or "").strip(),
            "lien": (r.get("Lien") or f"https://remorquepublicitaire.be/remorque/{rem_id}").strip(),
            "disponibilites": avail,
            "prochaine_dispo": next_dispos["prochaine_dispo"],
            "prochaine_dispo_in": next_dispos["prochaine_dispo_in"],
            "prochaine_dispo_out": next_dispos["prochaine_dispo_out"],
        }

    print(f"[BuildDB] Total remorques actives consolidées en direct : {len(trailers)}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_DB, "w", encoding="utf-8") as out_f:
        json.dump(trailers, out_f, ensure_ascii=False, indent=2)

    print(f"[BuildDB] Base de données générée avec succès : {OUTPUT_DB}")
    return trailers

build_unified_database = build_database

if __name__ == "__main__":
    build_database()
