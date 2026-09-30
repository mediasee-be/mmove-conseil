import os
import io
import math
import hashlib
import urllib.request
import ssl
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAPS_DIR = os.path.join(BASE_DIR, "data", "maps")
os.makedirs(MAPS_DIR, exist_ok=True)

def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return (xtile, ytile)

def num2deg(xtile: float, ytile: float, zoom: int) -> Tuple[float, float]:
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)

def _get_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("Arial", size)
    except Exception:
        return ImageFont.load_default()

class MapGeneratorService:
    """Générateur de cartes géographiques haute définition pour les plans média M Move."""

    def __init__(self, cache_dir: str = MAPS_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.ssl_ctx = ssl._create_unverified_context()

    def generate_campaign_map(
        self,
        panels: List[Dict[str, Any]],
        period_str: str = "campaign",
        width: int = 1300,
        height: int = 880
    ) -> str:
        """
        Génère une carte PNG haute définition (Retina 2x) avec les épingles numérotées et lissées des emplacements.
        Retourne le chemin d'accès absolu du fichier PNG.
        """
        valid_points = []
        for idx, p in enumerate(panels, 1):
            try:
                lat = float(p.get("lat") or 0)
                lng = float(p.get("lng") or 0)
                if lat != 0 and lng != 0:
                    valid_points.append({
                        "num": idx,
                        "id": str(p.get("id")),
                        "lat": lat,
                        "lng": lng,
                        "label": f"#{p.get('id')}"
                    })
            except (ValueError, TypeError):
                continue

        if not valid_points:
            # Image vide de secours
            blank = Image.new("RGB", (width, height), (245, 245, 245))
            d = ImageDraw.Draw(blank)
            font_fallback = _get_font(28)
            d.text((width // 4, height // 2), "Carte non disponible", fill=(100, 100, 100), font=font_fallback)
            fallback_path = os.path.join(self.cache_dir, f"map_empty_{period_str}.png")
            blank.save(fallback_path)
            return fallback_path

        # Clé de cache déterministe (v4hd pour forcer le recalcul avec marge de sécurité des pastilles)
        ids_key = "_".join(f"{p['id']}_{p['lat']:.4f}_{p['lng']:.4f}" for p in valid_points)
        h = hashlib.md5(f"v4hd_{period_str}_{width}_{height}_{ids_key}".encode("utf-8")).hexdigest()[:12]
        file_path = os.path.join(self.cache_dir, f"map_{period_str}_{h}.png")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 15000:
            return file_path

        lats = [p["lat"] for p in valid_points]
        lngs = [p["lng"] for p in valid_points]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)
        center_lat = (min_lat + max_lat) / 2.0
        center_lng = (min_lng + max_lng) / 2.0

        # Calcul automatique du zoom adapté garantissant que TOUTES les épingles et leurs badges ont au moins 65px de marge
        # Le marqueur a un rayon r=24 et son badge descend jusqu'à y + r + 30
        pad_x = 70
        pad_top = 50
        pad_bot = 70

        best_zoom = 9
        for candidate_zoom in range(15, 7, -1):
            c_x, c_y = deg2num(center_lat, center_lng, candidate_zoom)
            c_px_x = c_x * 256
            c_px_y = c_y * 256
            l_px = c_px_x - width / 2
            t_px = c_px_y - height / 2

            all_fit = True
            for p in valid_points:
                px, py = deg2num(p["lat"], p["lng"], candidate_zoom)
                pt_x = px * 256 - l_px
                pt_y = py * 256 - t_px
                if not (pad_x <= pt_x <= width - pad_x and pad_top <= pt_y <= height - pad_bot):
                    all_fit = False
                    break
            if all_fit:
                best_zoom = candidate_zoom
                break

        zoom = best_zoom

        center_x, center_y = deg2num(center_lat, center_lng, zoom)
        center_px_x = center_x * 256
        center_px_y = center_y * 256

        left_px = center_px_x - width / 2
        top_px = center_px_y - height / 2
        right_px = left_px + width
        bottom_px = top_px + height

        min_tile_x = int(left_px // 256)
        max_tile_x = int(right_px // 256)
        min_tile_y = int(top_px // 256)
        max_tile_y = int(bottom_px // 256)

        canvas_w = (max_tile_x - min_tile_x + 1) * 256
        canvas_h = (max_tile_y - min_tile_y + 1) * 256
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (240, 240, 240, 255))

        # Assemblage des tuiles OSM
        for tx in range(min_tile_x, max_tile_x + 1):
            for ty in range(min_tile_y, max_tile_y + 1):
                url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
                req = urllib.request.Request(url, headers={"User-Agent": "MmoveApp/1.0 (info@mediasee.be)"})
                try:
                    with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=3) as res:
                        tile_img = Image.open(io.BytesIO(res.read())).convert("RGBA")
                        px = (tx - min_tile_x) * 256
                        py = (ty - min_tile_y) * 256
                        canvas.paste(tile_img, (px, py))
                except Exception:
                    pass

        crop_x = int(left_px - min_tile_x * 256)
        crop_y = int(top_px - min_tile_y * 256)
        map_img = canvas.crop((crop_x, crop_y, crop_x + width, crop_y + height))

        # Overlay transparent pour rendu ultra net et anti-crénelé des pastilles
        pin_overlay = Image.new("RGBA", map_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(pin_overlay)

        font_num = _get_font(24)
        font_lbl = _get_font(15)

        for p in valid_points:
            px, py = deg2num(p["lat"], p["lng"], zoom)
            x = int(px * 256 - left_px)
            y = int(py * 256 - top_px)

            r = 24
            # Ombre portée douce
            draw.ellipse([x - r + 3, y - r + 5, x + r + 3, y + r + 5], fill=(30, 41, 59, 90))
            # Cercle principal orange M Move avec contour blanc
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(244, 146, 13, 255), outline=(255, 255, 255, 255), width=3)

            # Numéro d'ordre (1, 2, 3...) centré optiquement au pixel près
            num_str = str(p["num"])
            n_bbox = font_num.getbbox(num_str)
            nw = n_bbox[2] - n_bbox[0]
            nh = n_bbox[3] - n_bbox[1]
            draw.text((x - nw / 2 - n_bbox[0], y - nh / 2 - n_bbox[1]), num_str, fill=(255, 255, 255, 255), font=font_num)

            # Badge ID (#323) arrondi moderne
            lbl = p["label"]
            l_bbox = font_lbl.getbbox(lbl)
            lw = (l_bbox[2] - l_bbox[0]) + 16
            lh = (l_bbox[3] - l_bbox[1]) + 8
            badge_rect = [x - lw // 2, y + r + 4, x + lw // 2, y + r + 4 + lh]
            # Ombre du badge
            draw.rounded_rectangle([badge_rect[0] + 2, badge_rect[1] + 3, badge_rect[2] + 2, badge_rect[3] + 3], radius=5, fill=(30, 41, 59, 80))
            # Corps du badge
            draw.rounded_rectangle(badge_rect, radius=5, fill=(15, 23, 42, 245), outline=(255, 255, 255, 220), width=1)
            draw.text((x - (l_bbox[2] - l_bbox[0]) / 2 - l_bbox[0], y + r + 4 + (lh - (l_bbox[3] - l_bbox[1])) / 2 - l_bbox[1]), lbl, fill=(255, 255, 255, 255), font=font_lbl)

        final_img = Image.alpha_composite(map_img, pin_overlay).convert("RGB")
        final_img.save(file_path, "PNG", optimize=True)
        return file_path
