import os
import csv
import io
import json
import ssl
import urllib.request
from datetime import datetime

SHEET_RESERVATIONS_URL = "https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=1394058063"
SHEET_PANELS_URL = "https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=2093954666"

def fetch_csv(url):
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MDS-AI-Sync/2.0)"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def test_sync():
    print("1. Téléchargement des réservations...")
    res_csv = fetch_csv(SHEET_RESERVATIONS_URL)
    print(f"   Taille reçue : {len(res_csv)} octets")
    
    print("2. Téléchargement de l'inventaire des remorques...")
    pan_csv = fetch_csv(SHEET_PANELS_URL)
    print(f"   Taille reçue : {len(pan_csv)} octets")

    # Parsing des réservations
    reader_res = csv.DictReader(io.StringIO(res_csv))
    schedules = {}
    total_dispo = 0
    total_loue = 0

    for r in reader_res:
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

        # RÈGLE D'OR : "Si la colonne client est vide, alors c'est dispo."
        is_dispo = (not client) and ("BLOQ" not in remarque)
        status = "DISPO" if is_dispo else "LOUÉ"

        if is_dispo:
            total_dispo += 1
        else:
            total_loue += 1

        if rem_id not in schedules:
            schedules[rem_id] = {}
        if period not in schedules[rem_id]:
            schedules[rem_id][period] = {"IN": "DISPO", "OUT": "DISPO"}

        if face in ["IN", "OUT"]:
            schedules[rem_id][period][face] = status

    print(f"   Créneaux analysés : {total_dispo} DISPO, {total_loue} LOUÉ sur {len(schedules)} remorques")

    # Parsing des remorques
    reader_pan = csv.DictReader(io.StringIO(pan_csv))
    trailers = {}
    current_month = datetime.now().strftime("%Y-%m")

    for r in reader_pan:
        active_val = (r.get("Active") or "").strip().upper()
        if active_val != "Y":
            continue

        raw_rem = (r.get("Remorque") or "").strip()
        try:
            rem_id = str(int(float(raw_rem)))
        except (ValueError, TypeError):
            rem_id = raw_rem

        if not rem_id or rem_id == "0":
            continue

        gps_str = (r.get("GPS") or "").strip()
        lat, lng = None, None
        if gps_str and "," in gps_str:
            try:
                parts = gps_str.split(",")
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
            except (ValueError, IndexError):
                pass

        freq_raw = (r.get("Frequentation_Moyenne_veh_jour") or "").strip()
        freq_val = None
        if freq_raw:
            try:
                freq_val = int(float(freq_raw.replace(" ", "").replace(",", ".")))
            except ValueError:
                freq_val = None

        avail = schedules.get(rem_id, {})
        
        # Calcul prochaine dispo
        sorted_p = sorted([p for p in avail.keys() if p >= current_month])
        next_in = None
        next_out = None
        next_any = None
        for p in sorted_p:
            st = avail[p]
            if next_in is None and st.get("IN") == "DISPO":
                next_in = p
            if next_out is None and st.get("OUT") == "DISPO":
                next_out = p
            if next_any is None and (st.get("IN") == "DISPO" or st.get("OUT") == "DISPO"):
                next_any = p

        ots_raw = (r.get("Vues_Mensuelles_OTS") or "").strip()
        try:
            ots_val = int(float(ots_raw.replace(" ", "").replace(",", "."))) if ots_raw else (int(freq_val * 30 * 1.2) if freq_val else None)
        except ValueError:
            ots_val = int(freq_val * 30 * 1.2) if freq_val else None

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
            "prochaine_dispo": next_any or "Sur demande (+1 an)",
            "prochaine_dispo_in": next_in or "Sur demande (+1 an)",
            "prochaine_dispo_out": next_out or "Sur demande (+1 an)",
        }

    print(f"3. Total remorques actives consolidées en direct : {len(trailers)}")
    sample_ids = ["101", "102", "114", "201", "343", "512"]
    for sid in sample_ids:
        if sid in trailers:
            t = trailers[sid]
            print(f"   Remorque #{t['id']} ({t['ville']}) -> Prochaine dispo: {t['prochaine_dispo']} | Trafic: {t['frequentation_jour']} véh/j | OTS: {t['ots_mensuel']}")

if __name__ == "__main__":
    test_sync()
