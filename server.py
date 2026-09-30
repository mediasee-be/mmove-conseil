"""
M Move Multi-Agent HTTP Server
Serveur API local autonome (sans dépendances externes)
Expose les endpoints :
- POST /api/chat : pipeline multi-agents complet
- GET /api/health : statut du réseau M Move
- GET / : interface web de démonstration
"""

import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from core.agents.coordinator import CoordinatorAgent

PORT = int(os.environ.get("PORT", 8080))
coordinator = CoordinatorAgent()

class MmoveHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_HEAD(self):
        self._set_headers(200, "text/html; charset=utf-8")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        req_path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        if req_path == "/api/health":
            self._set_headers(200)
            sync_info = coordinator.sync.get_summary()
            trailers_count = len(coordinator.engine.trailers)
            faces_count = trailers_count * 2
            res = {
                "status": "ok",
                "trailers_count": trailers_count,
                "panneaux_count": trailers_count,
                "faces_count": faces_count,
                "geocache_entries": len(coordinator.engine.geocache),
                "synchronisation": sync_info
            }
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if req_path == "/api/sync/status":
            self._set_headers(200)
            sync_info = coordinator.sync.get_summary()
            self.wfile.write(json.dumps(sync_info, ensure_ascii=False).encode("utf-8"))
            return

        # Configuration de l'authentification Google
        if req_path == "/api/auth/config":
            self._set_headers(200)
            cfg = {
                "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "")
            }
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
            return

        # Référentiel des commerciaux (Réservé aux Administrateurs pour les filtres)
        if req_path.startswith("/api/salespeople"):
            user_id = query_params.get("user_id", [None])[0]

            self._set_headers(200)
            if user_id and coordinator.salesperson_service.is_admin(user_id):
                sp_list = coordinator.salesperson_service.get_all()
            elif user_id:
                sp_list = [coordinator.salesperson_service.get(user_id)]
            else:
                sp_list = []
            self.wfile.write(json.dumps(sp_list, ensure_ascii=False).encode("utf-8"))
            return

        # Liste des dossiers (filtrée par droits commerciaux ou vue globale admin)
        if req_path.startswith("/api/dossiers"):
            user_id = query_params.get("user_id", [None])[0]
            filter_sp = query_params.get("filter", [None])[0]

            self._set_headers(200)
            dossiers = coordinator.dossier_service.list_dossiers(
                requesting_user_id=user_id,
                filter_salesperson=filter_sp
            )
            self.wfile.write(json.dumps(dossiers, ensure_ascii=False).encode("utf-8"))
            return

        # Suppression d'un dossier
        if req_path == "/api/dossier/delete":
            dossier_id = query_params.get("id", [None])[0]
            user_id = query_params.get("user_id", [None])[0]
            if not dossier_id:
                self._set_headers(400)
                self.wfile.write(b'{"error": "Dossier ID required"}')
                return
            ok = coordinator.dossier_service.delete_dossier(dossier_id, requesting_user_id=user_id)
            if ok:
                self._set_headers(200)
                self.wfile.write(b'{"success": true, "message": "Dossier supprime"}')
            else:
                self._set_headers(403)
                self.wfile.write(b'{"error": "Impossible de supprimer ce dossier ou droits insuffisants"}')
            return

        # Détail d'un dossier spécifique pour rechargement
        if req_path == "/api/dossier":
            dossier_id = query_params.get("id", [None])[0]
            user_id = query_params.get("user_id", [None])[0]

            if not dossier_id:
                self._set_headers(400)
                self.wfile.write(b'{"error": "Dossier ID required"}')
                return

            dossier = coordinator.dossier_service.get_dossier(dossier_id, requesting_user_id=user_id)
            if not dossier:
                self._set_headers(404)
                self.wfile.write(b'{"error": "Dossier non trouve ou acces non autorise"}')
            # Charger explicitement le dossier dans le coordinateur (quitte le dossier en cours)
            coordinator.load_dossier(dossier, salesperson_id=user_id)

            self._set_headers(200)
            self.wfile.write(json.dumps(dossier, ensure_ascii=False).encode("utf-8"))
            return

        if req_path == "/api/context/reset":
            user_id = query_params.get("user_id", [None])[0]
            coordinator.reset_context(salesperson_id=user_id)
            self._set_headers(200)
            self.wfile.write(b'{"status": "ok", "message": "Contexte reinitialise"}')
            return

        if req_path == "/api/network-trailers":
            self._set_headers(200)
            network = []
            trailers_iterable = coordinator.engine.trailers.values() if isinstance(coordinator.engine.trailers, dict) else coordinator.engine.trailers
            for t in trailers_iterable:
                if t.get("lat") and t.get("lng"):
                    network.append({
                        "id": str(t.get("id", "")),
                        "ville": t.get("ville", ""),
                        "axe_routier": t.get("axe_routier", ""),
                        "lat": t.get("lat"),
                        "lng": t.get("lng"),
                        "frequentation": t.get("frequentation_jour"),
                        "photo": t.get("photo_in") or t.get("photo_out") or t.get("photo_url", ""),
                        "lien": t.get("lien", "")
                    })
            self.wfile.write(json.dumps(network, ensure_ascii=False).encode("utf-8"))
            return

        # Cartes géographiques haute définition générées pour les campagnes
        if req_path.startswith("/api/map/"):
            filename = os.path.basename(req_path)
            map_path = os.path.join("data", "maps", filename)
            if os.path.exists(map_path) and os.path.isfile(map_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(map_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"Carte non trouvee")
                return

        # Téléchargement du Plan Média PDF ou Catalogue de Disponibilités (A4 Paysage)
        if req_path in ["/api/download-plan-pdf", "/api/download-availability-pdf"] or req_path.startswith("/api/pdf/"):
            filename = query_params.get("file", [None])[0]
            if not filename:
                filename = os.path.basename(req_path)
            
            clean_filename = os.path.basename(filename)
            pdf_path = os.path.join("data", "pdf", clean_filename)
            if os.path.exists(pdf_path) and os.path.isfile(pdf_path):
                # Enregistrer le dossier commercial à ce moment précis si ce n'est pas déjà fait
                coordinator.save_pending_dossier_on_download(clean_filename)

                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'inline; filename="{clean_filename}"')
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(pdf_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"Fichier PDF non trouve")
                return

        # Fichiers statiques (images, logos, avatars)
        if req_path.startswith("/static/"):
            rel_path = req_path.lstrip("/")
            # Sécurité anti-traversal
            clean_path = os.path.normpath(rel_path)
            if clean_path.startswith("static/") and os.path.exists(clean_path) and os.path.isfile(clean_path):
                content_type = "application/octet-stream"
                if clean_path.endswith(".png"):
                    content_type = "image/png"
                elif clean_path.endswith(".jpg") or clean_path.endswith(".jpeg"):
                    content_type = "image/jpeg"
                elif clean_path.endswith(".webp"):
                    content_type = "image/webp"
                elif clean_path.endswith(".svg"):
                    content_type = "image/svg+xml"
                
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(clean_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"Fichier non trouve")
                return

        if req_path == "/favicon.ico":
            icon_path = "static/bot-avatar.png"
            if os.path.exists(icon_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(icon_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        # Interface Web interactive locale (supporte /, /?, /index.html, etc.)
        if req_path in ("", "/", "/index.html"):
            self._set_headers(200, "text/html; charset=utf-8")
            html_content = """<!DOCTYPE html>
<html lang="fr" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M Move - Conseil en Affichage 8m²</title>
    <!-- Favicon Bot Avatar -->
    <link rel="icon" type="image/png" href="/static/bot-avatar.png">
    <!-- Google Fonts: Plus Jakarta Sans & Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
                    },
                    colors: {
                        mmove: {
                            primary: '#F4920D',
                            secondary: '#FF5B34',
                            orange: '#F4920D',
                            coral: '#FF5B34',
                            text: '#666666',
                            dark: '#1E2229'
                        }
                    }
                }
            }
        }
    </script>
    <!-- Font Awesome 6 -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- Marked.js for Markdown Rendering -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <!-- Google Identity Services (OAuth 2.0 / Sign In with Google) -->
    <script src="https://accounts.google.com/gsi/client" async defer></script>
    <!-- Leaflet CSS & JS for Interactive Map -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <style>
        body {
            color: #666666;
        }
        .dark body {
            color: #cbd5e1;
        }
        .leaflet-div-icon {
            background: transparent;
            border: none;
        }
        .map-pin-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            cursor: pointer;
            transform-origin: 20px 15px;
            transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .map-pin-container:hover {
            transform: scale(1.15);
            z-index: 9999 !important;
        }
        .map-pin-circle {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: linear-gradient(135deg, #F4920D 0%, #FF5B34 100%);
            color: white;
            font-weight: 800;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px solid white;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35);
        }
        .map-pin-badge {
            background: #1E293B;
            color: #F8FAFC;
            font-size: 9px;
            font-weight: 700;
            padding: 1px 5px;
            border-radius: 4px;
            margin-top: -3px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            white-space: nowrap;
        }
        .map-dot-network {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: #F4920D;
            border: 1.5px solid white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            cursor: pointer;
            opacity: 0.65;
            transition: all 0.15s ease;
        }
        .map-dot-network:hover {
            transform: scale(1.6);
            opacity: 1;
            background: #FF5B34;
        }
        .dark .leaflet-tile {
            filter: brightness(0.7) invert(1) contrast(1.1) hue-rotate(200deg) saturate(0.35);
        }
        .leaflet-popup-content-wrapper {
            border-radius: 16px;
            padding: 4px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2);
        }
        .dark .leaflet-popup-content-wrapper {
            background: #0f172a;
            color: #f1f5f9;
            border: 1px solid #334155;
        }
        .dark .leaflet-popup-tip {
            background: #0f172a;
        }
        .logo-text {
            fill: #4f4f50;
            transition: fill 0.2s ease;
        }
        .dark .logo-text {
            fill: #ffffff;
        }
        .markdown-body {
            line-height: 1.6;
            font-size: 0.925rem;
            color: #555555;
        }
        .dark .markdown-body {
            color: #e2e8f0;
        }
        .markdown-body h1, .markdown-body h2, .markdown-body h3 {
            font-weight: 700;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            color: #F4920D;
        }
        .dark .markdown-body h1, .dark .markdown-body h2, .dark .markdown-body h3 {
            color: #F4920D;
        }
        .markdown-body ul {
            list-style-type: disc;
            margin-left: 1.25rem;
            margin-bottom: 0.75rem;
        }
        .markdown-body ol {
            list-style-type: decimal;
            margin-left: 1.25rem;
            margin-bottom: 0.75rem;
        }
        .markdown-body li {
            margin-bottom: 0.25rem;
        }
        .markdown-body strong {
            font-weight: 700;
            color: #222222;
        }
        .dark .markdown-body strong {
            color: #ffffff;
        }
        .markdown-body p {
            margin-bottom: 0.75rem;
        }
        .markdown-body p:last-child {
            margin-bottom: 0;
        }
        .markdown-body a {
            color: #F4920D;
            text-decoration: underline;
            font-weight: 600;
            transition: color 0.15s ease;
        }
        .markdown-body a:hover {
            color: #FF5B34;
        }
        .dark .markdown-body a {
            color: #F4920D;
        }
        .dark .markdown-body a:hover {
            color: #FF5B34;
        }
        /* Bouton PDF dans le chat et volet : Texte blanc impératif */
        .markdown-body a.btn-pdf,
        .dark .markdown-body a.btn-pdf,
        a.btn-pdf,
        a.btn-pdf *,
        .btn-pdf span,
        .btn-pdf i {
            color: #ffffff !important;
            text-decoration: none !important;
        }
        .markdown-body a.btn-pdf:hover,
        .dark .markdown-body a.btn-pdf:hover,
        a.btn-pdf:hover {
            color: #ffffff !important;
            text-decoration: none !important;
            filter: brightness(1.1);
        }
        .markdown-body hr {
            border-color: #e2e8f0;
            margin: 1rem 0;
        }
        .dark .markdown-body hr {
            border-color: #334155;
        }
        .no-scrollbar::-webkit-scrollbar {
            display: none;
        }
        .no-scrollbar {
            -ms-overflow-style: none;
            scrollbar-width: none;
        }
    </style>
</head>
<body class="bg-slate-50 dark:bg-slate-950 text-[#666] dark:text-slate-300 flex flex-col h-screen font-sans transition-colors duration-200">
    <!-- HEADER -->
    <header class="h-[60px] bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 px-4 flex items-center justify-between shadow-xs z-10 shrink-0">
        <div class="flex items-center space-x-3 md:space-x-4">
            <!-- Logo officiel M Move SVG -->
            <a href="/" class="flex items-center shrink-0 hover:opacity-95 transition" title="M Move">
                <svg class="h-8 md:h-9 w-auto" viewBox="214 219 415 160" xmlns="http://www.w3.org/2000/svg">
                    <g>
                        <path fill="#F4920D" d="M372.52,298.08c0,43.58-35.33,78.9-78.9,78.9s-78.9-35.33-78.9-78.9,35.33-78.9,78.9-78.9,78.9,35.33,78.9,78.9"/>
                        <path fill="#fff" d="M302.08,355.13h-11.15v-97.6c0-3.99-1.99-5.58-5.18-5.58s-6.38,1-10.16,3.79v99.39h-11.15v-112.54h11.15v4.78c2.99-3.19,7.17-5.98,13.35-5.98,5.78,0,9.56,2.39,11.55,6.38,3.98-3.39,8.76-6.38,15.14-6.38,8.56,0,12.95,5.18,12.95,13.74v99.99h-11.15v-97.6c0-3.99-1.79-5.58-5.18-5.58-3.19,0-6.38,1-10.16,3.79v99.39Z"/>
                        <path class="logo-text" d="M460.51,355.13h-11.15v-97.6c0-3.99-1.99-5.58-5.18-5.58s-6.38,1-10.16,3.79v99.39h-11.15v-112.54h11.15v4.78c2.99-3.19,7.17-5.98,13.35-5.98,5.78,0,9.56,2.39,11.55,6.38,3.98-3.39,8.76-6.38,15.14-6.38,8.56,0,12.95,5.18,12.95,13.74v99.99h-11.15v-97.6c0-3.99-1.79-5.58-5.18-5.58-3.19,0-6.38,1-10.16,3.79v99.39Z"/>
                        <path class="logo-text" d="M514.68,251.75c-4.58,0-6.97,2.39-6.97,6.97v80.07c0,4.78,2.39,7.17,6.97,7.17h2.59c4.78,0,6.97-2.39,6.97-7.17v-80.07c0-4.58-2.19-6.97-6.97-6.97h-2.59ZM514.28,356.32c-11.55,0-17.73-5.97-17.73-17.93v-79.27c0-11.75,6.18-17.73,17.73-17.73h3.39c11.75,0,17.73,5.97,17.73,17.73v79.27c0,11.95-5.98,17.93-17.73,17.93h-3.39Z"/>
                    </g>
                    <polygon class="logo-text" points="555.91 355.13 541.57 242.59 552.92 242.59 562.09 329.83 571.45 242.59 582.4 242.59 568.06 355.13 555.91 355.13"/>
                    <path class="logo-text" d="M599.73,292.38h15.74v-33.66c0-4.58-2.39-6.97-6.97-6.97h-1.79c-4.58,0-6.97,2.39-6.97,6.97v33.66ZM599.73,302.94v35.85c0,4.78,2.39,7.17,6.97,7.17h1.99c4.78,0,6.77-2.39,6.77-7.17v-26.09h11.15v25.7c0,11.95-5.97,17.93-17.93,17.93h-2.39c-11.55,0-17.73-5.97-17.73-17.93v-79.27c0-11.75,6.17-17.73,17.73-17.73h2.39c11.95,0,17.93,5.97,17.93,17.73v43.82h-26.89Z"/>
                </svg>
            </a>
            <div class="h-6 w-px bg-slate-200 dark:bg-slate-750"></div>
            <!-- Badge & Description -->
            <div class="flex items-center gap-2">
                <span class="h-6 px-2.5 rounded-full bg-[#F4920D]/10 text-[#F4920D] font-bold border border-[#F4920D]/20 text-xs inline-flex items-center leading-none">Conseil 8m²</span>
                <span id="headerPanelCount" class="text-xs text-[#666] dark:text-slate-400 font-medium hidden sm:inline">133 Panneaux &middot; 266 Faces Wallonie</span>
            </div>
        </div>

        <div class="flex items-center space-x-2">
            <!-- Mobile Toggle Chat / Listing / Carte -->
            <div class="flex lg:hidden items-center h-9 bg-slate-100 dark:bg-slate-800 rounded-xl p-0.5 border border-slate-200 dark:border-slate-700">
                <button type="button" id="viewChatBtn" onclick="switchMobileView('chat')" class="h-full px-2.5 text-xs font-bold rounded-lg bg-white dark:bg-slate-900 text-[#F4920D] shadow-xs transition flex items-center gap-1">
                    <i class="fa-solid fa-comments mr-1"></i>Chat
                </button>
                <button type="button" id="viewListingBtn" onclick="switchMobileView('listing')" class="h-full px-2.5 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition flex items-center gap-1">
                    <i class="fa-solid fa-layer-group mr-1"></i>
                    <span>Panneaux</span>
                    <span id="mobilePanelsBadge" class="hidden px-1.5 py-0.5 rounded-full text-[10px] bg-[#F4920D] text-white font-extrabold leading-none">0</span>
                </button>
                <button type="button" id="viewMapBtn" onclick="switchMobileView('map')" class="h-full px-2.5 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition flex items-center gap-1">
                    <i class="fa-solid fa-map-location-dot mr-1"></i>
                    <span>Carte</span>
                </button>
            </div>

            <!-- Sync Live Badge -->
            <div id="statsBadge" class="hidden 2xl:flex h-9 text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 rounded-xl text-[#666] dark:text-slate-300 items-center space-x-2 shadow-inner">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>133 panneaux (266 faces)</span>
            </div>

            <!-- Bouton Dossiers / Historique -->
            <button onclick="toggleDossiersDrawer()" title="Consulter l'historique des dossiers et propositions" class="h-9 px-3 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 shadow-xs shrink-0">
                <i class="fa-solid fa-folder-open text-[#F4920D]"></i>
                <span id="dossiersBtnLabel" class="hidden sm:inline">Dossiers</span>
                <span id="dossiersCountBadge" class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#F4920D] text-white leading-none">0</span>
            </button>

            <!-- Profil Utilisateur Connecté & Menu Déconnexion -->
            <div class="relative">
                <button onclick="toggleUserDropdown()" id="currentProfileBtn" title="Menu utilisateur" class="h-9 px-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200 shadow-xs shrink-0">
                    <span id="profileAvatar" class="w-5.5 h-5.5 rounded-lg bg-[#F4920D] text-white flex items-center justify-center text-[10px] font-black shadow-xs shrink-0">CH</span>
                    <span id="profileName" class="font-bold hidden md:inline truncate max-w-[130px]">Corentin Hubert</span>
                    <span id="profileRoleBadge" class="hidden text-[9px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600 dark:text-purple-400 font-extrabold uppercase border border-purple-500/20 leading-none">Admin</span>
                    <i class="fa-solid fa-chevron-down text-[10px] text-slate-400 shrink-0"></i>
                </button>

                <!-- Menu Déroulant Profil Individuel (Déconnexion, Infos) -->
                <div id="userDropdownMenu" class="hidden absolute right-0 mt-2 w-64 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in zoom-in-95 duration-150">
                    <div class="border-b border-slate-100 dark:border-slate-800 pb-2 mb-2">
                        <div class="flex items-center gap-2 mb-1">
                            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                            <p class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Connecté avec Google</p>
                        </div>
                        <p id="userDropdownName" class="text-xs font-bold text-slate-900 dark:text-white">Corentin Hubert</p>
                        <p id="userDropdownEmail" class="text-[11px] text-slate-500 dark:text-slate-400 truncate">corentin@mediasee.be</p>
                        <p id="userDropdownRole" class="text-[10px] font-semibold text-[#F4920D] mt-1">👑 Administrateur M Move</p>
                    </div>
                    <button onclick="logoutUser()" class="w-full text-left px-3 py-2 rounded-xl text-xs font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition flex items-center gap-2">
                        <i class="fa-solid fa-arrow-right-from-bracket"></i>
                        <span>Se déconnecter</span>
                    </button>
                </div>
            </div>

            <!-- Dark / Light Mode Toggle -->
            <button onclick="toggleDarkMode()" title="Changer le thème (Clair / Sombre)" class="h-9 w-9 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center justify-center shrink-0">
                <i id="themeIcon" class="fa-solid fa-moon text-[#666] dark:text-amber-400 text-xs"></i>
            </button>

            <!-- Bouton Discret Exporter les Logs (Debug / Retours) -->
            <button onclick="openConversationLogsModal()" title="Extraire les logs de la conversation pour débug / retours" class="h-9 w-9 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center justify-center text-slate-400 hover:text-[#F4920D] dark:text-slate-500 dark:hover:text-[#F4920D] opacity-60 hover:opacity-100 shrink-0" aria-label="Logs de conversation">
                <i class="fa-solid fa-code text-xs"></i>
            </button>
        </div>
    </header>

    <!-- MAIN THREE-COLUMN WORKSPACE (1/3 Chat, 1/3 Listing Panneaux, 1/3 Carte & Résumés) -->
    <main class="flex-1 flex overflow-hidden relative w-full h-[calc(100vh-61px)]">
        <!-- COLONNE 1 (1/3) : CHAT & CONVERSATION -->
        <section id="chatSection" class="w-full lg:w-1/3 flex flex-col min-w-0 h-full border-r border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 shrink-0">
            <!-- BANDEAU DOSSIER CLIENT EN COURS -->
            <div class="h-[52px] px-3.5 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2 shrink-0 z-10">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                    <span class="w-7 h-7 rounded-lg bg-[#F4920D]/10 text-[#F4920D] flex items-center justify-center text-xs font-bold shrink-0">
                        <i class="fa-solid fa-briefcase"></i>
                    </span>
                    <span class="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Client :</span>
                    <div class="relative flex-1 min-w-0">
                        <input type="text" id="clientNameInput" placeholder="Nom du client / annonceur..." 
                            class="w-full px-2.5 py-1 text-xs font-bold text-slate-800 dark:text-slate-100 bg-slate-50 dark:bg-slate-800/80 border border-slate-300 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#F4920D] transition truncate"
                            onchange="onClientNameInputChanged(this.value)">
                    </div>
                </div>
                <div class="flex items-center gap-1.5 shrink-0 text-xs">
                    <button onclick="startNewProposition()" title="Démarrer une nouvelle proposition vierge" class="px-2 py-1 rounded-lg text-slate-600 dark:text-slate-300 hover:text-[#F4920D] dark:hover:text-[#F4920D] bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 transition flex items-center gap-1 font-medium text-xs">
                        <i class="fa-solid fa-plus text-[10px]"></i> <span class="hidden xl:inline">Nouveau</span>
                    </button>
                </div>
            </div>

            <!-- Zone des messages de discussion -->
            <div id="chatMessages" class="flex-1 overflow-y-auto p-3.5 space-y-4 w-full">
                <!-- Message initial de bienvenue -->
                <div class="flex items-start space-x-2.5">
                    <div class="w-8 h-8 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xs shrink-0 mt-0.5">
                        <img src="/static/bot-avatar.png" alt="Conseiller M Move" class="w-full h-full object-cover object-top">
                    </div>
                    <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 text-xs leading-relaxed shadow-sm text-[#666] dark:text-slate-200">
                        <p class="font-bold text-[#F4920D] mb-1.5 flex items-center gap-1.5 text-xs">
                            <i class="fa-solid fa-sparkles text-[#FF5B34]"></i> Conseiller Commercial M Move
                        </p>
                        Bonjour ! Je suis votre conseiller pour le réseau de remorques publicitaires 8m² M Move en Wallonie (133 remorques, 266 faces).<br><br>
                        Quelle zone, axe ou période souhaitez-vous pour votre client ? Le listing des remorques et la cartographie s'affichent automatiquement dans les volets de droite.
                    </div>
                </div>
            </div>

            <!-- Barre de saisie inférieure -->
            <div class="p-3 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 z-10 shrink-0">
                <div class="space-y-2">
                    <!-- Suggestions rapides -->
                    <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
                        <button type="button" onclick="sendSuggestion('Campagne de 5 faces à Gembloux en Mars, Avril et Mai 2027')" class="shrink-0 px-2.5 py-0.5 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] transition border border-slate-200 dark:border-slate-700 text-[11px]">
                            🎯 Gembloux 3 mois
                        </button>
                        <button type="button" onclick="sendSuggestion('élargis vers wavre')" class="shrink-0 px-2.5 py-0.5 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] transition border border-slate-200 dark:border-slate-700 text-[11px]">
                            ➕ Élargis Wavre
                        </button>
                        <button type="button" onclick="sendSuggestion('refais ma sélection')" class="shrink-0 px-2.5 py-0.5 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] transition border border-slate-200 dark:border-slate-700 text-[11px]">
                            🔄 Refais sélection
                        </button>
                    </div>

                    <!-- Formulaire de saisie -->
                    <form id="chatForm" class="flex items-end space-x-2">
                        <textarea id="messageInput" rows="1" placeholder="Échangez avec le conseiller..." 
                            class="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#F4920D] text-slate-900 dark:text-white placeholder-slate-400 resize-none max-h-32 leading-normal" required></textarea>
                        <button type="submit" id="sendBtn" class="bg-gradient-to-r from-[#F4920D] to-[#FF5B34] hover:opacity-95 active:scale-95 text-white p-2.5 rounded-xl font-semibold transition shadow-xs flex items-center justify-center shrink-0">
                            <i class="fa-solid fa-paper-plane text-xs"></i>
                        </button>
                    </form>
                </div>
            </div>
        </section>

        <!-- COLONNE 2 (1/3) : LISTING PANNEAUX SÉLECTIONNÉS -->
        <section id="listingSection" class="hidden lg:flex w-full lg:w-1/3 flex-col min-w-0 h-full border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shrink-0">
            <!-- Header Colonne Listing -->
            <div class="h-[52px] px-3.5 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between gap-2 shrink-0">
                <div class="flex items-center gap-2 min-w-0">
                    <span class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-[#F4920D]/10 text-[#F4920D] shrink-0 font-bold">
                        <i class="fa-solid fa-layer-group text-xs"></i>
                    </span>
                    <div class="min-w-0">
                        <h3 id="listingColTitle" class="text-xs font-bold text-slate-900 dark:text-white truncate leading-tight">Sélection Emplacements</h3>
                        <p id="listingColSubtitle" class="text-[11px] text-slate-500 dark:text-slate-400 truncate leading-tight">Panneaux 8m² recommandés</p>
                    </div>
                </div>
                <span id="listingColCount" class="px-2.5 py-0.5 rounded-full bg-[#F4920D]/10 text-[#F4920D] font-bold text-xs border border-[#F4920D]/20 shrink-0">0 faces</span>
            </div>

            <!-- Onglets de sélection des mois (Campagne Multi-Mois) -->
            <div id="listingMonthTabsBar" class="hidden px-3 py-2 bg-slate-100/80 dark:bg-slate-800/70 border-b border-slate-200 dark:border-slate-700/80 flex items-center gap-1.5 overflow-x-auto no-scrollbar shrink-0">
                <!-- Généré dynamiquement en JS -->
            </div>

            <!-- Conteneur défilable de la liste des panneaux -->
            <div id="listingPanelsContainer" class="flex-1 overflow-y-auto p-3 space-y-2.5 bg-slate-50/30 dark:bg-slate-950/30">
                <div id="listingEmptyState" class="py-16 px-4 text-center text-slate-400">
                    <i class="fa-solid fa-map-pin text-3xl mb-2 text-slate-300 dark:text-slate-600"></i>
                    <p class="text-xs font-medium">Aucun panneau sélectionné.</p>
                    <p class="text-[11px] text-slate-400 mt-1">Saisissez votre demande dans le chat pour afficher les remorques qualifiées.</p>
                </div>
                <div id="listingPanelsList" class="space-y-2.5">
                    <!-- Populated dynamically with rich cards -->
                </div>

                <!-- Boîte d'aide pour demander une modification directe -->
                <div id="sideHelperBox" class="p-3 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 text-[11px] text-amber-900 dark:text-amber-200 flex items-start gap-2 shadow-2xs mt-3">
                    <i class="fa-solid fa-lightbulb text-[#F4920D] text-xs shrink-0 mt-0.5"></i>
                    <div class="leading-relaxed">
                        <span class="font-bold">Ajuster la sélection :</span>
                        <p class="mt-0.5 text-amber-800/90 dark:text-amber-300/90 text-[11px]">
                            Demandez vos ajustements directement dans le chat (ex : <i>« élargis vers Namur »</i>, <i>« valide la 108 »</i> ou <i>« sans la 329 »</i>).
                        </p>
                    </div>
                </div>
            </div>

            <!-- Barre d'action interactive de sélection client (Validation Plan Média) -->
            <div id="clientSelectionBar" class="hidden p-2.5 border-t border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm flex items-center justify-between gap-2 shrink-0 shadow-lg">
                <div class="min-w-0">
                    <p id="selectionCountText" class="text-xs font-bold text-slate-800 dark:text-slate-100 truncate">0 face retenue</p>
                    <p class="text-[10px] text-slate-500 truncate">Créer le Plan Média officiel</p>
                </div>
                <button type="button" onclick="validateClientSelection()" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shrink-0 flex items-center gap-1.5 shadow-xs transition">
                    <i class="fa-solid fa-file-signature text-xs"></i>
                    <span>Valider & Générer Plan</span>
                </button>
            </div>
        </section>

        <!-- COLONNE 3 (1/3) : CARTE & RÉSUMÉS D'IMPACT -->
        <aside id="mapSection" class="hidden lg:flex w-full lg:w-1/3 flex-col min-w-0 h-full bg-slate-50/60 dark:bg-slate-900 shrink-0">
            <!-- Header du volet cartographique -->
            <div class="h-[52px] px-3.5 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between gap-2 shrink-0">
                <div class="flex items-center gap-2 min-w-0">
                    <span class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-[#F4920D]/10 text-[#F4920D] shrink-0 border border-[#F4920D]/20">
                        <i class="fa-solid fa-map-location-dot text-xs"></i>
                    </span>
                    <div class="min-w-0">
                        <h3 id="sideMapTitle" class="text-xs font-bold text-slate-900 dark:text-white truncate leading-tight">Cartographie & Impact</h3>
                        <p id="sideMapSubtitle" class="text-[11px] text-slate-500 dark:text-slate-400 truncate leading-tight">Réseau 8m² Wallonie</p>
                    </div>
                </div>

                <div class="flex items-center gap-1.5 shrink-0">
                    <!-- Toggle Interactif / Rendu HD -->
                    <div id="mapModeToggle" class="hidden inline-flex bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5 border border-slate-200 dark:border-slate-700 text-[10px]">
                        <button type="button" onclick="setMapDisplayMode('interactive')" id="btnModeInteractive" class="px-2 py-0.5 font-bold rounded-md bg-white dark:bg-slate-900 text-[#F4920D] shadow-2xs">Interactif</button>
                        <button type="button" onclick="setMapDisplayMode('render')" id="btnModeRender" class="px-2 py-0.5 font-semibold rounded-md text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">HD</button>
                    </div>

                    <!-- Bouton Télécharger Plan Média PDF Direct -->
                    <a id="sidePdfDownloadBtn" href="#" target="_blank" download onclick="onPdfDownloadTriggered()" class="btn-pdf hidden inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-gradient-to-r from-[#F4920D] to-[#FF5B34] font-bold text-xs shadow-xs hover:brightness-110 active:scale-95 transition-all text-white" style="color: #ffffff !important; text-decoration: none !important;">
                        <i class="fa-solid fa-file-pdf" style="color: #ffffff !important;"></i>
                        <span style="color: #ffffff !important;">PDF</span>
                    </a>
                </div>
            </div>

            <!-- Conteneur Carte (Leaflet interactif ou Rendu HD) - Hauteur bornée -->
            <div class="relative w-full h-[250px] xl:h-[275px] shrink-0 bg-slate-100 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800">
                <!-- Carte Leaflet interactive -->
                <div id="leafletMap" class="w-full h-full z-0"></div>

                <!-- Conteneur Rendu HD Statique -->
                <div id="renderMapContainer" class="hidden absolute inset-0 bg-slate-900 flex items-center justify-center overflow-hidden z-10">
                    <img id="renderMapImage" src="" alt="Plan Média HD" class="w-full h-full object-cover" />
                </div>

                <!-- Badge overlay dynamique sur la carte -->
                <div id="mapOverlayBadge" class="absolute bottom-2 left-2 z-[400] bg-black/75 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded font-medium shadow-sm flex items-center gap-1.5 border border-white/10">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span id="mapOverlayText">Réseau M Move Wallonie</span>
                </div>
            </div>

            <!-- ZONE SOUS LA CARTE : VUES, TRAFIC, OTS ET RÉSUMÉS -->
            <div id="summarySection" class="flex-1 overflow-y-auto p-3 space-y-3 bg-white dark:bg-slate-900/60">
                <div id="summaryEmptyState" class="py-12 px-4 text-center text-slate-400">
                    <i class="fa-solid fa-chart-pie text-2xl mb-2 text-slate-300 dark:text-slate-600"></i>
                    <p class="text-xs font-medium">Métriques et résumés</p>
                    <p class="text-[11px] text-slate-400 mt-1">Les indicateurs de couverture, de trafic et les spécifications techniques s'afficheront ici.</p>
                </div>
                <div id="summaryContent" class="space-y-3 hidden">
                    <!-- Populated dynamically with summary cards, KPIs, deadlines -->
                </div>
            </div>
        </aside>
    </main>

    <script>
        // Configuration Marked.js
        if (typeof marked !== 'undefined') {
            marked.setOptions({ breaks: true, gfm: true });
        }

        // Thème Sombre / Clair avec mémorisation
        function initTheme() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'dark') {
                document.documentElement.classList.add('dark');
            } else if (savedTheme === 'light') {
                document.documentElement.classList.remove('dark');
            } else {
                // Défaut clair moderne comme AI Studio
                document.documentElement.classList.remove('dark');
            }
            updateThemeIcon();
        }

        function toggleDarkMode() {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            updateThemeIcon();
        }

        function updateThemeIcon() {
            const isDark = document.documentElement.classList.contains('dark');
            const icon = document.getElementById('themeIcon');
            if (icon) {
                icon.className = isDark ? 'fa-solid fa-sun text-amber-400 text-sm' : 'fa-solid fa-moon text-slate-600 text-sm';
            }
        }
        initTheme();

        // Gestion de l'agrandissement automatique du textarea
        const messageInput = document.getElementById('messageInput');
        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 140) + 'px';
        });

        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                chatForm.dispatchEvent(new Event('submit'));
            }
        });

        // Récupération de l'état de synchronisation
        async function loadSyncStatus() {
            try {
                const r = await fetch('/api/health');
                const data = await r.json();
                const pCount = data.panneaux_count || data.trailers_count || 133;
                const fCount = data.faces_count || (pCount * 2);
                const s = data.synchronisation;

                // Mise à jour synchrone de l'en-tête gauche
                const headerCountEl = document.getElementById('headerPanelCount');
                if (headerCountEl) {
                    headerCountEl.innerHTML = `${pCount} Panneaux &middot; ${fCount} Faces Wallonie`;
                }

                document.getElementById('statsBadge').innerHTML = `
                    <span class="flex items-center space-x-1.5">
                        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        <span class="font-bold text-slate-900 dark:text-white">${pCount}</span>
                        <span class="text-slate-500 dark:text-slate-400">panneaux</span>
                        <span class="text-xs text-[#F4920D] font-semibold">(${fCount} faces)</span>
                    </span>
                    <span class="text-slate-300 dark:text-slate-600">|</span>
                    <span title="Vérification horaire des réservations">
                        <i class="fa-regular fa-clock text-blue-500"></i> Dispo : <b>1x/h</b> <span class="text-slate-400 text-[11px]">(${s.dispo.prochaine_verification})</span>
                    </span>
                    <span class="text-slate-300 dark:text-slate-600">|</span>
                    <span title="Inventaire hebdomadaire du réseau">
                        <i class="fa-regular fa-calendar text-purple-500"></i> Panneaux : <b>1x/sem</b> <span class="text-slate-400 text-[11px]">(${s.panneaux.prochaine_verification})</span>
                    </span>
                `;
            } catch (e) {
                document.getElementById('statsBadge').innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>133 panneaux (266 faces) &middot; Synchronisation active</span>';
            }
        }
        loadSyncStatus();
        setInterval(loadSyncStatus, 30000);

        async function triggerSync(type) {
            const icon = document.getElementById('syncIcon');
            if (icon) icon.classList.add('fa-spin');
            try {
                await fetch('/api/sync/trigger', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: type })
                });
                await loadSyncStatus();
            } catch (err) {
                alert("Erreur lors de la synchronisation");
            } finally {
                if (icon) icon.classList.remove('fa-spin');
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const chatForm = document.getElementById('chatForm');
        const sendBtn = document.getElementById('sendBtn');
        let history = [];
        let detailedLogs = [{
            role: 'system',
            time: new Date().toLocaleTimeString('fr-FR'),
            timestamp: new Date().toISOString(),
            text: "Initialisation de la session M Move Conseil"
        }];

        function showLogsToast(msg) {
            const toast = document.getElementById('logsToast');
            const msgEl = document.getElementById('logsToastMsg');
            if (!toast || !msgEl) return;
            msgEl.textContent = msg;
            toast.classList.remove('translate-y-10', 'opacity-0', 'pointer-events-none');
            toast.classList.add('translate-y-0', 'opacity-100');
            setTimeout(() => {
                toast.classList.remove('translate-y-0', 'opacity-100');
                toast.classList.add('translate-y-10', 'opacity-0', 'pointer-events-none');
            }, 3000);
        }

        function generateLogsText() {
            if (!detailedLogs || detailedLogs.length === 0) {
                return "Aucun échange enregistré dans cette session.";
            }

            const NL = String.fromCharCode(10);
            const lines = [];
            lines.push("=== LOGS DE CONVERSATION M MOVE CONSEIL ===");
            lines.push("Date d'export : " + new Date().toLocaleString('fr-FR'));
            lines.push("Nombre total d'événements : " + detailedLogs.length);
            lines.push("==========================================");
            lines.push("");

            detailedLogs.forEach((item) => {
                if (item.role === 'user') {
                    lines.push("--------------------------------------------------");
                    lines.push(`[${item.time}] 👤 UTILISATEUR :`);
                    lines.push(item.text);
                    lines.push("");
                } else if (item.role === 'model') {
                    lines.push(`[${item.time}] 🤖 ASSISTANT M MOVE :`);
                    if (item.timing && item.timing.elapsed_ms) {
                        lines.push(`⏱️ Temps de réponse : ${(item.timing.elapsed_ms / 1000).toFixed(2)}s`);
                    }
                    if (item.extracted && item.extracted.intent) {
                        lines.push(`🎯 Intention détectée : ${item.extracted.intent}`);
                        if (item.extracted.client_name) lines.push(`🏢 Client : ${item.extracted.client_name}`);
                        if (item.extracted.target_periods && item.extracted.target_periods.length) lines.push(`📅 Périodes : ${item.extracted.target_periods.join(', ')}`);
                        if (item.extracted.city) lines.push(`📍 Ville : ${item.extracted.city}`);
                        if (item.extracted.n_faces) lines.push(`🔢 Faces : ${item.extracted.n_faces}`);
                    }
                    if (item.panels_summary && item.panels_summary.length > 0) {
                        lines.push(`🏷️ Remorques (${item.panels_count}) : ${item.panels_summary.join(', ')}`);
                    }
                    if (item.campaign_plan && item.campaign_plan.pdf_url) {
                        lines.push(`📄 Plan Média PDF : ${item.campaign_plan.pdf_url}`);
                    }
                    lines.push("");
                    lines.push("💬 TEXTE DE LA RÉPONSE :");
                    lines.push(item.text);
                    lines.push("");
                } else if (item.role === 'error') {
                    lines.push(`[${item.time}] ⚠️ ERREUR :`);
                    lines.push(item.text);
                    lines.push("");
                }
            });

            lines.push("==========================================");
            lines.push("=== FIN DES LOGS ===");
            return lines.join(NL);
        }

        async function openConversationLogsModal() {
            const modal = document.getElementById('logsModal');
            const ta = document.getElementById('logsTextarea');
            if (!modal || !ta) return;
            
            const logsText = generateLogsText();
            ta.value = logsText;
            modal.classList.remove('hidden');
            modal.classList.add('flex');

            try {
                await navigator.clipboard.writeText(logsText);
                showLogsToast("✓ Logs copiés dans le presse-papier !");
                const fb = document.getElementById('logsCopyFeedback');
                if (fb) {
                    fb.classList.remove('hidden');
                    setTimeout(() => fb.classList.add('hidden'), 3500);
                }
            } catch (err) {
                // Clipboard fallback sur clic
            }
        }

        function closeConversationLogsModal() {
            const modal = document.getElementById('logsModal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        }

        async function copyConversationLogs() {
            const ta = document.getElementById('logsTextarea');
            const text = (ta && ta.value) ? ta.value : generateLogsText();
            try {
                await navigator.clipboard.writeText(text);
                showLogsToast("✓ Logs copiés dans le presse-papier !");
                const fb = document.getElementById('logsCopyFeedback');
                if (fb) {
                    fb.classList.remove('hidden');
                    setTimeout(() => fb.classList.add('hidden'), 3000);
                }
            } catch (e) {
                if (ta) {
                    ta.select();
                    document.execCommand('copy');
                    showLogsToast("✓ Logs copiés !");
                }
            }
        }

        function downloadLogs(format) {
            let content, mime, filename;
            const now = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            if (format === 'json') {
                content = JSON.stringify(detailedLogs, null, 2);
                mime = 'application/json';
                filename = `mmove_logs_${now}.json`;
            } else {
                content = generateLogsText();
                mime = 'text/plain;charset=utf-8';
                filename = `mmove_logs_${now}.txt`;
            }
            const blob = new Blob([content], { type: mime });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showLogsToast(`✓ Fichier ${filename} téléchargé !`);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeConversationLogsModal();
        });

        function sendSuggestion(text) {
            messageInput.value = text;
            chatForm.dispatchEvent(new Event('submit'));
        }

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = messageInput.value.trim();
            if (!msg) return;

            // Message utilisateur
            messageInput.value = '';
            messageInput.style.height = 'auto';
            appendMessage('user', msg);
            history.push({ role: 'user', text: msg });

            const now = new Date();
            const timeStr = now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            detailedLogs.push({
                role: 'user',
                time: timeStr,
                timestamp: now.toISOString(),
                text: msg
            });

            // Indicateur de chargement
            const loadingId = appendLoading();
            sendBtn.disabled = true;

            try {
                const clientInput = document.getElementById('clientNameInput');
                const clientVal = clientInput ? clientInput.value.trim() : '';

                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: msg,
                        history: history,
                        client_name: clientVal,
                        salesperson_id: currentUser ? currentUser.id : 'CH'
                    })
                });
                const data = await res.json();
                removeLoading(loadingId);

                // Mémorisation de l'état de recherche / disponibilité
                window.lastAvailabilityPdfUrl = data.availability_pdf_url || null;
                window.canExpandZone = data.can_expand_zone || false;
                window.peripheralCount = data.peripheral_count || 0;
                window.peripheralCities = data.peripheral_cities || [];
                window.currentTargetPeriods = (data.target_periods && data.target_periods.length) ? data.target_periods : null;
                window.currentTargetLocation = data.location || null;
                window.currentSearchCircle = data.search_circle || null;
                window.currentRadiusKm = data.current_radius_km || (data.search_circle ? data.search_circle.radius_km : 5);
                window.nextRadiusKm = data.next_radius_km || (window.currentRadiusKm + 5);

                // Synchronisation du champ client avec l'extraction IA
                if (data.client_name && clientInput) {
                    clientInput.value = data.client_name;
                }

                // Mise à jour de la cartographie latérale en temps réel
                updateSideMap(data.campaign_plan, data.panels);

                // Si une proposition a été générée, recharger les dossiers
                if (data.campaign_plan) {
                    loadDossiers();
                }

                appendMessage('model', data.text, data.panels, data.timing, data.campaign_plan, data.badge, data.agent_name);
                history.push({ role: 'model', text: data.text });

                const modelNow = new Date();
                const modelTimeStr = modelNow.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                detailedLogs.push({
                    role: 'model',
                    time: modelTimeStr,
                    timestamp: modelNow.toISOString(),
                    text: data.text,
                    extracted: data.extracted || null,
                    client_name: data.client_name || null,
                    timing: data.timing || null,
                    panels_count: (data.panels || []).length,
                    panels_summary: (data.panels || []).map(p => `#${p.id || p.remorque} (${p.ville || ''} - ${p.axe_routier || p.direction || ''})`),
                    campaign_plan: data.campaign_plan ? {
                        periods: data.campaign_plan.periods,
                        pdf_url: data.campaign_plan.pdf_url,
                        summary: data.campaign_plan.summary
                    } : null
                });
            } catch (err) {
                removeLoading(loadingId);
                appendMessage('model', "Une erreur réseau est survenue. Veuillez réessayer dans quelques instants.");
                detailedLogs.push({
                    role: 'error',
                    time: new Date().toLocaleTimeString('fr-FR'),
                    text: err ? err.toString() : "Erreur réseau"
                });
            } finally {
                sendBtn.disabled = false;
                messageInput.focus();
            }
        });

        // Rendu complet d'une carte de remorque publicitaire (Style AI Studio / PanelCard)
        function renderPanelCard(p) {
            const panelId = String(p.id || p.remorque || '').replace('.0', '');
            const linkUrl = p.lien || `https://remorquepublicitaire.be/remorque/${panelId}`;
            const photoUrl = p.photo || p.image_url || `https://remorquepublicitaire.be/wp-content/uploads/2021/07/${panelId}in.jpg`;
            const isDirect = p.is_direct_match;
            const distText = (p.distance_km !== null && p.distance_km !== undefined) ? `📍 à ${p.distance_km} km` : null;
            const freqFormatted = p.frequentation ? Number(p.frequentation).toLocaleString('fr-FR') : null;
            const otsFormatted = p.ots ? Number(p.ots).toLocaleString('fr-FR') : null;

            return `
            <div class="bg-white dark:bg-slate-800/95 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700/80 overflow-hidden hover:shadow-md hover:border-[#F4920D]/60 transition-all text-sm flex flex-col group">
                <!-- 1. Photo de la remorque 8m² avec badges -->
                <div class="relative w-full h-36 bg-slate-900 overflow-hidden">
                    <img src="${photoUrl}" 
                         alt="Remorque #${panelId} - ${p.ville || ''}" 
                         class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                         onerror="this.onerror=null; this.src='https://remorquepublicitaire.be/wp-content/uploads/2021/07/logo-mmove.png'; this.classList.add('object-contain', 'p-4');" />
                    
                    ${distText ? `
                    <div class="absolute top-2 left-2 bg-black/75 backdrop-blur-sm text-white text-[11px] font-semibold px-2 py-0.5 rounded-md shadow-sm">
                        ${distText}
                    </div>` : ''}

                    ${p.prochaine_dispo ? `
                    <div class="absolute bottom-2 right-2 bg-emerald-700/95 backdrop-blur-sm text-white text-[11px] font-bold px-2 py-0.5 rounded-md shadow-sm border border-emerald-400/40 flex items-center space-x-1">
                        <i class="fa-regular fa-calendar"></i>
                        <span>Dès ${p.prochaine_dispo_human || p.prochaine_dispo}</span>
                    </div>` : ''}
                </div>

                <!-- 2. Corps de la carte -->
                <div class="p-4 space-y-3 flex-1 flex flex-col justify-between">
                    <div>
                        <!-- En-tête : Titre & Badge Direction -->
                        <div class="flex justify-between items-start gap-2 mb-1">
                            <div>
                                <a href="${linkUrl}" target="_blank" rel="noopener noreferrer" 
                                   class="font-bold text-base text-slate-900 dark:text-white hover:text-[#F4920D] dark:hover:text-[#F4920D] flex items-center gap-1.5 transition-colors">
                                    <span>#${panelId} - ${p.ville || 'Wallonie'}</span>
                                    <i class="fa-solid fa-arrow-up-right-from-square text-xs text-[#F4920D]"></i>
                                </a>
                                ${p.localisation ? `<p class="text-xs text-[#666] dark:text-slate-400 mt-0.5 font-medium">${p.localisation}</p>` : ''}
                            </div>
                            ${p.direction ? `
                            <span class="px-2.5 py-1 rounded-full text-xs font-bold shrink-0 bg-[#F4920D]/10 text-[#F4920D] border border-[#F4920D]/20 flex items-center gap-1" title="Direction de visibilité">
                                <i class="fa-solid fa-compass text-[#FF5B34] text-[10px]"></i>
                                <span>Dir. ${p.direction}</span>
                            </span>` : `
                            <span class="px-2 py-0.5 rounded-full text-xs font-semibold shrink-0 bg-slate-100 dark:bg-slate-800 text-[#666] dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                                8m²
                            </span>`}
                        </div>

                        <!-- Badge Disponibilité Mis en Valeur -->
                        ${p.prochaine_dispo ? `
                        <div class="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#F4920D]/10 dark:bg-[#F4920D]/20 border border-[#F4920D]/30 text-[#F4920D] font-bold text-xs shadow-2xs">
                            <i class="fa-regular fa-calendar-check text-[#F4920D]"></i>
                            <span>Disponible dès : <b>${p.prochaine_dispo_human || p.prochaine_dispo}</b></span>
                        </div>` : ''}

                        <!-- Axe routier & Direction -->
                        <div class="space-y-1.5 text-[#666] dark:text-slate-300 text-xs mt-2.5">
                            ${p.axe_routier ? `
                            <div class="flex items-center space-x-2">
                                <i class="fa-solid fa-road text-slate-400 dark:text-slate-500 w-3.5 text-center"></i>
                                <span class="font-semibold text-slate-700 dark:text-slate-200">${p.axe_routier}</span>
                            </div>` : ''}
                            ${p.direction ? `
                            <div class="flex items-center space-x-2">
                                <i class="fa-solid fa-compass text-[#FF5B34] w-3.5 text-center"></i>
                                <span>Sens de visibilité : <span class="font-bold text-slate-800 dark:text-slate-100">Direction ${p.direction}</span></span>
                            </div>` : ''}
                        </div>

                        <!-- Fréquentation & OTS -->
                        ${(freqFormatted || otsFormatted) ? `
                        <div class="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-700 flex items-center gap-3 text-xs">
                            ${freqFormatted ? `
                            <span class="flex items-center gap-1.5 text-[#F4920D] font-semibold" title="Fréquentation moyenne">
                                <i class="fa-solid fa-car text-[#F4920D]"></i>
                                ${freqFormatted} véh./j
                            </span>` : ''}
                            ${otsFormatted ? `
                            <span class="flex items-center gap-1.5 text-[#FF5B34] font-semibold" title="Opportunité de visibilité mensuelle">
                                <i class="fa-solid fa-eye text-[#FF5B34]"></i>
                                ${otsFormatted} OTS/mois
                            </span>` : ''}
                        </div>` : ''}

                        <!-- Contexte de visibilité -->
                        ${p.contexte_visibilite ? `
                        <div class="mt-2 bg-slate-50 dark:bg-slate-700/50 p-2.5 rounded-xl border border-slate-200/70 dark:border-slate-600/50 text-[11px] text-[#666] dark:text-slate-300 italic">
                            👁️ ${p.contexte_visibilite}
                        </div>` : ''}
                    </div>

                    <!-- Footer Disponibilité & Bouton Plus d'infos -->
                    <div class="pt-2">
                        ${p.prochaine_dispo ? `
                        <div class="bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 text-xs px-3 py-2 rounded-xl flex items-center justify-between font-medium">
                            <span class="flex items-center space-x-1.5">
                                <i class="fa-regular fa-calendar-check text-emerald-600 dark:text-emerald-400 text-sm"></i>
                                <span>Dispo dès : <b>${p.prochaine_dispo_human || p.prochaine_dispo}</b></span>
                            </span>
                            <a href="${linkUrl}" target="_blank" rel="noopener noreferrer" 
                               class="text-[11px] font-bold text-[#FF5B34] hover:text-[#F4920D] transition-colors underline">
                                Plus d'infos ↗
                            </a>
                        </div>` : ''}
                    </div>
                </div>
            </div>`;
        }

        function renderCampaignPlanWidget(cp) {
            if (!cp || !cp.months || cp.months.length === 0) return '';
            const summary = cp.summary || {};
            const months = cp.months || [];
            const widgetId = 'cp_' + Math.random().toString(36).substring(2, 9);
            const totalOts = summary.total_cumulative_ots ? Number(summary.total_cumulative_ots).toLocaleString('fr-FR') : '';
            const avgVeh = summary.avg_veh_per_day ? Number(summary.avg_veh_per_day).toLocaleString('fr-FR') : '';

            let tabsHtml = '';
            let panesHtml = '';

            months.forEach((m, idx) => {
                const isActive = idx === 0;
                const tabId = `${widgetId}_tab_${idx}`;
                const paneId = `${widgetId}_pane_${idx}`;

                tabsHtml += `
                <button type="button" 
                        onclick="switchCampaignTab('${widgetId}', ${idx})"
                        id="${tabId}"
                        class="campaign-tab-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${isActive ? 'bg-[#F4920D] text-white shadow-xs' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'}">
                    📅 ${m.period_human} (${m.panels ? m.panels.length : 0} faces)
                </button>`;

                let panelListHtml = '';
                if (m.panels) {
                    m.panels.forEach((p, pIdx) => {
                        const pid = String(p.id).replace('.0', '');
                        const pFreq = p.frequentation_jour ? Number(p.frequentation_jour).toLocaleString('fr-FR') : '';
                        const pOts = p.ots_mensuel ? Number(p.ots_mensuel).toLocaleString('fr-FR') : '';
                        const pDir = p.direction_in || p.direction_out || p.direction || 'Double sens';
                        const pAxe = p.axe_routier || p.code_route || '';

                        panelListHtml += `
                        <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200/80 dark:border-slate-700/60 flex items-start gap-2.5 text-xs">
                            <span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#F4920D] text-white font-bold text-[11px] shrink-0 mt-0.5 shadow-2xs">
                                ${pIdx + 1}
                            </span>
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center justify-between gap-1">
                                    <a href="${p.lien || `https://remorquepublicitaire.be/remorque/${pid}`}" target="_blank" class="font-bold text-slate-800 dark:text-slate-100 hover:text-[#F4920D] truncate">
                                        #${pid} ${p.ville} <span class="font-normal text-slate-500">(${p.localisation || ''})</span>
                                    </a>
                                    <span class="text-[10px] font-semibold text-[#F4920D] shrink-0">${pAxe}</span>
                                </div>
                                <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 flex flex-wrap gap-x-2">
                                    <span>🧭 Dir. <b>${pDir}</b></span>
                                    ${pFreq ? `<span>🚗 <b>${pFreq}</b> véh./j</span>` : ''}
                                    ${pOts ? `<span>👁️ <b>${pOts}</b> OTS</span>` : ''}
                                </div>
                            </div>
                        </div>`;
                    });
                }

                panesHtml += `
                <div id="${paneId}" class="campaign-pane ${isActive ? 'block' : 'hidden'} space-y-3 mt-3">
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-3 items-start">
                        <!-- Colonne gauche : Panneaux du mois -->
                        <div class="lg:col-span-6 space-y-2">
                            <div class="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-200 border-b border-slate-200 dark:border-slate-700 pb-1">
                                <span>Dispositif de ${m.period_human}</span>
                                <span class="text-[#F4920D] font-bold">${m.stats ? Number(m.stats.veh_per_day || 0).toLocaleString('fr-FR') : ''} véh./j</span>
                            </div>
                            <div class="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
                                ${panelListHtml}
                            </div>
                            ${m.deadline_full ? `
                            <div class="text-[10px] text-slate-500 dark:text-slate-400 flex items-center gap-1.5 pt-1 border-t border-slate-100 dark:border-slate-800">
                                <i class="fa-regular fa-clock text-[#F4920D]"></i>
                                <span>Fichiers 390×200 cm avant le <b>${m.deadline_full}</b></span>
                            </div>` : ''}
                        </div>

                        <!-- Colonne droite : Carte en vis-à-vis -->
                        <div class="lg:col-span-6">
                            ${m.map_url ? `
                            <div class="relative rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-sm bg-slate-100 dark:bg-slate-800">
                                <img src="${m.map_url}" alt="Carte ${m.period_human}" class="w-full h-auto object-cover" />
                                <div class="absolute bottom-2 left-2 bg-black/75 backdrop-blur-sm text-white text-[10px] px-2.5 py-1 rounded-md font-medium">
                                    Carte d'implantation — ${m.period_human}
                                </div>
                            </div>` : ''}
                        </div>
                    </div>
                </div>`;
            });

            return `
            <div id="${widgetId}" class="mt-4 p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
                <!-- En-tête Widget Plan Média -->
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-700/80 pb-3">
                    <div>
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-[#F4920D]/10 text-[#F4920D]">
                                <i class="fa-solid fa-map-location-dot text-sm"></i>
                            </span>
                            <h4 class="font-bold text-sm text-slate-900 dark:text-white">Plan Média Campagne 8m²</h4>
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#F4920D] text-white">
                                ${months.length} mois
                            </span>
                            ${cp.client_name ? `
                            <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 dark:bg-amber-950/60 text-[#F4920D] border border-amber-300 dark:border-amber-700/60 flex items-center gap-1">
                                <i class="fa-solid fa-building text-[10px]"></i> Client : ${cp.client_name}
                            </span>` : ''}
                        </div>
                        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            ${summary.total_faces_deployed || (months.length * 5)} faces déployées · ~${totalOts} occasions d'être vu (OTS)
                            ${!cp.client_name ? `<span class="italic text-slate-400 ml-1">· Indiquez un nom de client dans le chat pour personnaliser le PDF</span>` : ''}
                        </p>
                    </div>

                    <!-- Bouton Télécharger PDF -->
                    ${cp.pdf_url ? `
                    <a href="${cp.pdf_url}" target="_blank" download onclick="onPdfDownloadTriggered()"
                       class="btn-pdf inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-[#F4920D] to-[#FF5B34] font-bold text-xs shadow-xs hover:brightness-110 active:scale-95 transition-all shrink-0"
                       style="color: #ffffff !important; text-decoration: none !important;">
                        <i class="fa-solid fa-file-pdf text-sm" style="color: #ffffff !important;"></i>
                        <span style="color: #ffffff !important;">Télécharger le PDF</span>
                    </a>` : ''}
                </div>

                <!-- Onglets Mois -->
                <div class="flex flex-wrap gap-2 mt-3">
                    ${tabsHtml}
                </div>

                <!-- Contenu par mois -->
                ${panesHtml}
            </div>`;
        }

        function switchCampaignTab(widgetId, targetIdx) {
            const container = document.getElementById(widgetId);
            if (!container) return;
            const buttons = container.querySelectorAll('.campaign-tab-btn');
            const panes = container.querySelectorAll('.campaign-pane');

            buttons.forEach((btn, idx) => {
                if (idx === targetIdx) {
                    btn.className = 'campaign-tab-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all bg-[#F4920D] text-white shadow-xs';
                } else {
                    btn.className = 'campaign-tab-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700';
                }
            });

            panes.forEach((pane, idx) => {
                if (idx === targetIdx) {
                    pane.classList.remove('hidden');
                    pane.classList.add('block');
                } else {
                    pane.classList.remove('block');
                    pane.classList.add('hidden');
                }
            });
        }

        function appendMessage(role, text, panels = [], timing = null, campaignPlan = null, badge = null, agentName = null) {
            const div = document.createElement('div');
            const isUser = role === 'user';
            div.className = `flex items-start space-x-3 ${isUser ? 'justify-end' : ''}`;

            const avatar = isUser ? '' : `
                <div class="w-9 h-9 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xs shrink-0 mt-1">
                    <img src="/static/bot-avatar.png" alt="Conseiller M Move" class="w-full h-full object-cover object-top">
                </div>
            `;

            let formattedText = '';
            if (isUser) {
                formattedText = `<p class="whitespace-pre-line">${text}</p>`;
            } else {
                formattedText = (typeof marked !== 'undefined') ? marked.parse(text) : `<p class="whitespace-pre-line">${text}</p>`;
            }

            let badgeHtml = '';
            if (!isUser && badge) {
                let badgeColor = 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-200 dark:border-orange-800/40';
                if (badge.includes('🟢') || badge.toLowerCase().includes('inventaire')) {
                    badgeColor = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40';
                } else if (badge.includes('🔵') || badge.toLowerCase().includes('client')) {
                    badgeColor = 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800/40';
                } else if (badge.includes('📁') || badge.toLowerCase().includes('dossier')) {
                    badgeColor = 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-800/40';
                }
                badgeHtml = `
                <div class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${badgeColor} mb-2 shadow-2xs">
                    <span>${badge}</span>
                    ${agentName ? `<span class="opacity-70 font-normal">&middot; ${agentName}</span>` : ''}
                </div>`;
            }

            let timingHtml = '';
            if (timing) {
                timingHtml = `
                <div class="mt-3 text-[11px] text-[#888] dark:text-slate-500 flex flex-wrap gap-x-3 gap-y-1 border-t border-slate-200/80 dark:border-slate-700/80 pt-2 font-mono">
                    <span>⚡ Réponse: ${timing.total_ms}ms</span>
                    <span>&middot; NLU: ${timing.extraction_ms}ms</span>
                    <span>&middot; Géo/Dispo: ${timing.engine_ms}ms</span>
                    <span>&middot; Synthèse: ${timing.synthesis_ms}ms</span>
                </div>`;
            }

            const bubbleClass = isUser 
                ? 'bg-gradient-to-r from-[#F4920D] to-[#FF5B34] text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl text-sm shadow-sm font-medium' 
                : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 max-w-3xl text-xs sm:text-sm leading-relaxed shadow-sm text-[#666] dark:text-slate-100 markdown-body';

            div.innerHTML = `
                ${!isUser ? avatar : ''}
                <div class="${bubbleClass}">
                    ${badgeHtml}
                    ${formattedText}
                    ${timingHtml}
                </div>
            `;

            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function appendLoading() {
            const id = 'load_' + Date.now();
            const div = document.createElement('div');
            div.id = id;
            div.className = 'flex items-start space-x-3';
            div.innerHTML = `
                <div class="relative w-9 h-9 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xs shrink-0 mt-0.5">
                    <img src="/static/bot-avatar.png" alt="Conseiller M Move" class="w-full h-full object-cover object-top opacity-60">
                    <div class="absolute inset-0 bg-[#F4920D]/30 flex items-center justify-center">
                        <i class="fa-solid fa-spinner fa-spin text-white text-xs"></i>
                    </div>
                </div>
                <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 text-sm text-[#666] dark:text-slate-400 flex items-center space-x-3 shadow-sm">
                    <span class="animate-pulse flex items-center gap-2">
                        <i class="fa-solid fa-magnifying-glass-location text-[#F4920D]"></i>
                        Recherche d'implantation &amp; calcul des disponibilités en direct...
                    </span>
                </div>
            `;
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return id;
        }

        function removeLoading(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        // ==========================================
        // MODULE CARTOGRAPHIQUE EN VIS-À-VIS (Split View Leaflet)
        // ==========================================
        let map = null;
        let networkLayer = null;
        let recommendationLayer = null;
        let markersMap = {};
        let currentCampaignPlan = null;
        let activeMonthIdx = 0;
        let currentMapMode = 'interactive';

        function initLeafletMap() {
            if (typeof L === 'undefined') return;
            const mapEl = document.getElementById('leafletMap');
            if (!mapEl) return;

            try {
                map = L.map('leafletMap', {
                    zoomControl: true,
                    attributionControl: false
                }).setView([50.50, 4.65], 9);

                L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 18,
                    attribution: '&copy; OpenStreetMap'
                }).addTo(map);

                networkLayer = L.layerGroup().addTo(map);
                recommendationLayer = L.layerGroup().addTo(map);

                loadNetworkMarkers();

                window.addEventListener('resize', () => {
                    if (map) map.invalidateSize();
                });
            } catch (e) {
                console.warn("Initialisation Leaflet:", e);
            }
        }

        async function loadNetworkMarkers() {
            try {
                const res = await fetch('/api/network-trailers');
                const trailers = await res.json();
                if (!Array.isArray(trailers) || !networkLayer) return;

                trailers.forEach(t => {
                    if (t.lat && t.lng) {
                        const dotIcon = L.divIcon({
                            className: 'leaflet-div-icon',
                            html: `<div class="map-dot-network" title="#${t.id} - ${t.ville}"></div>`,
                            iconSize: [9, 9],
                            iconAnchor: [4.5, 4.5]
                        });
                        const m = L.marker([parseFloat(t.lat), parseFloat(t.lng)], { icon: dotIcon });
                        m.bindPopup(`
                            <div style="font-family:'Plus Jakarta Sans',sans-serif; font-size:12px; line-height:1.4;">
                                <div style="font-weight:700; color:#F4920D;">#${t.id} ${t.ville}</div>
                                <div style="color:#64748b; font-size:11px;">${t.axe_routier || ''}</div>
                                ${t.frequentation ? `<div style="margin-top:4px; font-weight:600;">🚗 ${Number(t.frequentation).toLocaleString('fr-FR')} véh./j</div>` : ''}
                                ${t.photo ? `<img src="${t.photo}" style="width:100%; border-radius:6px; margin-top:6px; max-height:85px; object-fit:cover;" onerror="this.remove()"/>` : ''}
                            </div>
                        `);
                        networkLayer.addLayer(m);
                    }
                });
            } catch (e) {
                console.warn("Impossible de charger les remorques du réseau:", e);
            }
        }

        function switchMobileView(view) {
            const chatSec = document.getElementById('chatSection');
            const listSec = document.getElementById('listingSection');
            const mapSec = document.getElementById('mapSection');
            const chatBtn = document.getElementById('viewChatBtn');
            const listBtn = document.getElementById('viewListingBtn');
            const mapBtn = document.getElementById('viewMapBtn');

            // Sur mobile, réinitialiser l'affichage
            if (chatSec) { chatSec.classList.add('hidden'); chatSec.classList.remove('flex'); }
            if (listSec) { listSec.classList.add('hidden'); listSec.classList.remove('flex'); }
            if (mapSec) { mapSec.classList.add('hidden'); mapSec.classList.remove('flex'); }

            const activeBtn = 'h-full px-2.5 text-xs font-bold rounded-lg bg-white dark:bg-slate-900 text-[#F4920D] shadow-xs transition flex items-center gap-1';
            const inactiveBtn = 'h-full px-2.5 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition flex items-center gap-1';

            if (chatBtn) chatBtn.className = inactiveBtn;
            if (listBtn) listBtn.className = inactiveBtn;
            if (mapBtn) mapBtn.className = inactiveBtn;

            if (view === 'listing') {
                if (listSec) { listSec.classList.remove('hidden'); listSec.classList.add('flex'); }
                if (listBtn) listBtn.className = activeBtn;
            } else if (view === 'map') {
                if (mapSec) { mapSec.classList.remove('hidden'); mapSec.classList.add('flex'); }
                if (mapBtn) mapBtn.className = activeBtn;
                if (map) setTimeout(() => map.invalidateSize(), 200);
            } else {
                if (chatSec) { chatSec.classList.remove('hidden'); chatSec.classList.add('flex'); }
                if (chatBtn) chatBtn.className = activeBtn;
            }
        }

        window.addEventListener('resize', () => {
            if (window.innerWidth >= 1024) {
                const chatSec = document.getElementById('chatSection');
                const listSec = document.getElementById('listingSection');
                const mapSec = document.getElementById('mapSection');
                if (chatSec) { chatSec.classList.remove('hidden'); chatSec.classList.add('flex'); }
                if (listSec) { listSec.classList.remove('hidden'); listSec.classList.add('flex'); }
                if (mapSec) { mapSec.classList.remove('hidden'); mapSec.classList.add('flex'); }
                if (map) map.invalidateSize();
            }
        });

        function setMapDisplayMode(mode) {
            currentMapMode = mode;
            const btnInteractive = document.getElementById('btnModeInteractive');
            const btnRender = document.getElementById('btnModeRender');
            const leafletEl = document.getElementById('leafletMap');
            const renderEl = document.getElementById('renderMapContainer');

            if (mode === 'render') {
                leafletEl.classList.add('hidden');
                renderEl.classList.remove('hidden');
                btnRender.className = 'px-2 py-0.5 font-bold rounded-md bg-white dark:bg-slate-900 text-[#F4920D] shadow-2xs';
                btnInteractive.className = 'px-2 py-0.5 font-semibold rounded-md text-slate-500 hover:text-slate-800 dark:hover:text-slate-200';
            } else {
                renderEl.classList.add('hidden');
                leafletEl.classList.remove('hidden');
                btnInteractive.className = 'px-2 py-0.5 font-bold rounded-md bg-white dark:bg-slate-900 text-[#F4920D] shadow-2xs';
                btnRender.className = 'px-2 py-0.5 font-semibold rounded-md text-slate-500 hover:text-slate-800 dark:hover:text-slate-200';
                if (map) map.invalidateSize();
            }
        }

        function updateSideMap(campaignPlan, panels) {
            // Colonne 2 : Listing
            const listTitle = document.getElementById('listingColTitle');
            const listSubtitle = document.getElementById('listingColSubtitle');
            const listCount = document.getElementById('listingColCount');
            const tabsBar = document.getElementById('listingMonthTabsBar');
            const mobilePanelsBadge = document.getElementById('mobilePanelsBadge');

            // Colonne 3 : Carte & Résumé
            const sideTitle = document.getElementById('sideMapTitle');
            const sideSubtitle = document.getElementById('sideMapSubtitle');
            const pdfBtn = document.getElementById('sidePdfDownloadBtn');
            const modeToggle = document.getElementById('mapModeToggle');

            if (campaignPlan && campaignPlan.months && campaignPlan.months.length > 0) {
                currentCampaignPlan = campaignPlan;
                window.currentSearchCircle = null;
                activeMonthIdx = 0;

                const totalFaces = campaignPlan.summary?.total_faces_deployed || (campaignPlan.months.length * 5);
                const clientPart = campaignPlan.client_name ? ` · ${campaignPlan.client_name}` : '';

                if (listTitle) listTitle.innerText = "Plan Média Multi-Mois";
                if (listSubtitle) listSubtitle.innerText = `${campaignPlan.months.length} mois · ${totalFaces} faces déployées`;
                if (listCount) listCount.innerText = `${totalFaces} faces`;

                if (sideTitle) sideTitle.innerText = "Cartographie & Impact";
                if (sideSubtitle) sideSubtitle.innerText = `${totalFaces} faces déployées${clientPart}`;

                if (campaignPlan.pdf_url) {
                    pdfBtn.href = campaignPlan.pdf_url;
                    pdfBtn.classList.remove('hidden');
                } else {
                    pdfBtn.classList.add('hidden');
                }

                modeToggle.classList.remove('hidden');

                // Onglets mensuels dans la colonne 2 (Listing)
                if (campaignPlan.months.length > 1) {
                    tabsBar.classList.remove('hidden');
                    let tabsHtml = '';
                    campaignPlan.months.forEach((m, idx) => {
                        const isAct = idx === 0;
                        tabsHtml += `
                            <button type="button" onclick="selectCampaignMonth(${idx})" id="listingMonthBtn_${idx}" 
                                    class="listing-month-btn px-2.5 py-1 rounded-lg text-xs font-bold transition-all shrink-0 ${isAct ? 'bg-[#F4920D] text-white shadow-xs' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200/80 dark:border-slate-700'}">
                                📅 ${m.period_human} (${m.panels?.length || 5})
                            </button>
                        `;
                    });
                    tabsBar.innerHTML = tabsHtml;
                } else {
                    tabsBar.classList.add('hidden');
                }

                if (mobilePanelsBadge) {
                    mobilePanelsBadge.innerText = totalFaces;
                    mobilePanelsBadge.classList.remove('hidden');
                }

                selectCampaignMonth(0);
            } else if (panels && panels.length > 0) {
                currentCampaignPlan = null;
                const count = panels.length;

                const hasTargetPeriod = window.currentTargetPeriods && window.currentTargetPeriods.length > 0;
                const periodLabel = hasTargetPeriod ? window.currentTargetPeriods.map(p => formatPeriodHuman(p)).join(', ') : null;
                const locLabel = window.currentTargetLocation || 'Wallonie';

                if (listTitle) listTitle.innerText = periodLabel ? `Disponibilités · ${periodLabel}` : "Sélection Emplacements";
                if (listSubtitle) listSubtitle.innerText = `${count} panneaux libres à ${locLabel} pour sélection client`;
                if (listCount) listCount.innerText = `${count} faces`;
                if (tabsBar) tabsBar.classList.add('hidden');

                if (sideTitle) sideTitle.innerText = "Cartographie & Impact";
                if (sideSubtitle) sideSubtitle.innerText = `${count} panneaux qualifiés (${locLabel})`;

                if (window.lastAvailabilityPdfUrl && pdfBtn) {
                    pdfBtn.href = window.lastAvailabilityPdfUrl;
                    pdfBtn.innerHTML = '<i class="fa-solid fa-file-pdf" style="color:#ffffff!important;"></i><span style="color:#ffffff!important;">Catalogue PDF</span>';
                    pdfBtn.classList.remove('hidden');
                } else if (pdfBtn) {
                    pdfBtn.classList.add('hidden');
                }
                if (modeToggle) modeToggle.classList.add('hidden');

                if (mobilePanelsBadge) {
                    mobilePanelsBadge.innerText = count;
                    mobilePanelsBadge.classList.remove('hidden');
                }

                displayPanelsOnSideMap(panels, null, null);
                renderSummarySection(null, 0, panels);
            }
        }

        function selectCampaignMonth(idx) {
            if (!currentCampaignPlan || !currentCampaignPlan.months[idx]) return;
            activeMonthIdx = idx;

            // Mise à jour visuelle des onglets mensuels
            const btns = document.querySelectorAll('.listing-month-btn');
            btns.forEach((b, i) => {
                if (i === idx) {
                    b.className = 'listing-month-btn px-2.5 py-1 rounded-lg text-xs font-bold transition-all shrink-0 bg-[#F4920D] text-white shadow-xs';
                } else {
                    b.className = 'listing-month-btn px-2.5 py-1 rounded-lg text-xs font-bold transition-all shrink-0 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200/80 dark:border-slate-700';
                }
            });

            const m = currentCampaignPlan.months[idx];
            const renderImg = document.getElementById('renderMapImage');
            if (renderImg && m.map_url) {
                renderImg.src = m.map_url;
            }

            displayPanelsOnSideMap(m.panels, m.stats, m.period_human);
            renderSummarySection(currentCampaignPlan, idx);
        }

        function displayPanelsOnSideMap(panels, stats = null, periodLabel = null) {
            if (!recommendationLayer || !map) return;
            recommendationLayer.clearLayers();
            markersMap = {};

            const overlayText = document.getElementById('mapOverlayText');
            const listEl = document.getElementById('listingPanelsList');
            const emptyState = document.getElementById('listingEmptyState');

            if (!panels || panels.length === 0) {
                if (emptyState) emptyState.classList.remove('hidden');
                if (listEl) listEl.innerHTML = '';
                return;
            }

            if (emptyState) emptyState.classList.add('hidden');
            const count = panels.length;

            if (overlayText) {
                overlayText.innerText = periodLabel ? `${count} faces actives · ${periodLabel}` : `${count} faces sélectionnées`;
            }

            const bounds = [];
            let listCardsHtml = '';

            // Affichage du cercle de recherche de disponibilité si actif
            if (window.currentSearchCircle && window.currentSearchCircle.lat && window.currentSearchCircle.lng) {
                const sc = window.currentSearchCircle;
                const radiusMeters = (sc.radius_km || 5.0) * 1000;
                const searchCircle = L.circle([sc.lat, sc.lng], {
                    radius: radiusMeters,
                    color: '#F4920D',
                    fillColor: '#F4920D',
                    fillOpacity: 0.08,
                    weight: 2,
                    dashArray: '6, 6'
                });
                searchCircle.bindTooltip(`🎯 Zone de recherche : ${sc.location} (${sc.radius_km} km)`, { permanent: false, direction: 'top' });
                recommendationLayer.addLayer(searchCircle);

                const centerPinIcon = L.divIcon({
                    className: 'leaflet-div-icon',
                    html: `
                        <div style="background:#1e293b; color:#ffffff; border-radius:12px; padding:3px 8px; font-weight:800; font-size:10px; border:2px solid #F4920D; box-shadow:0 2px 8px rgba(0,0,0,0.3); white-space:nowrap; display:inline-flex; align-items:center; gap:4px;">
                            <span>🎯</span> <span>${sc.location} · ${sc.radius_km} km</span>
                        </div>
                    `,
                    iconSize: [110, 24],
                    iconAnchor: [55, 12]
                });
                const centerMarker = L.marker([sc.lat, sc.lng], { icon: centerPinIcon, zIndexOffset: 400 });
                recommendationLayer.addLayer(centerMarker);

                const circleBounds = searchCircle.getBounds();
                bounds.push([circleBounds.getSouth(), circleBounds.getWest()]);
                bounds.push([circleBounds.getNorth(), circleBounds.getEast()]);
            }

            panels.forEach((p, idx) => {
                const num = idx + 1;
                const panelId = String(p.id || p.remorque || '').replace('.0', '');
                const lat = parseFloat(p.lat);
                const lng = parseFloat(p.lng);
                const photoUrl = p.photo || p.image_url || `https://remorquepublicitaire.be/wp-content/uploads/2021/07/${panelId}in.jpg`;
                const axe = p.axe_routier || p.code_route || '';
                const dir = p.direction ? `Vers ${p.direction}` : (p.direction_in ? `Dir. ${p.direction_in}` : '');
                const distKm = (p.distance_km !== null && p.distance_km !== undefined && p.distance_km > 0) ? `📍 ${p.distance_km} km` : '';
                const freq = p.frequentation_jour ? Number(p.frequentation_jour).toLocaleString('fr-FR') + ' v/j' : '';
                const ots = p.ots_mensuel ? Number(p.ots_mensuel).toLocaleString('fr-FR') + ' OTS' : '';
                const isPinned = p.is_pinned || false;
                const dispo = p.prochaine_dispo_human || p.prochaine_dispo || 'Disponible';

                if (!isNaN(lat) && !isNaN(lng)) {
                    bounds.push([lat, lng]);

                    const pinIcon = L.divIcon({
                        className: 'leaflet-div-icon',
                        html: `
                            <div class="map-pin-container" onclick="focusPanelOnMap('${panelId}')">
                                <div class="map-pin-circle">${num}</div>
                                <div class="map-pin-badge">#${panelId}</div>
                            </div>
                        `,
                        iconSize: [40, 48],
                        iconAnchor: [20, 15],
                        popupAnchor: [0, -18]
                    });

                    const marker = L.marker([lat, lng], { icon: pinIcon, zIndexOffset: 1000 + num });
                    marker.bindPopup(`
                        <div style="font-family:'Plus Jakarta Sans',sans-serif; font-size:12px; line-height:1.4;">
                            <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
                                <span style="background:#F4920D; color:white; font-weight:800; border-radius:50%; width:20px; height:20px; display:inline-flex; align-items:center; justify-content:center; font-size:11px;">${num}</span>
                                <span style="font-weight:700; color:#1e293b; font-size:13px;">#${panelId} ${p.ville || ''}</span>
                            </div>
                            <div style="color:#64748b; font-size:11px; font-weight:500;">${axe} ${dir ? '· ' + dir : ''}</div>
                            ${freq ? `<div style="color:#0f172a; font-size:11px; font-weight:600; margin-top:3px;">🚗 ${freq} · 👁️ ${ots}</div>` : ''}
                            ${distKm ? `<div style="color:#059669; font-size:11px; font-weight:600; margin-top:2px;">${distKm}</div>` : ''}
                            <img src="${photoUrl}" style="width:100%; border-radius:8px; margin-top:6px; max-height:95px; object-fit:cover;" onerror="this.remove()" />
                            <div style="margin-top:6px; text-align:right;">
                                <a href="${p.lien || '#'}" target="_blank" style="color:#F4920D; font-weight:700; text-decoration:none; font-size:11px;">Fiche panneau &rarr;</a>
                            </div>
                        </div>
                    `);
                    recommendationLayer.addLayer(marker);
                    markersMap[panelId] = marker;
                }

                // Carte riche dans la colonne 2 (Listing)
                listCardsHtml += `
                    <div id="listingCard_${panelId}" 
                         class="p-3 rounded-2xl bg-white dark:bg-slate-800/90 border border-slate-200/90 dark:border-slate-700/80 shadow-xs hover:border-[#F4920D] dark:hover:border-[#F4920D] transition-all">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex items-center gap-2 min-w-0">
                                <span class="w-6 h-6 rounded-full bg-[#F4920D] text-white font-extrabold flex items-center justify-center shrink-0 text-xs shadow-2xs">
                                    ${num}
                                </span>
                                <div class="min-w-0">
                                    <a href="${p.lien || '#'}" target="_blank" class="font-bold text-xs text-slate-900 dark:text-white hover:text-[#F4920D] truncate block">
                                        #${panelId} ${p.ville || ''} <span class="text-[11px] font-normal text-slate-500">${p.localisation ? '(' + p.localisation + ')' : ''}</span>
                                    </a>
                                </div>
                            </div>
                            ${isPinned ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold text-[10px] shrink-0 border border-amber-500/20">📌 Garanti</span>' : ''}
                        </div>

                        <div class="text-[11px] text-slate-600 dark:text-slate-300 mt-1 flex items-center gap-1.5 truncate">
                            <span class="font-semibold text-[#F4920D] shrink-0">${axe}</span>
                            <span class="truncate">${dir}</span>
                            ${distKm ? `<span class="ml-auto text-emerald-600 font-semibold shrink-0 text-[10px]">${distKm}</span>` : ''}
                        </div>

                        ${(!((window.currentTargetPeriods && window.currentTargetPeriods.length > 0) || (currentCampaignPlan && currentCampaignPlan.months && currentCampaignPlan.months.length > 0)) && (p.prochaine_dispo_human || p.prochaine_dispo)) ? `
                        <div class="mt-1 flex items-center gap-1.5 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium truncate">
                            <i class="fa-regular fa-calendar-check text-[10px] shrink-0"></i>
                            <span class="truncate">${p.prochaine_dispo_human || p.prochaine_dispo}</span>
                        </div>` : ''}

                        <div class="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between text-[11px]">
                            <div class="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300 text-[10px] sm:text-[11px]">
                                ${freq ? `<span>🚗 <b>${freq}</b></span>` : ''}
                                ${ots ? `<span>👁️ <b>${ots}</b></span>` : ''}
                            </div>
                            <div class="flex items-center gap-2">
                                <button type="button" onclick="toggleSelectPanel('${panelId}')" id="btnSelect_${panelId}" class="px-2 py-0.5 rounded-lg text-[10px] font-bold border transition ${isPinned ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-slate-100 dark:bg-slate-700/80 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-600 hover:bg-[#F4920D] hover:text-white hover:border-[#F4920D]'}">
                                    ${isPinned ? '✓ Retenu' : '+ Retenir'}
                                </button>
                                <button type="button" onclick="focusPanelOnMap('${panelId}')" class="text-[11px] font-bold text-[#F4920D] hover:underline flex items-center gap-1">
                                    <i class="fa-solid fa-crosshairs text-[10px]"></i> Localiser
                                </button>
                                <a href="${p.lien || '#'}" target="_blank" title="Ouvrir la fiche technique" class="text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                                    <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            });

            let expandBannerHtml = '';
            if (window.canExpandZone && window.peripheralCount > 0) {
                const nextR = window.nextRadiusKm || ((window.currentRadiusKm || 5) + 5);
                expandBannerHtml = `
                    <div class="mb-2.5 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 flex items-center justify-between gap-2 text-xs">
                        <div class="min-w-0">
                            <span class="font-bold">+${window.peripheralCount} panneau${window.peripheralCount > 1 ? 'x' : ''}</span> 
                            <span class="text-[11px] opacity-80">dans les communes voisines (rayon ${nextR} km)</span>
                        </div>
                        <button type="button" onclick="sendSuggestion('élargis la zone de 5km')" class="px-2.5 py-1 rounded-lg bg-[#F4920D] text-white font-bold text-[11px] hover:bg-[#e0840b] shrink-0 shadow-2xs">
                            Élargir la zone (+5 km)
                        </button>
                    </div>
                `;
            }

            listEl.innerHTML = expandBannerHtml + listCardsHtml;

            // Recadrage dynamique de la carte
            if (bounds.length > 0) {
                setTimeout(() => {
                    map.invalidateSize();
                    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
                }, 100);
            }
        }

        function formatPeriodHuman(p) {
            if (!p) return '';
            const m = String(p).match(/(\d{4})[-_](\d{1,2})/);
            if (!m) return p;
            const months = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];
            const mi = parseInt(m[2], 10) - 1;
            return `${months[mi] || m[2]} ${m[1]}`;
        }

        window.selectedPanels = [];
        function toggleSelectPanel(id) {
            id = String(id).replace('#', '');
            window.selectedPanels = window.selectedPanels || [];
            const idx = window.selectedPanels.indexOf(id);
            const btn = document.getElementById(`btnSelect_${id}`);
            if (idx >= 0) {
                window.selectedPanels.splice(idx, 1);
                if (btn) {
                    btn.className = "px-2 py-0.5 rounded-lg text-[10px] font-bold border transition bg-slate-100 dark:bg-slate-700/80 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-600 hover:bg-[#F4920D] hover:text-white hover:border-[#F4920D]";
                    btn.innerText = "+ Retenir";
                }
            } else {
                window.selectedPanels.push(id);
                if (btn) {
                    btn.className = "px-2 py-0.5 rounded-lg text-[10px] font-bold border transition bg-emerald-600 text-white border-emerald-600";
                    btn.innerText = "✓ Retenu";
                }
            }
            updateSelectionBar();
        }

        function updateSelectionBar() {
            const bar = document.getElementById('clientSelectionBar');
            const txt = document.getElementById('selectionCountText');
            if (!bar) return;
            if (window.selectedPanels && window.selectedPanels.length > 0) {
                bar.classList.remove('hidden');
                if (txt) txt.innerText = `${window.selectedPanels.length} remorque(s) retenue(s) : #${window.selectedPanels.join(', #')}`;
            } else {
                bar.classList.add('hidden');
            }
        }

        function validateClientSelection() {
            if (!window.selectedPanels || window.selectedPanels.length === 0) return;
            const msg = "On retient " + window.selectedPanels.map(id => "#" + id).join(" et ");
            window.selectedPanels = [];
            updateSelectionBar();
            sendSuggestion(msg);
        }

        function renderSummarySection(campaignPlan, activeMonthIdx = 0, searchPanels = null) {
            const summaryEmptyState = document.getElementById('summaryEmptyState');
            const summaryContent = document.getElementById('summaryContent');

            if (!summaryContent) return;

            if (campaignPlan && campaignPlan.months && campaignPlan.months.length > 0) {
                if (summaryEmptyState) summaryEmptyState.classList.add('hidden');
                summaryContent.classList.remove('hidden');

                const summary = campaignPlan.summary || {};
                const totalOts = Number(summary.total_cumulative_ots || 0).toLocaleString('fr-FR');
                const avgVeh = Number(summary.avg_veh_per_day || 0).toLocaleString('fr-FR');
                const totalFaces = summary.total_faces_deployed || (campaignPlan.months.length * 5);
                const activeM = campaignPlan.months[activeMonthIdx] || campaignPlan.months[0];
                const mStats = activeM.stats || {};
                const mVeh = Number(mStats.veh_per_day || 0).toLocaleString('fr-FR');
                const mOts = Number(mStats.ots_month || 0).toLocaleString('fr-FR');
                const deadline = activeM.deadline_full || '15 du mois précédent';
                const pdfUrl = campaignPlan.pdf_url || '#';

                // Axes touchés du mois
                const axesSet = new Set();
                (activeM.panels || []).forEach(p => {
                    const a = p.axe_routier || p.code_route;
                    if (a) axesSet.add(a);
                });
                const axesList = Array.from(axesSet).slice(0, 4).join(' · ');

                summaryContent.innerHTML = `
                    <!-- KPIs d'Impact Global -->
                    <div class="grid grid-cols-2 gap-2">
                        <div class="p-2.5 rounded-xl bg-orange-50/70 dark:bg-orange-950/20 border border-orange-200/80 dark:border-orange-800/40">
                            <div class="text-[10px] font-bold text-orange-600 dark:text-orange-400 uppercase tracking-wider flex items-center gap-1">
                                <i class="fa-solid fa-eye"></i> Audience Totale
                            </div>
                            <div class="text-sm font-black text-slate-900 dark:text-white mt-0.5">~${totalOts}</div>
                            <div class="text-[10px] text-slate-500 dark:text-slate-400">OTS cumulés (${campaignPlan.months.length} mois)</div>
                        </div>

                        <div class="p-2.5 rounded-xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                            <div class="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1">
                                <i class="fa-solid fa-car"></i> Trafic Moyen
                            </div>
                            <div class="text-sm font-black text-slate-900 dark:text-white mt-0.5">${avgVeh}</div>
                            <div class="text-[10px] text-slate-500 dark:text-slate-400">véhicules / jour</div>
                        </div>
                    </div>

                    <!-- Dispositif du mois actif -->
                    <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/60">
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-bold text-slate-800 dark:text-slate-200">
                                📅 Dispositif ${activeM.period_human}
                            </span>
                            <span class="text-[11px] font-bold text-[#F4920D] bg-[#F4920D]/10 px-2 py-0.5 rounded-md">
                                ${activeM.panels?.length || 5} faces
                            </span>
                        </div>
                        <div class="text-[11px] text-slate-600 dark:text-slate-300 mt-1 flex items-center justify-between">
                            <span>🚗 <b>${mVeh}</b> véh./j</span>
                            <span>👁️ <b>~${mOts}</b> OTS/mois</span>
                        </div>
                        ${axesList ? `
                        <div class="mt-1.5 pt-1.5 border-t border-slate-200/60 dark:border-slate-700/60 text-[10px] text-slate-500 dark:text-slate-400 truncate">
                            <span class="font-semibold text-slate-700 dark:text-slate-300">Axes :</span> ${axesList}
                        </div>` : ''}
                    </div>

                    <!-- Rétroplanning & Spécifications Bâches -->
                    <div class="p-3 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-800/40 space-y-1.5 text-[11px] text-amber-900 dark:text-amber-200">
                        <div class="font-bold flex items-center gap-1 text-xs">
                            <i class="fa-solid fa-calendar-check text-[#F4920D]"></i> Rétroplanning & Technique
                        </div>
                        <div class="text-slate-700 dark:text-slate-300 space-y-1">
                            <p>• <b>Format visuels bâche :</b> 390 × 200 cm <span class="text-slate-400">(bords perdus 392×202 cm)</span></p>
                            <p>• <b>Remise des maquettes :</b> Avant le <b>${deadline}</b></p>
                            <p>• <b>Logistique :</b> Tournée de pose sur 3 jours ouvrables</p>
                        </div>
                    </div>

                    <!-- Bouton Officiel Téléchargement PDF -->
                    ${pdfUrl !== '#' ? `
                    <a href="${pdfUrl}" target="_blank" download 
                       class="w-full py-2.5 px-3 rounded-xl bg-gradient-to-r from-[#F4920D] to-[#FF5B34] text-white font-bold text-xs shadow-sm hover:brightness-105 active:scale-98 transition flex items-center justify-center gap-2 text-center" style="color:#ffffff !important; text-decoration:none !important;">
                        <i class="fa-solid fa-file-pdf text-sm" style="color:#ffffff !important;"></i>
                        <span style="color:#ffffff !important;">Télécharger le Plan Média PDF (A4 Paysage)</span>
                    </a>` : ''}
                `;
            } else if (searchPanels && searchPanels.length > 0) {
                if (summaryEmptyState) summaryEmptyState.classList.add('hidden');
                summaryContent.classList.remove('hidden');

                const totalFreq = searchPanels.reduce((sum, p) => sum + (p.frequentation_jour || 0), 0);
                const totalOts = searchPanels.reduce((sum, p) => sum + (p.ots_mensuel || Math.round((p.frequentation_jour || 0) * 30 * 1.2)), 0);
                const totalFreqStr = Number(totalFreq).toLocaleString('fr-FR');
                const totalOtsStr = Number(totalOts).toLocaleString('fr-FR');

                summaryContent.innerHTML = `
                    <div class="grid grid-cols-2 gap-2">
                        <div class="p-2.5 rounded-xl bg-orange-50/70 dark:bg-orange-950/20 border border-orange-200/80 dark:border-orange-800/40">
                            <div class="text-[10px] font-bold text-orange-600 dark:text-orange-400 uppercase tracking-wider flex items-center gap-1">
                                <i class="fa-solid fa-eye"></i> Audience Mensuelle
                            </div>
                            <div class="text-sm font-black text-slate-900 dark:text-white mt-0.5">~${totalOtsStr}</div>
                            <div class="text-[10px] text-slate-500 dark:text-slate-400">OTS estimés sur 1 mois</div>
                        </div>

                        <div class="p-2.5 rounded-xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                            <div class="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1">
                                <i class="fa-solid fa-car"></i> Trafic Direct
                            </div>
                            <div class="text-sm font-black text-slate-900 dark:text-white mt-0.5">${totalFreqStr}</div>
                            <div class="text-[10px] text-slate-500 dark:text-slate-400">véhicules / jour</div>
                        </div>
                    </div>

                    <div class="p-3 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-800/40 text-[11px] text-amber-900 dark:text-amber-200">
                        <div class="font-bold flex items-center gap-1 text-xs">
                            <i class="fa-solid fa-lightbulb text-[#F4920D]"></i> Prochaine étape
                        </div>
                        <p class="mt-1 text-slate-700 dark:text-slate-300">
                            Indiquez dans le chat les mois souhaités pour générer un plan de campagne complet avec rotation et dossier PDF officiel.
                        </p>
                    </div>
                `;
            } else {
                if (summaryContent) { summaryContent.innerHTML = ''; summaryContent.classList.add('hidden'); }
                if (summaryEmptyState) summaryEmptyState.classList.remove('hidden');
            }
        }

        function focusPanelOnMap(panelId) {
            const marker = markersMap[panelId];
            if (marker && map) {
                map.flyTo(marker.getLatLng(), 14, { duration: 0.8 });
                marker.openPopup();
            }

            // Mettre en surbrillance la carte dans la colonne 2 (Listing)
            document.querySelectorAll('[id^="listingCard_"]').forEach(c => {
                c.classList.remove('ring-2', 'ring-[#F4920D]', 'bg-amber-50/50', 'dark:bg-amber-950/20');
            });
            const card = document.getElementById(`listingCard_${panelId}`);
            if (card) {
                card.classList.add('ring-2', 'ring-[#F4920D]', 'bg-amber-50/50', 'dark:bg-amber-950/20');
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        // ==========================================
        // AUTHENTIFICATION GOOGLE WORKSPACE & PROFIL
        // ==========================================
        let currentUser = null;
        let adminSalespeopleList = [];
        let allDossiers = [];

        async function initAuth() {
            // Vérifier session locale persistée
            const savedUserStr = localStorage.getItem('mmove_auth_user');
            const hasLoggedOut = localStorage.getItem('mmove_logged_out') === '1';

            if (savedUserStr && !hasLoggedOut) {
                try {
                    currentUser = JSON.parse(savedUserStr);
                } catch(e) {
                    currentUser = null;
                }
            }

            // Si aucune session n'est enregistrée et qu'on n'a pas explicitement cliqué sur déconnexion
            if ((!currentUser || !currentUser.id) && !hasLoggedOut) {
                try {
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: 'corentin@mediasee.be' })
                    });
                    const data = await res.json();
                    if (data.status === 'ok') {
                        currentUser = data.user;
                        localStorage.setItem('mmove_auth_user', JSON.stringify(currentUser));
                        localStorage.setItem('mmove_salesperson_id', currentUser.id);
                    }
                } catch(e) {
                    console.warn("Auto-connexion Corentin:", e);
                }
            }

            if (currentUser && currentUser.id) {
                onUserAuthenticated(currentUser);
                hideLoginModal();
            } else {
                showLoginModal();
            }

            // Initialiser Google Identity Services
            initGoogleGIS();
        }

        async function initGoogleGIS() {
            try {
                const cfgRes = await fetch('/api/auth/config');
                if (cfgRes.ok) {
                    const cfg = await cfgRes.json();
                    if (cfg.google_client_id && window.google && window.google.accounts) {
                        google.accounts.id.initialize({
                            client_id: cfg.google_client_id,
                            callback: handleGoogleCredentialResponse,
                            auto_select: false
                        });
                        const btnContainer = document.getElementById('googleSignInBtn');
                        if (btnContainer) {
                            google.accounts.id.renderButton(btnContainer, {
                                theme: "outline",
                                size: "large",
                                text: "signin_with",
                                shape: "pill",
                                width: 280
                            });
                        }
                    }
                }
            } catch(e) {
                console.warn("Google GIS non initialisé :", e);
            }
        }

        function showLoginModal() {
            const modal = document.getElementById('loginModal');
            if (modal) {
                modal.classList.remove('hidden');
                modal.classList.add('flex');
            }
        }

        function hideLoginModal() {
            const modal = document.getElementById('loginModal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        }

        async function handleGoogleCredentialResponse(response) {
            if (!response || !response.credential) return;
            await submitAuthPayload({ credential: response.credential });
        }

        async function handleEmailLoginSubmit(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const emailInput = document.getElementById('loginEmailInput');
            const email = (emailInput ? emailInput.value : '').trim();
            if (!email) return false;
            await submitAuthPayload({ email: email });
            return false;
        }

        async function loginDirectCorentin() {
            await submitAuthPayload({ email: 'corentin@mediasee.be' });
        }

        async function loginDirectDavid() {
            await submitAuthPayload({ email: 'david@mediasee.be' });
        }

        async function submitAuthPayload(payload) {
            const errBox = document.getElementById('loginErrorMessage');
            const errText = document.getElementById('loginErrorText');
            if (errBox) errBox.classList.add('hidden');

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.status === 'ok') {
                    currentUser = data.user;
                    localStorage.setItem('mmove_auth_user', JSON.stringify(currentUser));
                    localStorage.setItem('mmove_salesperson_id', currentUser.id);
                    localStorage.removeItem('mmove_logged_out');
                    onUserAuthenticated(currentUser);
                    hideLoginModal();
                    const roleLabel = currentUser.initials === 'DR' ? 'Directeur' : (currentUser.is_admin ? 'Admin' : 'Conseiller');
                    showLogsToast(`✓ Connecté : ${currentUser.name} (${roleLabel})`);
                } else {
                    if (errBox && errText) {
                        errText.textContent = data.message || "Erreur de connexion. Vérifiez votre adresse.";
                        errBox.classList.remove('hidden');
                    }
                }
            } catch(err) {
                if (errBox && errText) {
                    errText.textContent = "Erreur de communication avec le serveur d'authentification.";
                    errBox.classList.remove('hidden');
                }
            }
        }

        async function onUserAuthenticated(user) {
            updateProfileUI();

            // Si l'utilisateur est admin, charger la liste des commerciaux uniquement pour son filtre superviseur
            if (user.is_admin) {
                try {
                    const res = await fetch(`/api/salespeople?user_id=${encodeURIComponent(user.id)}`);
                    if (res.ok) {
                        adminSalespeopleList = await res.json();
                        populateAdminSelect();
                    }
                } catch(e) {
                    console.warn("Échec chargement liste commerciaux pour superviseur:", e);
                }
            } else {
                adminSalespeopleList = [];
            }

            loadDossiers();
        }

        function updateProfileUI() {
            if (!currentUser) return;
            const avatar = document.getElementById('profileAvatar');
            const name = document.getElementById('profileName');
            const roleBadge = document.getElementById('profileRoleBadge');
            const drawerTitle = document.getElementById('dossiersDrawerTitle');
            const drawerSub = document.getElementById('dossiersDrawerSubtitle');
            const adminFilterContainer = document.getElementById('adminCommercialFilterContainer');

            // Dropdown utilisateur
            const dropName = document.getElementById('userDropdownName');
            const dropEmail = document.getElementById('userDropdownEmail');
            const dropRole = document.getElementById('userDropdownRole');

            const isDirector = currentUser.initials === 'DR' || currentUser.role_title === 'Directeur';

            if (avatar) avatar.textContent = currentUser.initials;
            if (name) name.textContent = currentUser.name;
            if (dropName) dropName.textContent = currentUser.name;
            if (dropEmail) dropEmail.textContent = currentUser.email || 'Google Workspace';
            
            if (dropRole) {
                if (isDirector) {
                    dropRole.textContent = '👑 Directeur (Superviseur)';
                } else if (currentUser.is_admin) {
                    dropRole.textContent = '👑 Administrateur M Move';
                } else {
                    dropRole.textContent = '💼 Conseiller Commercial';
                }
            }

            if (currentUser.is_admin) {
                if (roleBadge) {
                    roleBadge.classList.remove('hidden');
                    roleBadge.textContent = isDirector ? 'Directeur' : 'Admin';
                    if (isDirector) {
                        roleBadge.className = 'text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-extrabold uppercase border border-blue-500/20';
                    } else {
                        roleBadge.className = 'text-[9px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600 dark:text-purple-400 font-extrabold uppercase border border-purple-500/20';
                    }
                }
                if (drawerTitle) drawerTitle.textContent = isDirector ? "Dossiers Commerciaux (Vue Directeur)" : "Dossiers Commerciaux (Vue Superviseur)";
                if (drawerSub) drawerSub.textContent = "Vue globale sur toutes les propositions de l'équipe";
                if (adminFilterContainer) adminFilterContainer.classList.remove('hidden');
            } else {
                if (roleBadge) roleBadge.classList.add('hidden');
                if (drawerTitle) drawerTitle.textContent = "Mes Dossiers Commerciaux";
                if (drawerSub) drawerSub.textContent = `Propositions de ${currentUser.name}`;
                if (adminFilterContainer) adminFilterContainer.classList.add('hidden');
            }
        }

        function populateAdminSelect() {
            const adminSelect = document.getElementById('adminSalespersonSelect');
            if (!adminSelect || !currentUser || !currentUser.is_admin) return;

            adminSelect.innerHTML = '<option value="ALL">👥 Tous les commerciaux</option>';
            adminSalespeopleList.forEach(sp => {
                const opt = document.createElement('option');
                opt.value = sp.initials;
                opt.textContent = `${sp.name} (${sp.initials})`;
                adminSelect.appendChild(opt);
            });
        }

        function toggleUserDropdown() {
            const menu = document.getElementById('userDropdownMenu');
            if (menu) menu.classList.toggle('hidden');
        }

        // Fermer le dropdown de profil si on clique ailleurs
        document.addEventListener('click', (e) => {
            const btn = document.getElementById('currentProfileBtn');
            const menu = document.getElementById('userDropdownMenu');
            if (btn && menu && !btn.contains(e.target) && !menu.contains(e.target)) {
                menu.classList.add('hidden');
            }
        });

        function logoutUser() {
            currentUser = null;
            localStorage.removeItem('mmove_auth_user');
            localStorage.removeItem('mmove_salesperson_id');
            localStorage.setItem('mmove_logged_out', '1');
            const menu = document.getElementById('userDropdownMenu');
            if (menu) menu.classList.add('hidden');
            showLoginModal();
            showLogsToast("Déconnecté.");
        }

        // --- GESTION DU TIROIR DES DOSSIERS ---
        function toggleDossiersDrawer() {
            const drawer = document.getElementById('dossiersDrawer');
            const backdrop = document.getElementById('dossiersDrawerBackdrop');
            if (!drawer) return;

            const isClosed = drawer.classList.contains('-translate-x-full');
            if (isClosed) {
                drawer.classList.remove('-translate-x-full');
                if (backdrop) {
                    backdrop.classList.remove('hidden', 'opacity-0', 'pointer-events-none');
                    backdrop.classList.add('opacity-100');
                }
                loadDossiers();
            } else {
                closeDossiersDrawer();
            }
        }

        function closeDossiersDrawer() {
            const drawer = document.getElementById('dossiersDrawer');
            const backdrop = document.getElementById('dossiersDrawerBackdrop');
            if (drawer) drawer.classList.add('-translate-x-full');
            if (backdrop) {
                backdrop.classList.remove('opacity-100');
                backdrop.classList.add('opacity-0', 'pointer-events-none');
                setTimeout(() => backdrop.classList.add('hidden'), 300);
            }
        }

        async function loadDossiers() {
            try {
                const adminSelect = document.getElementById('adminSalespersonSelect');
                const filterVal = (currentUser.is_admin && adminSelect) ? adminSelect.value : '';
                const url = `/api/dossiers?user_id=${encodeURIComponent(currentUser.id)}&filter=${encodeURIComponent(filterVal)}`;
                const res = await fetch(url);
                if (res.ok) {
                    allDossiers = await res.json();
                    const badge = document.getElementById('dossiersCountBadge');
                    if (badge) badge.textContent = allDossiers.length;
                    filterDossiersList();
                }
            } catch (e) {
                console.warn("Erreur chargement dossiers:", e);
            }
        }

        function onAdminFilterSalespersonChanged(val) {
            loadDossiers();
        }

        function filterDossiersList() {
            const searchInput = document.getElementById('dossierSearchInput');
            const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
            const container = document.getElementById('dossiersListContainer');
            if (!container) return;

            const filtered = allDossiers.filter(d => {
                const client = (d.client_name || '').toLowerCase();
                const loc = (d.location || '').toLowerCase();
                const sp = (d.salesperson_name || '').toLowerCase();
                const periods = (d.periods || []).join(' ').toLowerCase();
                return client.includes(query) || loc.includes(query) || sp.includes(query) || periods.includes(query);
            });

            if (filtered.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-400 text-xs">
                        <i class="fa-solid fa-folder-open text-2xl mb-2 text-slate-300 dark:text-slate-600"></i>
                        <p>${query ? 'Aucun dossier ne correspond à votre recherche.' : 'Aucun dossier enregistré.'}</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = '';
            filtered.forEach(d => {
                const card = document.createElement('div');
                card.className = "p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 hover:border-[#F4920D]/40 transition space-y-2";
                
                const periodsBadges = (d.periods || []).map(p => 
                    `<span class="px-1.5 py-0.5 rounded bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 text-[10px] font-semibold border border-slate-200 dark:border-slate-700">${p}</span>`
                ).join(' ');

                card.innerHTML = `
                    <div class="flex items-start justify-between gap-2">
                        <div>
                            <h4 class="text-xs font-black text-slate-900 dark:text-white flex items-center gap-1.5">
                                <i class="fa-solid fa-file-lines text-[#F4920D]"></i> ${d.client_name || 'Client Partenaire'}
                            </h4>
                            <p class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                                <b>${d.location || 'Wallonie'}</b> · ${d.faces_count || 0} faces · ~${Number(d.total_ots || 0).toLocaleString('fr-FR')} OTS
                            </p>
                        </div>
                        <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 shrink-0">
                            ${d.salesperson_initials || ''}
                        </span>
                    </div>

                    <div class="flex items-center gap-1 flex-wrap">
                        ${periodsBadges}
                    </div>

                    <div class="pt-1.5 border-t border-slate-200/80 dark:border-slate-700/60 flex items-center justify-between gap-2 text-[11px]">
                        <span class="text-[10px] text-slate-400">${d.created_at ? d.created_at.slice(0, 16) : ''}</span>
                        <div class="flex items-center gap-1.5">
                            ${d.pdf_url ? `
                                <a href="${d.pdf_url}" target="_blank" class="px-2 py-1 rounded-lg bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-semibold transition flex items-center gap-1">
                                    <i class="fa-solid fa-file-pdf text-red-500"></i> PDF
                                </a>
                            ` : ''}
                            <button onclick="reloadDossier('${d.id}')" class="px-2.5 py-1 rounded-lg bg-[#F4920D] hover:bg-[#FF5B34] text-white font-bold transition flex items-center gap-1 shadow-xs">
                                <i class="fa-solid fa-arrow-rotate-left text-[10px]"></i> Recharger
                            </button>
                            <button onclick="deleteDossier('${d.id}', '${(d.client_name || 'ce dossier').replace(/'/g, "\\'")}')" 
                                    class="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition flex items-center justify-center" 
                                    title="Supprimer ce dossier">
                                <i class="fa-solid fa-trash-can text-xs"></i>
                            </button>
                        </div>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        async function reloadDossier(dossierId) {
            try {
                const res = await fetch(`/api/dossier?id=${encodeURIComponent(dossierId)}&user_id=${encodeURIComponent(currentUser ? currentUser.id : 'CH')}`);
                if (!res.ok) {
                    showLogsToast("⚠️ Impossible de charger ce dossier");
                    return;
                }
                const dossier = await res.json();
                
                // 1. Quitter intégralement le dossier en cours et réinitialiser la discussion
                history = [];
                detailedLogs = [];
                window.lastAvailabilityPdfUrl = null;
                window.canExpandZone = false;
                window.peripheralCount = 0;
                window.peripheralCities = [];
                window.currentTargetPeriods = null;
                window.currentTargetLocation = null;
                window.currentSearchCircle = null;
                window.currentRadiusKm = 5;
                window.nextRadiusKm = 10;

                const chatMessages = document.getElementById('chatMessages');
                chatMessages.innerHTML = '';

                // 2. Mettre à jour l'annonceur
                const clientInput = document.getElementById('clientNameInput');
                if (clientInput) clientInput.value = dossier.client_name || '';

                // 3. Mettre à jour la cartographie et les listings
                currentCampaignPlan = dossier.campaign_plan || null;
                updateSideMap(dossier.campaign_plan, dossier.panels);

                // 4. Afficher le dossier rechargé comme nouveau point de départ exclusif
                const pdfLink = dossier.pdf_url 
                    ? `\n\n📄 **[Télécharger le Plan Média PDF](${dossier.pdf_url})**` 
                    : '';
                const textMsg = `📁 **Dossier rechargé : ${dossier.client_name}**\n\n- **Conseiller :** ${dossier.salesperson_name || 'Conseiller M Move'} (${dossier.salesperson_initials || ''})\n- **Dispositif :** ${dossier.faces_count || (dossier.panels || []).length} faces à ${dossier.location || 'Wallonie'}\n- **Périodes :** ${(dossier.periods || []).join(', ')}\n- **Audience estimée :** ~${Number(dossier.total_ots || 0).toLocaleString('fr-FR')} OTS${pdfLink}\n\n*Le dossier en cours a été quitté. Vous travaillez désormais exclusivement sur ce dossier, vous pouvez continuer à le faire évoluer dans le chat.*`;
                
                appendMessage('model', textMsg, dossier.panels, {}, dossier.campaign_plan, '📁 Dossier actif', 'Dossier Commercial');
                history.push({ role: 'model', text: textMsg });

                closeDossiersDrawer();
                showLogsToast(`✓ Dossier « ${dossier.client_name} » rechargé (dossier précédent quitté)`);
            } catch (e) {
                console.error("Erreur rechargement dossier:", e);
                showLogsToast("⚠️ Erreur lors du chargement du dossier");
            }
        }

        async function deleteDossier(dossierId, clientName) {
            if (!confirm(`Êtes-vous sûr de vouloir supprimer définitivement le dossier « ${clientName} » ?`)) {
                return;
            }
            try {
                const res = await fetch(`/api/dossier/delete?id=${encodeURIComponent(dossierId)}&user_id=${encodeURIComponent(currentUser.id)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: dossierId, user_id: currentUser.id })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    showLogsToast(`✓ Dossier « ${clientName} » supprimé.`);
                    loadDossiers();
                } else {
                    showLogsToast(`⚠️ ${data.error || "Impossible de supprimer ce dossier"}`);
                }
            } catch (e) {
                console.error("Erreur suppression dossier:", e);
                showLogsToast("⚠️ Erreur réseau lors de la suppression");
            }
        }

        function onPdfDownloadTriggered() {
            showLogsToast("✓ Dossier commercial enregistré dans vos dossiers !");
            setTimeout(() => {
                loadDossiers();
            }, 800);
        }

        function startNewProposition() {
            // Notifier le serveur pour réinitialiser le contexte actif du conseiller
            fetch(`/api/context/reset?user_id=${encodeURIComponent(currentUser ? currentUser.id : 'CH')}`, { method: 'POST' }).catch(() => {});

            const clientInput = document.getElementById('clientNameInput');
            if (clientInput) clientInput.value = '';

            const chatMessages = document.getElementById('chatMessages');
            const welcomeMsg = chatMessages.firstElementChild;
            chatMessages.innerHTML = '';
            if (welcomeMsg) chatMessages.appendChild(welcomeMsg);
            history = [];
            detailedLogs = [];
            currentCampaignPlan = null;
            window.lastAvailabilityPdfUrl = null;
            window.canExpandZone = false;
            window.peripheralCount = 0;
            window.peripheralCities = [];
            window.currentTargetPeriods = null;
            window.currentTargetLocation = null;
            window.currentSearchCircle = null;
            window.currentRadiusKm = 5;
            window.nextRadiusKm = 10;

            // Réinitialiser Colonne 2 (Listing)
            const listTitle = document.getElementById('listingColTitle');
            const listSubtitle = document.getElementById('listingColSubtitle');
            const listCount = document.getElementById('listingColCount');
            const tabsBar = document.getElementById('listingMonthTabsBar');
            const panelsList = document.getElementById('listingPanelsList');
            const listEmpty = document.getElementById('listingEmptyState');
            const mobilePanelsBadge = document.getElementById('mobilePanelsBadge');

            if (listTitle) listTitle.innerText = "Sélection Emplacements";
            if (listSubtitle) listSubtitle.innerText = "Panneaux 8m² recommandés";
            if (listCount) listCount.innerText = "0 faces";
            if (tabsBar) { tabsBar.innerHTML = ''; tabsBar.classList.add('hidden'); }
            if (panelsList) panelsList.innerHTML = '';
            if (listEmpty) listEmpty.classList.remove('hidden');
            if (mobilePanelsBadge) { mobilePanelsBadge.innerText = '0'; mobilePanelsBadge.classList.add('hidden'); }

            // Réinitialiser Colonne 3 (Carte & Résumés)
            const sideTitle = document.getElementById('sideMapTitle');
            const sideSubtitle = document.getElementById('sideMapSubtitle');
            const pdfBtn = document.getElementById('sidePdfDownloadBtn');
            const modeToggle = document.getElementById('mapModeToggle');
            const summaryEmpty = document.getElementById('summaryEmptyState');
            const summaryContent = document.getElementById('summaryContent');

            if (sideTitle) sideTitle.innerText = "Cartographie & Impact";
            if (sideSubtitle) sideSubtitle.innerText = "Réseau 8m² Wallonie";
            if (pdfBtn) pdfBtn.classList.add('hidden');
            if (modeToggle) modeToggle.classList.add('hidden');
            if (summaryContent) { summaryContent.innerHTML = ''; summaryContent.classList.add('hidden'); }
            if (summaryEmpty) summaryEmpty.classList.remove('hidden');

            // Réinitialiser la carte vers le réseau global
            if (typeof initLeafletMap === 'function') {
                initLeafletMap();
            }
            showLogsToast("✓ Nouvelle proposition vierge prête");
        }

        function onClientNameInputChanged(val) {
            if (val.trim()) {
                showLogsToast(`✓ Annonceur défini : ${val.trim()}`);
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            initLeafletMap();
            initAuth();
        });
    </script>

    <!-- TOAST NOTIFICATION LOGS -->
    <div id="logsToast" class="fixed bottom-5 right-5 z-50 transform translate-y-10 opacity-0 pointer-events-none transition-all duration-300 bg-slate-900/95 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-lg border border-slate-700 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-emerald-400"></i>
        <span id="logsToastMsg">Logs copiés dans le presse-papier !</span>
    </div>

    <!-- MODAL LOGS DE CONVERSATION (Discret) -->
    <div id="logsModal" onclick="if(event.target === this) closeConversationLogsModal()" class="fixed inset-0 z-50 hidden items-center justify-center bg-black/60 backdrop-blur-xs p-4">
        <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
            <!-- Modal Header -->
            <div class="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-800/60">
                <div class="flex items-center gap-2.5">
                    <span class="w-7 h-7 rounded-lg bg-[#F4920D]/10 text-[#F4920D] flex items-center justify-center text-xs font-bold border border-[#F4920D]/20">
                        <i class="fa-solid fa-code"></i>
                    </span>
                    <div>
                        <h3 class="text-xs font-bold text-slate-900 dark:text-white">Logs d'échanges de la conversation</h3>
                        <p class="text-[10px] text-slate-500 dark:text-slate-400">Copiez ce contenu pour le transmettre directement à l'assistant IA</p>
                    </div>
                </div>
                <button onclick="closeConversationLogsModal()" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition">
                    <i class="fa-solid fa-xmark text-sm"></i>
                </button>
            </div>

            <!-- Modal Content : Textarea pré-rempli et sélectionnable -->
            <div class="p-4 flex-1 flex flex-col min-h-0">
                <textarea id="logsTextarea" readonly class="w-full flex-1 p-3.5 font-mono text-[11px] leading-relaxed bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 rounded-xl resize-none focus:outline-none focus:ring-1 focus:ring-[#F4920D] select-all overflow-y-auto" rows="14"></textarea>
            </div>

            <!-- Modal Footer : Actions rapides -->
            <div class="px-5 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-between gap-2">
                <span id="logsCopyFeedback" class="text-xs text-emerald-600 dark:text-emerald-400 font-semibold hidden flex items-center gap-1">
                    <i class="fa-solid fa-check"></i> Copié dans le presse-papier !
                </span>
                <div class="flex items-center gap-2 ml-auto">
                    <button onclick="downloadLogs('txt')" class="px-3 py-1.5 text-xs font-semibold rounded-xl bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition flex items-center gap-1.5">
                        <i class="fa-solid fa-download"></i> .TXT
                    </button>
                    <button onclick="downloadLogs('json')" class="px-3 py-1.5 text-xs font-semibold rounded-xl bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition flex items-center gap-1.5">
                        <i class="fa-solid fa-file-code"></i> .JSON
                    </button>
                    <button id="logsCopyBtn" onclick="copyConversationLogs()" class="px-4 py-1.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#F4920D] to-[#FF5B34] text-white shadow-xs hover:brightness-110 active:scale-95 transition flex items-center gap-1.5">
                        <i class="fa-solid fa-copy"></i> Copier les logs
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- TIROIR LATÉRAL DOSSIERS & HISTORIQUE -->
    <div id="dossiersDrawerBackdrop" onclick="closeDossiersDrawer()" class="fixed inset-0 z-40 hidden bg-black/50 backdrop-blur-xs transition-opacity duration-300 opacity-0 pointer-events-none"></div>
    <aside id="dossiersDrawer" class="fixed top-0 left-0 bottom-0 z-50 w-full sm:w-[480px] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col transform -translate-x-full transition-transform duration-300 ease-in-out">
        <!-- Header du Tiroir -->
        <div class="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-800/60">
            <div class="flex items-center gap-2.5">
                <span class="w-8 h-8 rounded-xl bg-[#F4920D]/10 text-[#F4920D] flex items-center justify-center text-sm font-bold border border-[#F4920D]/20">
                    <i class="fa-solid fa-folder-open"></i>
                </span>
                <div>
                    <h2 id="dossiersDrawerTitle" class="text-sm font-bold text-slate-900 dark:text-white">Dossiers Commerciaux</h2>
                    <p id="dossiersDrawerSubtitle" class="text-[11px] text-slate-500 dark:text-slate-400">Historique et propositions sauvegardées</p>
                </div>
            </div>
            <button onclick="closeDossiersDrawer()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
                <i class="fa-solid fa-xmark text-sm"></i>
            </button>
        </div>

        <!-- Filtres (Recherche & Filtre Commercial pour Admin) -->
        <div class="p-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 space-y-2">
            <!-- Recherche rapide -->
            <div class="relative">
                <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-400"></i>
                <input type="text" id="dossierSearchInput" placeholder="Rechercher un client, ville, période..." oninput="filterDossiersList()"
                    class="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#F4920D] text-slate-800 dark:text-slate-200">
            </div>

            <!-- Filtre commercial (Visible uniquement si Admin) -->
            <div id="adminCommercialFilterContainer" class="hidden flex items-center gap-2 pt-1">
                <span class="text-[11px] font-bold text-slate-500 dark:text-slate-400 shrink-0">Conseiller :</span>
                <select id="adminSalespersonSelect" onchange="onAdminFilterSalespersonChanged(this.value)"
                    class="flex-1 py-1 px-2 text-xs font-semibold bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#F4920D] text-slate-800 dark:text-slate-200">
                    <option value="ALL">👥 Tous les commerciaux</option>
                </select>
            </div>
        </div>

        <!-- Liste des Dossiers -->
        <div id="dossiersListContainer" class="flex-1 overflow-y-auto p-3 space-y-2.5">
            <div class="text-center py-8 text-slate-400 text-xs">
                <i class="fa-solid fa-folder-open text-2xl mb-2 text-slate-300 dark:text-slate-600"></i>
                <p>Aucun dossier pour le moment.</p>
                <p class="text-[11px] text-slate-400 mt-1">Générez une première proposition dans le chat !</p>
            </div>
        </div>
    </aside>

    <!-- ÉCRAN D'AUTHENTIFICATION GOOGLE WORKSPACE (@mediasee.be) -->
    <div id="loginModal" class="fixed inset-0 z-50 hidden items-center justify-center bg-slate-900/80 backdrop-blur-md p-4">
        <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-2xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <!-- Header Logo & Titre -->
            <div class="p-6 text-center border-b border-slate-100 dark:border-slate-800 bg-gradient-to-b from-amber-500/5 to-transparent">
                <div class="w-14 h-14 mx-auto mb-3 rounded-2xl bg-gradient-to-tr from-[#F4920D] to-[#FF5B34] flex items-center justify-center text-white shadow-lg shadow-orange-500/20">
                    <span class="font-black text-2xl tracking-tighter">m</span>
                </div>
                <h2 class="text-base font-black text-slate-900 dark:text-white">Espace Commercial M Move</h2>
                <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">Connexion réservée aux comptes Google Workspace</p>
                <div class="inline-flex items-center gap-1.5 px-3 py-1 mt-3 rounded-full bg-slate-100 dark:bg-slate-800 text-[11px] font-semibold text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 shadow-2xs">
                    <i class="fa-brands fa-google text-red-500 text-xs"></i>
                    <span>@mediasee.be</span>
                </div>
            </div>

            <!-- Corps : Connexion Google ou Email Workspace -->
            <div class="p-6 space-y-4">
                <!-- Bouton officiel Google Sign-In (initialisé automatiquement si Client ID présent) -->
                <div id="googleSignInWrapper" class="flex justify-center empty:hidden">
                    <div id="googleSignInBtn"></div>
                </div>

                <!-- Formulaire email Workspace -->
                <form id="loginEmailForm" onsubmit="handleEmailLoginSubmit(event); return false;" action="javascript:void(0);" method="POST" class="space-y-3">
                    <div>
                        <label for="loginEmailInput" class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                            Adresse email Workspace
                        </label>
                        <div class="relative">
                            <i class="fa-solid fa-envelope absolute left-3.5 top-3 text-xs text-slate-400"></i>
                            <input type="email" id="loginEmailInput" placeholder="votre-adresse@mediasee.be" required
                                class="w-full pl-9 pr-3 py-2 text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#F4920D] text-slate-900 dark:text-white transition">
                        </div>
                    </div>

                    <button type="submit" id="loginSubmitBtn"
                        class="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-[#F4920D] to-[#FF5B34] text-white text-xs font-bold shadow-md hover:brightness-105 active:scale-98 transition flex items-center justify-center gap-2">
                        <i class="fa-brands fa-google"></i>
                        <span>Se connecter avec Google Workspace</span>
                    </button>
                </form>

                <!-- Raccourcis rapides Superviseurs (Corentin Admin & David Directeur) -->
                <div class="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-2">
                    <button type="button" onclick="loginDirectCorentin()"
                        class="w-full py-2 px-3 rounded-xl bg-purple-50 dark:bg-purple-950/40 hover:bg-purple-100 dark:hover:bg-purple-900/50 text-purple-700 dark:text-purple-300 text-xs font-bold border border-purple-200 dark:border-purple-800 transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-crown text-amber-500"></i>
                        <span>Connexion : Corentin Hubert (Admin)</span>
                    </button>
                    <button type="button" onclick="loginDirectDavid()"
                        class="w-full py-2 px-3 rounded-xl bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-100 dark:hover:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-bold border border-blue-200 dark:border-blue-800 transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-user-tie text-blue-500"></i>
                        <span>Connexion : David Rossomme (Directeur)</span>
                    </button>
                </div>

                <!-- Message d'erreur -->
                <div id="loginErrorMessage" class="hidden p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs text-red-600 dark:text-red-400 font-medium flex items-center gap-2">
                    <i class="fa-solid fa-circle-exclamation text-sm shrink-0"></i>
                    <span id="loginErrorText">Erreur d'authentification</span>
                </div>
            </div>

            <!-- Footer Sécurité -->
            <div class="p-3.5 bg-slate-50 dark:bg-slate-800/60 border-t border-slate-100 dark:border-slate-800 text-center text-[11px] text-slate-400 dark:text-slate-500 flex items-center justify-center gap-1.5">
                <i class="fa-solid fa-shield-halved text-[#F4920D]"></i>
                <span>Authentification sécurisée · Dossiers commerciaux étanches</span>
            </div>
        </div>
    </div>
</body>
</html>"""
            self.wfile.write(html_content.encode("utf-8"))
            return

        self._set_headers(404)
        self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        req_path = parsed.path

        # Réinitialisation du contexte (quitter le dossier en cours)
        if req_path == "/api/context/reset":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            query_params = urllib.parse.parse_qs(parsed.query)
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                data = {}
            user_id = data.get("user_id") or query_params.get("user_id", ["CH"])[0]
            coordinator.reset_context(salesperson_id=user_id)
            self._set_headers(200)
            self.wfile.write(b'{"status": "ok", "message": "Contexte reinitialise"}')
            return

        # Authentification Google Workspace (@mediasee.be)
        if req_path == "/api/auth/login":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                email = data.get("email")
                credential = data.get("credential")

                user = coordinator.salesperson_service.authenticate(email=email, credential_jwt=credential)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "ok", "user": user}, ensure_ascii=False).encode("utf-8"))
            except PermissionError as pe:
                self._set_headers(403)
                self.wfile.write(json.dumps({"status": "error", "message": str(pe)}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._set_headers(400)
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return

        # Suppression d'un dossier commercial
        if req_path == "/api/dossier/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            query_params = urllib.parse.parse_qs(parsed.query)
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                data = {}

            dossier_id = data.get("id") or query_params.get("id", [None])[0]
            user_id = data.get("user_id") or query_params.get("user_id", [None])[0]

            if not dossier_id:
                self._set_headers(400)
                self.wfile.write(b'{"error": "Dossier ID required"}')
                return

            ok = coordinator.dossier_service.delete_dossier(dossier_id, requesting_user_id=user_id)
            if ok:
                self._set_headers(200)
                self.wfile.write(b'{"success": true, "message": "Dossier supprime"}')
            else:
                self._set_headers(403)
                self.wfile.write(b'{"error": "Impossible de supprimer ce dossier ou droits insuffisants"}')
            return

        if req_path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                user_msg = data.get("message", "")
                history = data.get("history", [])

                if not user_msg:
                    self._set_headers(400)
                    self.wfile.write(b'{"error": "Message required"}')
                    return

                client_name = data.get("client_name", "")
                salesperson_id = data.get("salesperson_id", "")

                res = coordinator.process_message(
                    user_msg,
                    conversation_history=history,
                    client_name=client_name,
                    salesperson_id=salesperson_id
                )
                self._set_headers(200)
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._set_headers(500)
                err_resp = {"error": "Server error", "details": str(e)}
                self.wfile.write(json.dumps(err_resp, ensure_ascii=False).encode("utf-8"))
            return

        if self.path == "/api/sync/trigger":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}

            target = data.get("type", "all")
            results = {}
            if target in ["dispo", "all"]:
                results["dispo"] = coordinator.sync.check_disponibilites(force=True)
            if target in ["panels", "all"]:
                results["panneaux"] = coordinator.sync.check_panneaux(force=True)

            results["summary"] = coordinator.sync.get_summary()
            self._set_headers(200)
            self.wfile.write(json.dumps(results, ensure_ascii=False).encode("utf-8"))
            return

        self._set_headers(404)
        self.wfile.write(b'{"error": "Not found"}')

def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, MmoveHandler)
    print(f"Serveur M Move Multi-Agents démarré sur http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
