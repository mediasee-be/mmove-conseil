"""
Build Mmove Consolidated Database
Consolide le réseau des remorques actives (core/mmove_network_enriched.csv)
avec les calendriers de disponibilité 2026 et 2027 (fichiers Excel).
Génère data/mmove_db.json pour un accès en mémoire ultra-rapide (< 1ms).
"""

import os
import csv
import json
import openpyxl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "core", "mmove_network_enriched.csv")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DB = os.path.join(DATA_DIR, "mmove_db.json")

EXCEL_2026_PATH = os.path.join(DATA_DIR, "Mmove_2026.xlsx")
EXCEL_2027_PATH = os.path.join(DATA_DIR, "Mmove_2027.xlsx")

MONTH_NAMES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

def parse_schedule_excel(file_path, year):
    """
    Lit l'onglet DISPO d'un classeur Excel Mmove annuel
    Retourne { trailer_id: { "YYYY-MM": { "IN": "DISPO"|"LOUÉ", "OUT": "DISPO"|"LOUÉ" } } }
    """
    if not os.path.exists(file_path):
        print(f"Attention : Fichier {file_path} introuvable.")
        return {}

    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    if "DISPO" not in wb.sheetnames:
        print(f"Feuille DISPO introuvable dans {file_path}")
        return {}

    sheet = wb["DISPO"]
    schedule = {}

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return {}

    # Ligne d'en-tête (normalement ligne index 0)
    # Col 0: ID remorque, Col 1: Ville/Emplacement, Col 2: Emplacement, Col 3: Direction
    # Col 4..: Mois alternés IN / OUT
    for r in rows[2:]:  # Commence après les en-têtes
        rem_raw = r[0]
        if rem_raw is None:
            continue
        try:
            rem_id = str(int(float(rem_raw))).strip()
        except (ValueError, TypeError):
            continue

        if not rem_id or rem_id == "0":
            continue

        schedule[rem_id] = {}

        # 12 mois avec 2 colonnes par mois (IN et OUT)
        col_idx = 4
        for m_idx, month_name in enumerate(MONTH_NAMES, start=1):
            period_key = f"{year}-{m_idx:02d}"
            status_in = "DISPO"
            status_out = "DISPO"

            if col_idx < len(r):
                val_in = str(r[col_idx]).strip().upper() if r[col_idx] else ""
                status_in = "LOUÉ" if "LOU" in val_in or "RESERV" in val_in or "SOLD" in val_in else "DISPO"
            
            if col_idx + 1 < len(r):
                val_out = str(r[col_idx + 1]).strip().upper() if r[col_idx + 1] else ""
                status_out = "LOUÉ" if "LOU" in val_out or "RESERV" in val_out or "SOLD" in val_out else "DISPO"

            schedule[rem_id][period_key] = {
                "IN": status_in,
                "OUT": status_out,
            }
            col_idx += 2

    return schedule

def calculate_next_dispo(availability_dict):
    """
    Calcule la prochaine disponibilité pour chaque face (IN / OUT)
    et globale.
    """
    sorted_periods = sorted(availability_dict.keys())
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
        "prochaine_dispo_in": next_in or "Non disponible",
        "prochaine_dispo_out": next_out or "Non disponible",
        "prochaine_dispo": next_any or "Non disponible"
    }

def build_database():
    print(f"Lecture du réseau Mmove depuis {CSV_PATH}...")
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Fichier {CSV_PATH} introuvable.")

    # 1. Charger les plannings 2026 et 2027
    print(f"Chargement des disponibilités 2026...")
    sched_2026 = parse_schedule_excel(EXCEL_2026_PATH, 2026)
    print(f"Plannings 2026 chargés pour {len(sched_2026)} remorques.")

    print(f"Chargement des disponibilités 2027...")
    sched_2027 = parse_schedule_excel(EXCEL_2027_PATH, 2027)
    print(f"Plannings 2027 chargés pour {len(sched_2027)} remorques.")

    # 2. Lire le CSV enrichi
    trailers = {}
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            active_val = r.get("Active", "").strip().upper()
            if active_val != "Y":
                continue  # RÈGLE ABSOLUE : Uniquement remorques actives

            rem_raw = r.get("Remorque", "").strip()
            try:
                rem_id = str(int(float(rem_raw)))
            except (ValueError, TypeError):
                rem_id = rem_raw

            if not rem_id:
                continue

            # GPS
            gps_str = r.get("GPS", "").strip()
            lat, lng = None, None
            if gps_str and "," in gps_str:
                try:
                    parts = gps_str.split(",")
                    lat = float(parts[0].strip())
                    lng = float(parts[1].strip())
                except (ValueError, IndexError):
                    pass

            # Fréquentation
            freq_raw = r.get("Frequentation_Moyenne_veh_jour", "").strip()
            freq_val = None
            if freq_raw:
                try:
                    freq_val = int(float(freq_raw.replace(" ", "").replace(",", ".")))
                except ValueError:
                    freq_val = None

            # Contexte & Scores
            contexte = r.get("Contexte_Visibilite", "").strip()
            score_impact = r.get("Score_Impact_Temps_Exposition", "").strip()
            axe_routier = r.get("Axe-remorque", "").strip()
            code_route = r.get("Code_Route", "").strip()
            nom_route = r.get("Nom_Route", "").strip()
            ville = r.get("Ville-remorque", "").strip()
            localisation = r.get("Localisation-remorque", "").strip()
            direction_in = r.get("Direction-remorque", "").strip()
            direction_out = r.get("Direction-out", "").strip()
            province = r.get("Province", "").strip()

            photo_in = r.get("Photo-IN", "").strip()
            photo_out = r.get("Photo-OUT", "").strip()

            # Fusion disponibilités 2026 + 2027
            avail_combined = {}
            if rem_id in sched_2026:
                avail_combined.update(sched_2026[rem_id])
            if rem_id in sched_2027:
                avail_combined.update(sched_2027[rem_id])

            next_dispos = calculate_next_dispo(avail_combined)

            # OTS estimé mensuel (~ 30 jours * frequentation * facteur de passage)
            ots_val = int(freq_val * 30 * 1.2) if freq_val else None

            trailers[rem_id] = {
                "id": rem_id,
                "ville": ville,
                "localisation": localisation,
                "province": province,
                "axe_routier": axe_routier,
                "code_route": code_route,
                "nom_route": nom_route,
                "direction_in": direction_in,
                "direction_out": direction_out,
                "lat": lat,
                "lng": lng,
                "active": "Y",
                "frequentation_jour": freq_val,
                "ots_mensuel": ots_val,
                "score_impact": score_impact,
                "contexte_visibilite": contexte,
                "photo_in": photo_in,
                "photo_out": photo_out,
                "lien": f"https://remorquepublicitaire.be/remorque/{rem_id}",
                "disponibilites": avail_combined,
                "prochaine_dispo": next_dispos["prochaine_dispo"],
                "prochaine_dispo_in": next_dispos["prochaine_dispo_in"],
                "prochaine_dispo_out": next_dispos["prochaine_dispo_out"],
            }

    print(f"Total remorques actives consolidées : {len(trailers)}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_DB, "w", encoding="utf-8") as out_f:
        json.dump(trailers, out_f, ensure_ascii=False, indent=2)

    print(f"Base de données générée avec succès : {OUTPUT_DB}")
    return trailers

build_unified_database = build_database

if __name__ == "__main__":
    build_database()
