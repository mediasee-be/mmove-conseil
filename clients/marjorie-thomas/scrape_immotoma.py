import urllib.request
import re
import csv
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calcul distance en kilomètres entre 2 coordonnées GPS (formule de Haversine)"""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    R = 6371.0 # Rayon moyen de la terre en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def fetch_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Erreur fetch {url}: {e}")
        return None

def clean_price(price_str):
    if not price_str:
        return None
    digits = re.sub(r'[^\d]', '', price_str)
    return int(digits) if digits else None

def get_listings_from_catalog():
    properties = []
    print("Scraping du catalogue immotoma.be/fr/a-vendre...")
    for page in range(1, 11):
        url = f"https://immotoma.be/fr/a-vendre?filter=1&page={page}"
        html = fetch_url(url)
        if not html:
            continue
        cards = re.findall(r'(<a [^>]*class=\"carte[^\"]*\"[^>]*>.*?</a>)', html, re.DOTALL)
        print(f"Page {page}: {len(cards)} cartes trouvées")
        for c in cards:
            m_cls = re.search(r'class=\"([^\"]+)\"', c)
            cls = m_cls.group(1) if m_cls else ''
            
            # EXCLURE LES VENDUS STRICTEMENT
            if 'carte--vendu' in cls:
                continue
                
            status = 'actif'
            if 'carte--sous-option' in cls:
                status = 'sous-option'
                
            m_href = re.search(r'href=\"([^\"]+)\"', c)
            href = m_href.group(1) if m_href else ''
            
            m_id = re.search(r'/bien/(\d+)/', href)
            prop_id = m_id.group(1) if m_id else ''
            
            m_title = re.search(r'carte_title\">\s*([^<]+)', c)
            title = m_title.group(1).strip() if m_title else ''
            
            m_price = re.search(r'carte_price[^\"]*\">\s*([^<]+)', c)
            price_raw = m_price.group(1).strip() if m_price else ''
            
            m_city = re.search(r'carte_adresse\">\s*([^<]+)', c)
            city = m_city.group(1).strip().capitalize() if m_city else ''
            
            m_img = re.search(r'background-image\s*:\s*url\((https://[^\)]+)\)', c)
            card_img = m_img.group(1) if m_img else ''
            
            m_peb = re.search(r'PEB_([A-G])\.svg', c)
            peb = m_peb.group(1) if m_peb else None
            
            m_ch = re.search(r'(\d+)\s*Ch\.', c)
            bedrooms = int(m_ch.group(1)) if m_ch else None
            has_garage = 'garage.png' in c
            has_jardin = 'jardin.png' in c
            has_terrasse = 'terasse.png' in c
            
            properties.append({
                'id': prop_id,
                'url': href,
                'status': status,
                'title': title,
                'price_raw': price_raw,
                'price': clean_price(price_raw),
                'city': city,
                'image': card_img,
                'peb': peb,
                'bedrooms': bedrooms,
                'has_garage': has_garage,
                'has_jardin': has_jardin,
                'has_terrasse': has_terrasse,
                'lat': None,
                'lng': None,
                'street': '',
                'surface': None,
                'bathrooms': None,
                'type': title,
                'description': ''
            })
            
    print(f"Total des biens à vendre retenus (hors vendus) : {len(properties)}")
    return properties

def enrich_property_detail(prop):
    html = fetch_url(prop['url'])
    if not html:
        return prop
    
    gx = re.search(r'data-GoogleX=\"([^\"]+)\"', html)
    gy = re.search(r'data-GoogleY=\"([^\"]+)\"', html)
    if gx and gy:
        try:
            prop['lat'] = float(gx.group(1))
            prop['lng'] = float(gy.group(1))
        except ValueError:
            pass
            
    m_pic = re.search(r'data-MediumPictureItemUrl=\"([^\"]+)\"', html)
    if m_pic and m_pic.group(1):
        prop['image'] = m_pic.group(1)
        
    t_desc = re.search(r'data-TypeDescription=\"([^\"]+)\"', html)
    if t_desc and t_desc.group(1):
        prop['type'] = t_desc.group(1)
        
    surf = re.search(r'data-SurfaceTotal=\"([^\"]+)\"', html)
    if surf and surf.group(1):
        try:
            s = float(surf.group(1))
            if s > 0:
                prop['surface'] = round(s, 1)
        except ValueError:
            pass
            
    beds = re.search(r'data-NumberOfBedRooms=\"([^\"]+)\"', html)
    if beds and beds.group(1):
        try:
            b = int(beds.group(1))
            if b > 0:
                prop['bedrooms'] = b
        except ValueError:
            pass

    baths = re.search(r'data-NumberOfBathRooms=\"([^\"]+)\"', html)
    if baths and baths.group(1):
        try:
            ba = int(baths.group(1))
            if ba > 0:
                prop['bathrooms'] = ba
        except ValueError:
            pass
            
    street_m = re.search(r'<span[^>]*class=\"inline font_text text--xl color_dark bold upper\">\s*([^<]+)', html)
    if street_m:
        street_clean = re.sub(r'\s+', ' ', street_m.group(1)).strip()
        prop['street'] = street_clean
        
    city_m = re.search(r'<span[^>]*class=\"inline font_text text--xl color_dark bold\">\s*([^<]+)', html)
    if city_m and not prop['city']:
        prop['city'] = city_m.group(1).strip().capitalize()
        
    desc_m = re.search(r'<p class=\"text--lg\">\s*([^<]+)', html)
    if desc_m:
        prop['description'] = re.sub(r'\s+', ' ', desc_m.group(1)).strip()[:350] + '...'
        
    # Agence de référence
    if 'charleroi' in prop['url'].lower() or 'charleroi' in prop['city'].lower():
        prop['agency_hint'] = 'Charleroi'
    elif 'tamines' in prop['url'].lower() or 'tamines' in prop['city'].lower():
        prop['agency_hint'] = 'Tamines'
    elif 'fosses' in prop['url'].lower() or 'fosses' in prop['city'].lower():
        prop['agency_hint'] = 'Fosses-la-Ville'
    else:
        prop['agency_hint'] = 'Toma Immobilier'
        
    return prop

def parse_mmove_csv(csv_path):
    print("Parsing des remorques publicitaires Mmove...")
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    trailers = []
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
            
        lat = None
        lng = None
        wkt_m = re.match(r'^\"?POINT \(([\d\.-]+)\s+([\d\.-]+)\)\"?,(.*)', line)
        if wkt_m:
            lng = float(wkt_m.group(1))
            lat = float(wkt_m.group(2))
            rest = wkt_m.group(3)
        else:
            rest = line.lstrip(',')
            
        reader = csv.reader(io.StringIO(rest))
        row = next(reader)
        
        rem_id = row[0].strip().replace('.0', '') if len(row) > 0 else f"T{i}"
        ville = row[1].strip() if len(row) > 1 else ''
        loc = row[2].strip() if len(row) > 2 else ''
        axe = row[3].strip() if len(row) > 3 else ''
        dir_in = row[4].strip() if len(row) > 4 else ''
        dir_out = row[5].strip() if len(row) > 5 else ''
        province = row[6].strip() if len(row) > 6 else ''
        
        active_status = 'Y'
        for col in row:
            if col.strip() in ['Y', 'N']:
                active_status = col.strip()
                break
                
        lien = f"https://remorquepublicitaire.be/remorque/{rem_id}"
        for col in reversed(row):
            if col.strip().startswith('http'):
                lien = col.strip()
                break
                
        if lat is not None and lng is not None:
            trailers.append({
                'id': rem_id,
                'name': f"Remorque Mmove #{rem_id} - {ville}",
                'lat': lat,
                'lng': lng,
                'ville': ville,
                'localisation': loc,
                'axe': axe,
                'dir_in': dir_in,
                'dir_out': dir_out,
                'province': province,
                'active': active_status == 'Y',
                'lien': lien
            })
            
    print(f"Total remorques Mmove avec coordonnées GPS : {len(trailers)}")
    return trailers

def compute_proximity(properties, trailers):
    print("Calcul du croisement et des distances de proximité (5 km et 10 km)...")
    for p in properties:
        if p['lat'] is None or p['lng'] is None:
            p['nearest_trailer'] = None
            p['trailers_within_5km'] = []
            p['trailers_within_10km'] = []
            continue
            
        nearest = None
        min_dist = float('inf')
        t_5k = []
        t_10k = []
        
        for t in trailers:
            d = haversine_distance(p['lat'], p['lng'], t['lat'], t['lng'])
            if d is not None:
                if d < min_dist:
                    min_dist = d
                    nearest = {
                        'trailer_id': t['id'],
                        'ville': t['ville'],
                        'axe': t['axe'],
                        'distance_km': d
                    }
                if d <= 5.0:
                    t_5k.append({
                        'trailer_id': t['id'],
                        'ville': t['ville'],
                        'axe': t['axe'],
                        'distance_km': d
                    })
                if d <= 10.0:
                    t_10k.append({
                        'trailer_id': t['id'],
                        'ville': t['ville'],
                        'axe': t['axe'],
                        'distance_km': d
                    })
                    
        p['nearest_trailer'] = nearest
        p['trailers_within_5km'] = sorted(t_5k, key=lambda x: x['distance_km'])
        p['trailers_within_10km'] = sorted(t_10k, key=lambda x: x['distance_km'])
        
    for t in trailers:
        props_5k = []
        props_10k = []
        for p in properties:
            if p['lat'] is None or p['lng'] is None:
                continue
            d = haversine_distance(t['lat'], t['lng'], p['lat'], p['lng'])
            if d is not None:
                item = {
                    'prop_id': p['id'],
                    'title': p['title'],
                    'city': p['city'],
                    'price': p['price'],
                    'price_raw': p['price_raw'],
                    'status': p['status'],
                    'url': p['url'],
                    'distance_km': d
                }
                if d <= 5.0:
                    props_5k.append(item)
                if d <= 10.0:
                    props_10k.append(item)
                    
        t['nearby_properties'] = sorted(props_10k, key=lambda x: x['distance_km'])
        t['props_within_5km'] = len(props_5k)
        t['props_within_10km'] = len(props_10k)

def main():
    props = get_listings_from_catalog()
    
    print(f"Enrichissement des coordonnées GPS des {len(props)} biens...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        enriched_props = list(executor.map(enrich_property_detail, props))
        
    # Geocode default for Courcelles if missing
    for p in enriched_props:
        if p['id'] == '25795' and p['lat'] is None:
            p['lat'] = 50.4608
            p['lng'] = 4.3752
            p['street'] = 'Courcelles (centre)'

    valid_coords = [p for p in enriched_props if p['lat'] is not None and p['lng'] is not None]
    print(f"Biens géolocalisés avec succès : {len(valid_coords)} / {len(enriched_props)}")
    
    trailers = parse_mmove_csv('mmove_remorques.csv')
    
    compute_proximity(enriched_props, trailers)
    
    output_data = {
        'metadata': {
            'generated_at': '2026-09-16T15:40:00+02:00',
            'agency': 'Marjorie Thomas (Immo Toma)',
            'agency_url': 'https://immotoma.be/fr/a-vendre',
            'source_mmove': 'Panneaux publicitaires Mmove (https://remorquepublicitaire.be/)',
            'total_properties': len(enriched_props),
            'geolocated_properties': len(valid_coords),
            'total_trailers': len(trailers),
            'active_properties_count': len([p for p in enriched_props if p['status'] == 'actif']),
            'sous_option_properties_count': len([p for p in enriched_props if p['status'] == 'sous-option'])
        },
        'properties': enriched_props,
        'trailers': trailers
    }
    
    with open('map_data.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    js_content = 'window.MAP_DATA = ' + json.dumps(output_data, ensure_ascii=False) + ';'
    with open('data.js', 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    print("Sauvegarde terminée dans map_data.json et data.js !")

if __name__ == '__main__':
    main()
