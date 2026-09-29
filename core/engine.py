"""
Mmove Prospection Engine
Calcul universel de croisement géographique entre les points d'intérêt d'un prospect
et le réseau des 134 remorques publicitaires Mmove en Wallonie.
"""

import os
import re
import csv
import io
import json
import math
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

EARTH_RADIUS_KM = 6371.0

def haversine_distance(lat1, lon1, lat2, lon2):
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

def geocode_address_nominatim(address_str, user_agent="MmoveProspection/1.0"):
    """Géocodage d'adresse via OpenStreetMap Nominatim (Belgique)"""
    if not address_str or len(address_str.strip()) < 3:
        return None, None
    query = address_str.strip()
    if "belgique" not in query.lower() and "belgium" not in query.lower():
        query += ", Belgique"
        
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1&countrycodes=be"
    req = urllib.request.Request(url, headers={'User-Agent': user_agent})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            if data and len(data) > 0:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Warning geocoding {address_str}: {e}")
    return None, None

# Fallbacks d'images vérifiées pour les remorques sans photo directe dans le sheet
TRAILER_PHOTO_FALLBACKS = {
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

def parse_mmove_network(csv_path):
    """Parse le fichier CSV enrichi des remorques Mmove (uniquement les panneaux actifs)"""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Fichier réseau Mmove introuvable : {csv_path}")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader, [])]

    # Détecter si on a les en-têtes standard de Mmove_App
    is_enriched_format = any('Frequentation' in h or 'Active' in h for h in headers)

    trailers = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        if is_enriched_format:
            dict_reader = csv.DictReader(f)
            for idx, r in enumerate(dict_reader, start=1):
                # 1. Filtre strict : Uniquement les panneaux actifs
                active_val = r.get('Active', '').strip().upper()
                if active_val != 'Y':
                    continue

                rem_id = r.get('Remorque', '').strip().replace('.0', '')
                if not rem_id:
                    continue

                # 2. Coordonnées GPS
                gps_str = r.get('GPS', '').strip()
                lat, lng = None, None
                if gps_str and ',' in gps_str:
                    try:
                        pts = gps_str.split(',')
                        lat = float(pts[0].strip())
                        lng = float(pts[1].strip())
                    except (ValueError, IndexError):
                        pass

                if lat is None or lng is None:
                    continue

                ville = r.get('Ville-remorque', '').strip()
                loc = r.get('Localisation-remorque', '').strip()
                axe = r.get('Axe-remorque', '').strip()
                dir_in = r.get('Direction-remorque', '').strip()
                dir_out = r.get('Direction-out', '').strip()
                province = r.get('Province', '').strip()
                commune = r.get('Commune', '').strip()
                code_route = r.get('Code_Route', '').strip()
                nom_route = r.get('Nom_Route', '').strip()

                # 3. Fréquentation journalière
                freq_raw = r.get('Frequentation_Moyenne_veh_jour', '').strip().replace(' ', '')
                freq_val = int(freq_raw) if freq_raw.isdigit() else None
                freq_fmt = f"{freq_val:,} véh./jour".replace(',', ' ') if freq_val else "Non renseignée"

                # 4. Photos (IN / OUT / Fallback)
                p_in = r.get('Photo-IN', '').strip()
                p_out = r.get('Photo-OUT', '').strip()

                def build_photo_url(p):
                    if not p: return ''
                    if p.startswith('http'): return p
                    if p.startswith('Photo/'):
                        return 'https://remorquepublicitaire.be/wp-content/uploads/' + urllib.parse.quote(p)
                    return ''

                photo_in_url = build_photo_url(p_in)
                photo_out_url = build_photo_url(p_out)

                # Photo principale
                main_photo = photo_in_url or photo_out_url
                if not main_photo and rem_id in TRAILER_PHOTO_FALLBACKS:
                    main_photo = TRAILER_PHOTO_FALLBACKS[rem_id]

                lien = r.get('Lien', '').strip()
                if not lien or not lien.startswith('http'):
                    lien = f"https://remorquepublicitaire.be/remorque/{rem_id}"

                trailers.append({
                    'id': rem_id,
                    'name': f"Remorque #{rem_id} - {ville}",
                    'lat': lat,
                    'lng': lng,
                    'ville': ville,
                    'localisation': loc,
                    'axe': axe,
                    'dir_in': dir_in,
                    'dir_out': dir_out,
                    'province': province,
                    'commune': commune,
                    'code_route': code_route,
                    'nom_route': nom_route,
                    'active': True,
                    'lien': lien,
                    'frequentation_jour': freq_val,
                    'frequentation_fmt': freq_fmt,
                    'photo_url': main_photo,
                    'photo_in': photo_in_url,
                    'photo_out': photo_out_url,
                    'indice_confiance': r.get('Indice_Confiance', '').strip(),
                    'score_impact': r.get('Score_Impact_Temps_Exposition', '').strip(),
                    'contexte_visibilite': r.get('Contexte_Visibilite', '').strip(),
                    'notes_troncon': r.get('Notes_Troncon', '').strip()
                })
        else:
            # Ancien format WKT (fallback de sécurité)
            f.seek(0)
            lines = f.readlines()
            for i, line in enumerate(lines[1:], start=2):
                line = line.strip()
                if not line: continue
                lat, lng = None, None
                wkt_m = re.match(r'^\"?POINT \(([\d\.-]+)\s+([\d\.-]+)\)\"?,(.*)', line)
                if wkt_m:
                    lng = float(wkt_m.group(1))
                    lat = float(wkt_m.group(2))
                    rest = wkt_m.group(3)
                else:
                    rest = line.lstrip(',')
                reader = csv.reader(io.StringIO(rest))
                row = next(reader, [])
                if not row or lat is None or lng is None: continue
                rem_id = row[0].strip().replace('.0', '') if len(row) > 0 else f"T{i}"
                ville = row[1].strip() if len(row) > 1 else ''
                trailers.append({
                    'id': rem_id,
                    'name': f"Remorque #{rem_id} - {ville}",
                    'lat': lat,
                    'lng': lng,
                    'ville': ville,
                    'localisation': row[2].strip() if len(row) > 2 else '',
                    'axe': row[3].strip() if len(row) > 3 else '',
                    'dir_in': row[4].strip() if len(row) > 4 else '',
                    'dir_out': row[5].strip() if len(row) > 5 else '',
                    'province': row[6].strip() if len(row) > 6 else '',
                    'active': True,
                    'lien': f"https://remorquepublicitaire.be/remorque/{rem_id}",
                    'frequentation_jour': None,
                    'frequentation_fmt': "Non renseignée",
                    'photo_url': TRAILER_PHOTO_FALLBACKS.get(rem_id, '')
                })

    return trailers

def load_client_locations(locations_path):
    """Charge les points d'intérêt d'un client (format CSV ou JSON)"""
    if not os.path.exists(locations_path):
        raise FileNotFoundError(f"Fichier de points d'intérêt introuvable : {locations_path}")

    locations = []
    if locations_path.endswith('.json'):
        with open(locations_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            if isinstance(raw, list):
                locations = raw
            elif isinstance(raw, dict) and 'locations' in raw:
                locations = raw['locations']
            elif isinstance(raw, dict) and 'properties' in raw:
                locations = raw['properties']
    else:
        # Format CSV
        with open(locations_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, r in enumerate(reader, start=1):
                # Normalisation des colonnes
                r_lower = {k.strip().lower(): v.strip() for k, v in r.items() if k}
                
                loc_id = r_lower.get('id') or r_lower.get('code') or str(idx)
                title = r_lower.get('nom') or r_lower.get('name') or r_lower.get('title') or r_lower.get('titre') or f"Lieu #{idx}"
                city = r_lower.get('ville') or r_lower.get('city') or r_lower.get('commune') or ''
                street = r_lower.get('rue') or r_lower.get('street') or r_lower.get('adresse') or r_lower.get('address') or ''
                category = r_lower.get('type') or r_lower.get('categorie') or r_lower.get('category') or 'Point de vente'
                status = r_lower.get('statut') or r_lower.get('status') or 'actif'
                url = r_lower.get('url') or r_lower.get('lien') or r_lower.get('site') or ''
                img = r_lower.get('image') or r_lower.get('photo') or r_lower.get('img') or ''
                desc = r_lower.get('description') or r_lower.get('desc') or ''
                
                lat = r_lower.get('latitude') or r_lower.get('lat')
                lng = r_lower.get('longitude') or r_lower.get('lng') or r_lower.get('lon')
                
                try:
                    lat = float(lat) if lat else None
                    lng = float(lng) if lng else None
                except ValueError:
                    lat, lng = None, None

                locations.append({
                    'id': loc_id,
                    'title': title,
                    'city': city,
                    'street': street,
                    'lat': lat,
                    'lng': lng,
                    'type': category,
                    'status': status,
                    'url': url,
                    'image': img,
                    'description': desc,
                    'raw_data': r
                })

    return locations

def process_cross_analysis(client_config, locations, trailers, geocode_missing=False):
    """
    Calcule les métriques de croisement complètes :
    - Distances vers chaque remorque
    - Rayons 5 km & 10 km
    - Taux de couverture global
    - Top remorques stratégiques
    """
    # 1. Géocodage si nécessaire
    if geocode_missing:
        for loc in locations:
            if loc['lat'] is None or loc['lng'] is None:
                addr_query = f"{loc.get('street', '')} {loc.get('city', '')}".strip()
                if addr_query:
                    lat, lng = geocode_address_nominatim(addr_query)
                    if lat and lng:
                        loc['lat'] = lat
                        loc['lng'] = lng

    valid_locations = [l for l in locations if l.get('lat') is not None and l.get('lng') is not None]
    
    # 2. Calcul proximité pour chaque point du client
    for loc in locations:
        if loc.get('lat') is None or loc.get('lng') is None:
            loc['nearest_trailer'] = None
            loc['trailers_within_5km'] = []
            loc['trailers_within_10km'] = []
            continue

        nearest = None
        min_dist = float('inf')
        t_5k = []
        t_10k = []
        t_20k = []

        for t in trailers:
            d = haversine_distance(loc['lat'], loc['lng'], t['lat'], t['lng'])
            if d is not None:
                item = {
                    'trailer_id': t['id'],
                    'ville': t['ville'],
                    'axe': t['axe'],
                    'distance_km': d
                }
                if d < min_dist:
                    min_dist = d
                    nearest = item
                if d <= 5.0:
                    t_5k.append(item)
                if d <= 10.0:
                    t_10k.append(item)
                if d <= 20.0:
                    t_20k.append(item)

        loc['nearest_trailer'] = nearest
        loc['trailers_within_5km'] = sorted(t_5k, key=lambda x: x['distance_km'])
        loc['trailers_within_10km'] = sorted(t_10k, key=lambda x: x['distance_km'])
        loc['trailers_within_20km'] = sorted(t_20k, key=lambda x: x['distance_km'])

    # 3. Calcul proximité pour chaque remorque Mmove
    for t in trailers:
        locs_5k = []
        locs_10k = []
        locs_20k = []

        for loc in valid_locations:
            d = haversine_distance(t['lat'], t['lng'], loc['lat'], loc['lng'])
            if d is not None:
                item = {
                    'id': loc['id'],
                    'title': loc['title'],
                    'city': loc.get('city', ''),
                    'type': loc.get('type', ''),
                    'status': loc.get('status', 'actif'),
                    'url': loc.get('url', ''),
                    'distance_km': d
                }
                if d <= 5.0:
                    locs_5k.append(item)
                if d <= 10.0:
                    locs_10k.append(item)
                if d <= 20.0:
                    locs_20k.append(item)

        t['nearby_locations'] = sorted(locs_20k, key=lambda x: x['distance_km'])
        t['locs_within_5km'] = len(locs_5k)
        t['locs_within_10km'] = len(locs_10k)
        t['locs_within_20km'] = len(locs_20k)
        # Compatibilité avec interface précédente
        t['props_within_5km'] = len(locs_5k)
        t['props_within_10km'] = len(locs_10k)
        t['props_within_20km'] = len(locs_20k)

    # 4. Statistiques globales
    total_locs = len(valid_locations)
    locs_5k_count = len([l for l in valid_locations if l.get('nearest_trailer') and l['nearest_trailer']['distance_km'] <= 5.0])
    locs_10k_count = len([l for l in valid_locations if l.get('nearest_trailer') and l['nearest_trailer']['distance_km'] <= 10.0])
    locs_20k_count = len([l for l in valid_locations if l.get('nearest_trailer') and l['nearest_trailer']['distance_km'] <= 20.0])
    
    cov_5k_pct = round((locs_5k_count / total_locs * 100), 1) if total_locs > 0 else 0
    cov_10k_pct = round((locs_10k_count / total_locs * 100), 1) if total_locs > 0 else 0
    cov_20k_pct = round((locs_20k_count / total_locs * 100), 1) if total_locs > 0 else 0

    all_dists = [l['nearest_trailer']['distance_km'] for l in valid_locations if l.get('nearest_trailer')]
    avg_dist = round(sum(all_dists) / len(all_dists), 2) if all_dists else 0

    trailers_with_5k = len([t for t in trailers if t['locs_within_5km'] >= 1])
    trailers_with_10k = len([t for t in trailers if t['locs_within_10km'] >= 1])
    trailers_with_20k = len([t for t in trailers if t['locs_within_20km'] >= 1])

    traffic_5k = sum(t['frequentation_jour'] for t in trailers if t['locs_within_5km'] >= 1 and t.get('frequentation_jour'))
    traffic_10k = sum(t['frequentation_jour'] for t in trailers if t['locs_within_10km'] >= 1 and t.get('frequentation_jour'))
    traffic_20k = sum(t['frequentation_jour'] for t in trailers if t['locs_within_20km'] >= 1 and t.get('frequentation_jour'))
    total_network_traffic = sum(t['frequentation_jour'] for t in trailers if t.get('frequentation_jour'))

    return {
        'config': client_config,
        'summary': {
            'total_locations': len(locations),
            'geolocated_locations': total_locs,
            'total_trailers': len(trailers),
            'locations_within_5km': locs_5k_count,
            'coverage_5km_pct': cov_5k_pct,
            'locations_within_10km': locs_10k_count,
            'coverage_10km_pct': cov_10k_pct,
            'locations_within_20km': locs_20k_count,
            'coverage_20km_pct': cov_20k_pct,
            'average_distance_km': avg_dist,
            'trailers_covering_5km': trailers_with_5k,
            'trailers_covering_10km': trailers_with_10k,
            'trailers_covering_20km': trailers_with_20k,
            'traffic_exposed_5km': traffic_5k,
            'traffic_exposed_10km': traffic_10k,
            'traffic_exposed_20km': traffic_20k,
            'total_network_traffic': total_network_traffic
        },
        'locations': locations,
        'trailers': trailers
    }
