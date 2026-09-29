#!/usr/bin/env python3
"""
Mmove Prospection Generator
Générateur automatisé de cartes interactives personnalisées pour les prospects Mmove.

Usage :
  python generator.py --client marjorie-thomas
  python generator.py --client exemple-automobile
  python generator.py --client exemple-retail
  python generator.py --all
"""

import os
import sys
import re
import json
import shutil
import argparse
from pathlib import Path

# Importer le moteur de croisement
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.engine import (
    parse_mmove_network,
    load_client_locations,
    process_cross_analysis
)

def build_client(client_dir, dist_base_dir, mmove_trailers, geocode=False):
    client_path = Path(client_dir)
    config_file = client_path / "config.json"
    
    if not config_file.exists():
        print(f"⚠️ Ignoré : config.json manquant dans {client_path}")
        return False

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    client_id = config.get("client_id", client_path.name)
    client_name = config.get("client_name", client_id)
    print(f"\n==========================================")
    print(f"🚀 Traitement du prospect : {client_name} ({client_id})")
    print(f"==========================================")

    # Trouver le fichier de données (locations.json ou locations.csv)
    loc_file = None
    for candidate in ["locations.json", "locations.csv"]:
        if (client_path / candidate).exists():
            loc_file = client_path / candidate
            break

    if not loc_file:
        print(f"❌ Erreur : aucun fichier locations.csv ou locations.json trouvé dans {client_path}")
        return False

    # Charger les POI et calculer le croisement
    locations = load_client_locations(str(loc_file))
    print(f"📍 {len(locations)} points d'intérêt chargés depuis {loc_file.name}")

    dataset = process_cross_analysis(config, locations, mmove_trailers, geocode_missing=geocode)
    summary = dataset['summary']

    print(f"📊 Résultats du croisement avec les {len(mmove_trailers)} remorques Mmove actives :")
    print(f"   • Couverture ≤ 5 km  : {summary['coverage_5km_pct']}% ({summary['locations_within_5km']} / {summary['geolocated_locations']})")
    print(f"   • Couverture ≤ 10 km : {summary['coverage_10km_pct']}% ({summary['locations_within_10km']} / {summary['geolocated_locations']})")
    print(f"   • Couverture ≤ 20 km : {summary.get('coverage_20km_pct', 0)}% ({summary.get('locations_within_20km', 0)} / {summary['geolocated_locations']})")
    print(f"   • Distance moyenne au panneau le plus proche : {summary['average_distance_km']} km")
    print(f"   • Remorques Mmove actives couvrant ce client : {summary['trailers_covering_10km']} panneaux (≤10km) / {summary.get('trailers_covering_20km', 0)} panneaux (≤20km)")

    # Préparer le dossier de sortie dans dist/
    out_dir = Path(dist_base_dir) / client_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copier le logo Mmove
    logo_src = BASE_DIR / "core" / "template" / "logo-mmove.png"
    if logo_src.exists():
        shutil.copy(logo_src, out_dir / "logo-mmove.png")

    # Sauvegarder data.json
    data_json_path = out_dir / "data.json"
    with open(data_json_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    # Lire le template HTML et injecter APP_DATA directement
    template_html_path = BASE_DIR / "core" / "template" / "index.html"
    with open(template_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Injection propre de APP_DATA dans la balise script
    injected_js = f"window.APP_DATA = {json.dumps(dataset, ensure_ascii=False)};"
    html_content = re.sub(
        r'//\s*window\.APP_DATA will be injected here during standalone export',
        lambda m: injected_js,
        html_content
    )

    out_html = out_dir / "index.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✅ Déploiement généré avec succès dans :")
    print(f"   file://{out_html.resolve()}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Générateur de cartes de prospection commerciale Mmove")
    parser.add_argument("--client", type=str, help="Identifiant ou dossier du client dans clients/ (ex: marjorie-thomas)")
    parser.add_argument("--all", action="store_true", help="Générer tous les clients présents dans clients/")
    parser.add_argument("--geocode", action="store_true", help="Activer le géocodage automatique des adresses sans coordonnées GPS")
    args = parser.parse_args()

    mmove_csv = BASE_DIR / "core" / "mmove_network.csv"
    if not mmove_csv.exists():
        print(f"❌ Erreur : base Mmove introuvable ({mmove_csv})")
        sys.exit(1)

    print("🔌 Chargement du réseau officiel des remorques Mmove...")
    mmove_trailers = parse_mmove_network(str(mmove_csv))
    print(f"✅ {len(mmove_trailers)} remorques Mmove opérationnelles prêtes pour le croisement.")

    dist_dir = BASE_DIR / "dist"
    clients_dir = BASE_DIR / "clients"

    if args.all:
        for c in sorted(clients_dir.iterdir()):
            if c.is_dir() and not c.name.startswith("_"):
                build_client(c, dist_dir, mmove_trailers, geocode=args.geocode)
    elif args.client:
        target = clients_dir / args.client
        if not target.exists():
            print(f"❌ Dossier client introuvable : {target}")
            sys.exit(1)
        build_client(target, dist_dir, mmove_trailers, geocode=args.geocode)
    else:
        print("💡 Précisez un client avec `--client <nom>` ou utilisez `--all` pour tout générer.")
        parser.print_help()

if __name__ == "__main__":
    main()
