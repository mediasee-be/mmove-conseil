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
        if self.path == "/api/health":
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

        if self.path == "/api/sync/status":
            self._set_headers(200)
            sync_info = coordinator.sync.get_summary()
            self.wfile.write(json.dumps(sync_info, ensure_ascii=False).encode("utf-8"))
            return

        if self.path == "/api/network-trailers":
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
        if self.path.startswith("/api/map/"):
            filename = os.path.basename(self.path.split("?")[0])
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

        # Téléchargement du Plan Média PDF (A4 Paysage)
        if self.path.startswith("/api/download-plan-pdf") or self.path.startswith("/api/pdf/"):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed.query)
            filename = query_params.get("file", [None])[0]
            if not filename:
                filename = os.path.basename(parsed.path)
            
            clean_filename = os.path.basename(filename)
            pdf_path = os.path.join("data", "pdf", clean_filename)
            if os.path.exists(pdf_path) and os.path.isfile(pdf_path):
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
        if self.path.startswith("/static/"):
            rel_path = self.path.lstrip("/")
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

        if self.path == "/favicon.ico":
            icon_path = "static/bot-avatar.png"
            if os.path.exists(icon_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(icon_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        # Interface Web interactive locale
        if self.path == "/" or self.path == "/index.html":
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
    <header class="bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 px-4 py-2.5 flex items-center justify-between shadow-xs z-10 shrink-0">
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
                <span class="text-xs px-2.5 py-0.5 rounded-full bg-[#F4920D]/10 text-[#F4920D] font-bold border border-[#F4920D]/20">Conseil 8m²</span>
                <span id="headerPanelCount" class="text-xs text-[#666] dark:text-slate-400 font-medium hidden sm:inline">133 Panneaux &middot; 266 Faces Wallonie</span>
            </div>
        </div>

        <div class="flex items-center space-x-2">
            <!-- Mobile Toggle Chat / Carte -->
            <div class="flex lg:hidden items-center bg-slate-100 dark:bg-slate-800 rounded-xl p-0.5 border border-slate-200 dark:border-slate-700">
                <button type="button" id="viewChatBtn" onclick="switchMobileView('chat')" class="px-2.5 py-1 text-xs font-bold rounded-lg bg-white dark:bg-slate-900 text-[#F4920D] shadow-xs transition">
                    <i class="fa-solid fa-comments mr-1"></i>Chat
                </button>
                <button type="button" id="viewMapBtn" onclick="switchMobileView('map')" class="px-2.5 py-1 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition flex items-center gap-1">
                    <i class="fa-solid fa-map-location-dot"></i>
                    <span>Carte</span>
                    <span id="mobilePinBadge" class="hidden px-1.5 py-0.2 rounded-full text-[10px] bg-[#F4920D] text-white font-extrabold">0</span>
                </button>
            </div>

            <!-- Sync Live Badge -->
            <div id="statsBadge" class="hidden xl:flex text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 py-1.5 rounded-xl text-[#666] dark:text-slate-300 items-center space-x-2 shadow-inner">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>133 panneaux (266 faces)</span>
            </div>

            <!-- Sync Button -->
            <button onclick="triggerSync('all')" title="Forcer la vérification immédiate des disponibilités" class="text-xs bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 rounded-xl text-[#F4920D] hover:text-[#FF5B34] transition flex items-center space-x-1 font-medium">
                <i class="fa-solid fa-arrows-rotate" id="syncIcon"></i>
                <span class="hidden md:inline">Sync</span>
            </button>

            <!-- Dark / Light Mode Toggle -->
            <button onclick="toggleDarkMode()" title="Changer le thème (Clair / Sombre)" class="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center justify-center">
                <i id="themeIcon" class="fa-solid fa-moon text-[#666] dark:text-amber-400 text-sm"></i>
            </button>

            <!-- Bouton Discret Exporter les Logs (Debug / Retours) -->
            <button onclick="openConversationLogsModal()" title="Extraire les logs de la conversation pour débug / retours" class="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center justify-center text-slate-400 hover:text-[#F4920D] dark:text-slate-500 dark:hover:text-[#F4920D] opacity-60 hover:opacity-100" aria-label="Logs de conversation">
                <i class="fa-solid fa-code text-xs"></i>
            </button>
        </div>
    </header>

    <!-- MAIN TWO-PANEL WORKSPACE (Chat à gauche, Carte à droite) -->
    <main class="flex-1 flex overflow-hidden relative">
        <!-- COLONNE GAUCHE : CHAT & CONVERSATION -->
        <section id="chatSection" class="flex-1 flex flex-col min-w-0 h-full border-r border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
            <!-- Zone des messages de discussion -->
            <div id="chatMessages" class="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 w-full">
                <!-- Message initial de bienvenue -->
                <div class="flex items-start space-x-3">
                    <div class="w-9 h-9 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xs shrink-0 mt-0.5">
                        <img src="/static/bot-avatar.png" alt="Conseiller M Move" class="w-full h-full object-cover object-top">
                    </div>
                    <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-5 max-w-3xl text-sm leading-relaxed shadow-sm text-[#666] dark:text-slate-200">
                        <p class="font-bold text-[#F4920D] mb-2 flex items-center gap-1.5">
                            <i class="fa-solid fa-sparkles text-[#FF5B34]"></i> Conseiller Commercial M Move
                        </p>
                        Bonjour ! Je suis votre conseiller expert pour le réseau de panneaux publicitaires 8m² M Move en Wallonie (133 panneaux, 266 faces stratégiques).<br><br>
                        Quelle zone, quel axe routier ou quelle période souhaitez-vous couvrir pour votre prochaine campagne ? La cartographie du dispositif s'actualise en direct à droite de votre écran.
                    </div>
                </div>
            </div>

            <!-- Barre de saisie inférieure -->
            <div class="p-3 md:p-4 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 z-10 shrink-0">
                <div class="max-w-4xl mx-auto space-y-2.5">
                    <!-- Suggestions rapides en 1 clic -->
                    <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
                        <span class="flex items-center gap-1 text-[#666] dark:text-slate-400 shrink-0 font-medium mr-1">
                            <i class="fa-solid fa-wand-magic-sparkles text-[#F4920D]"></i> Idées :
                        </span>
                        <button type="button" onclick="sendSuggestion('Campagne de 5 faces à Gembloux en Mars, Avril et Mai 2027')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                            🎯 5 faces Gembloux 3 mois
                        </button>
                        <button type="button" onclick="sendSuggestion('Magasin de bricolage près de Namur en mai 2026')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                            📍 Bricolage Namur
                        </button>
                        <button type="button" onclick="sendSuggestion('Concessionnaire auto sur la N4 ou E411')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                            🚗 Concession auto N4 / E411
                        </button>
                        <button type="button" onclick="sendSuggestion('Disponibilités panneaux à Wierde et Naninne')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                            📅 Wierde & Naninne
                        </button>
                    </div>

                    <!-- Formulaire de saisie -->
                    <form id="chatForm" class="flex items-end space-x-2.5">
                        <textarea id="messageInput" rows="1" placeholder="Posez votre question (ex: Campagne 5 faces autour de Gembloux)..." 
                            class="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#F4920D] focus:border-[#F4920D] text-slate-900 dark:text-white placeholder-slate-400 resize-none max-h-36 leading-normal" required></textarea>
                        <button type="submit" id="sendBtn" class="bg-gradient-to-r from-[#F4920D] to-[#FF5B34] hover:opacity-95 active:scale-95 text-white px-5 py-3 rounded-2xl font-semibold text-sm transition shadow-sm flex items-center justify-center shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
                            <i class="fa-solid fa-paper-plane text-sm"></i>
                        </button>
                    </form>
                </div>
            </div>
        </section>

        <!-- COLONNE DROITE : CARTOGRAPHIE & DISPOSITIF EN VIS-À-VIS -->
        <aside id="mapSection" class="hidden lg:flex flex-col w-full lg:w-[460px] xl:w-[520px] 2xl:w-[580px] h-full bg-white dark:bg-slate-900 shrink-0 shadow-lg border-l border-slate-200 dark:border-slate-800 transition-all duration-300">
            <!-- Header du volet cartographique -->
            <div class="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-900/90 backdrop-blur-sm flex items-center justify-between gap-2 shrink-0">
                <div class="flex items-center gap-2.5 min-w-0">
                    <span class="inline-flex items-center justify-center w-8 h-8 rounded-xl bg-[#F4920D]/10 text-[#F4920D] shrink-0 border border-[#F4920D]/20">
                        <i class="fa-solid fa-map-location-dot text-sm"></i>
                    </span>
                    <div class="min-w-0">
                        <h3 id="sideMapTitle" class="text-xs font-bold text-slate-900 dark:text-white truncate">Cartographie du Dispositif</h3>
                        <p id="sideMapSubtitle" class="text-[11px] text-slate-500 dark:text-slate-400 truncate">133 panneaux 8m² &middot; Réseau Wallonie</p>
                    </div>
                </div>

                <div class="flex items-center gap-1.5 shrink-0">
                    <!-- Toggle Interactif / Rendu HD -->
                    <div id="mapModeToggle" class="hidden inline-flex bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5 border border-slate-200 dark:border-slate-700 text-[11px]">
                        <button type="button" onclick="setMapDisplayMode('interactive')" id="btnModeInteractive" class="px-2 py-0.5 font-bold rounded-md bg-white dark:bg-slate-900 text-[#F4920D] shadow-2xs">Interactif</button>
                        <button type="button" onclick="setMapDisplayMode('render')" id="btnModeRender" class="px-2 py-0.5 font-semibold rounded-md text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">Rendu HD</button>
                    </div>

                    <!-- Bouton Télécharger Plan Média PDF Direct -->
                    <a id="sidePdfDownloadBtn" href="#" target="_blank" download class="btn-pdf hidden inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-[#F4920D] to-[#FF5B34] font-bold text-xs shadow-xs hover:brightness-110 active:scale-95 transition-all" style="color: #ffffff !important; text-decoration: none !important;">
                        <i class="fa-solid fa-file-pdf" style="color: #ffffff !important;"></i>
                        <span class="hidden sm:inline" style="color: #ffffff !important;">PDF</span>
                    </a>
                </div>
            </div>

            <!-- Barre d'onglets mois par mois pour les campagnes -->
            <div id="sideMonthTabsBar" class="hidden px-3.5 py-2 bg-slate-100/70 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700/80 flex items-center gap-1.5 overflow-x-auto no-scrollbar shrink-0">
                <!-- Généré dynamiquement en JS (Mars 2027, Avril 2027...) -->
            </div>

            <!-- Conteneur Carte (Leaflet interactif ou Rendu HD) -->
            <div class="relative w-full h-[320px] xl:h-[360px] 2xl:h-[400px] shrink-0 bg-slate-100 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800">
                <!-- Carte Leaflet interactive -->
                <div id="leafletMap" class="w-full h-full z-0"></div>

                <!-- Conteneur Rendu HD Statique -->
                <div id="renderMapContainer" class="hidden absolute inset-0 bg-slate-900 flex items-center justify-center overflow-hidden z-10">
                    <img id="renderMapImage" src="" alt="Plan Média HD" class="w-full h-full object-cover" />
                </div>

                <!-- Badge overlay dynamique sur la carte -->
                <div id="mapOverlayBadge" class="absolute bottom-2.5 left-2.5 z-[400] bg-black/75 backdrop-blur-md text-white text-[11px] px-2.5 py-1 rounded-lg font-medium shadow-sm flex items-center gap-1.5 border border-white/10">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span id="mapOverlayText">Réseau M Move Wallonie</span>
                </div>
            </div>

            <!-- Partie inférieure défilable : Métriques et Liste des Faces -->
            <div class="flex-1 overflow-y-auto p-3.5 space-y-3 bg-slate-50/50 dark:bg-slate-900/50">
                <!-- En-tête de la liste des faces (sobre et épuré) -->
                <div id="sideListHeader" class="hidden flex items-center justify-between px-1 pb-1">
                    <span id="sideListTitle" class="text-xs font-bold text-slate-700 dark:text-slate-300">Emplacements sélectionnés</span>
                    <span id="sideListCount" class="px-2.5 py-0.5 rounded-full bg-[#F4920D]/10 text-[#F4920D] font-bold text-[11px] border border-[#F4920D]/20">5 faces</span>
                </div>

                <!-- Liste des faces du mois actif -->
                <div id="sidePanelsList" class="space-y-2">
                    <!-- Populated dynamically with interactive face cards -->
                </div>

                <!-- Boîte d'aide pour demander une modification directe -->
                <div id="sideHelperBox" class="p-3 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 text-[11px] text-amber-900 dark:text-amber-200 flex items-start gap-2 shadow-2xs">
                    <i class="fa-solid fa-lightbulb text-[#F4920D] text-sm shrink-0 mt-0.5"></i>
                    <div>
                        <span class="font-bold">Ajuster le dispositif en direct :</span>
                        <p class="mt-0.5 text-amber-800/90 dark:text-amber-300/90">
                            Vous souhaitez modifier un emplacement ? Demandez-le simplement dans le chat à gauche (ex : <i>« Remplace le panneau 4 par un emplacement sur la N4 »</i> ou <i>« Élargis la sélection vers Eghezée »</i>).
                        </p>
                    </div>
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

            let out = "=== LOGS DE CONVERSATION M MOVE CONSEIL ===\n";
            out += `Date d'export : ${new Date().toLocaleString('fr-FR')}\n`;
            out += `Nombre total d'événements : ${detailedLogs.length}\n`;
            out += "==========================================\n\n";

            detailedLogs.forEach((item) => {
                if (item.role === 'user') {
                    out += `--------------------------------------------------\n`;
                    out += `[${item.time}] 👤 UTILISATEUR :\n`;
                    out += `${item.text}\n\n`;
                } else if (item.role === 'model') {
                    out += `[${item.time}] 🤖 ASSISTANT M MOVE :\n`;
                    if (item.timing && item.timing.elapsed_ms) {
                        out += `⏱️ Temps de réponse : ${(item.timing.elapsed_ms / 1000).toFixed(2)}s\n`;
                    }
                    if (item.extracted && item.extracted.intent) {
                        out += `🎯 Intention détectée : ${item.extracted.intent}\n`;
                        if (item.extracted.client_name) out += `🏢 Client : ${item.extracted.client_name}\n`;
                        if (item.extracted.target_periods && item.extracted.target_periods.length) out += `📅 Périodes : ${item.extracted.target_periods.join(', ')}\n`;
                        if (item.extracted.city) out += `📍 Ville : ${item.extracted.city}\n`;
                        if (item.extracted.n_faces) out += `🔢 Faces : ${item.extracted.n_faces}\n`;
                    }
                    if (item.panels_summary && item.panels_summary.length > 0) {
                        out += `🏷️ Remorques (${item.panels_count}) : ${item.panels_summary.join(', ')}\n`;
                    }
                    if (item.campaign_plan && item.campaign_plan.pdf_url) {
                        out += `📄 Plan Média PDF : ${item.campaign_plan.pdf_url}\n`;
                    }
                    out += `\n💬 TEXTE DE LA RÉPONSE :\n`;
                    out += `${item.text}\n\n`;
                } else if (item.role === 'error') {
                    out += `[${item.time}] ⚠️ ERREUR :\n${item.text}\n\n`;
                }
            });

            out += `==========================================\n`;
            out += `=== FIN DES LOGS ===\n`;
            return out;
        }

        async function openConversationLogsModal() {
            const modal = document.getElementById('logsModal');
            const ta = document.getElementById('logsTextarea');
            if (!modal || !ta) return;
            
            const logsText = generateLogsText();
            ta.value = logsText;
            modal.classList.remove('hidden');

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
            if (modal) modal.classList.add('hidden');
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
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg, history: history })
                });
                const data = await res.json();
                removeLoading(loadingId);

                // Mise à jour de la cartographie latérale en temps réel
                updateSideMap(data.campaign_plan, data.panels);

                appendMessage('model', data.text, data.panels, data.timing, data.campaign_plan);
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
                    <a href="${cp.pdf_url}" target="_blank" download
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

        function appendMessage(role, text, panels = [], timing = null, campaignPlan = null) {
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

            let campaignHtml = campaignPlan ? renderCampaignPlanWidget(campaignPlan) : '';

            let panelsHtml = '';
            if (!campaignPlan && panels && panels.length > 0) {
                panelsHtml = '<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">';
                panels.forEach(p => {
                    panelsHtml += renderPanelCard(p);
                });
                panelsHtml += '</div>';
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
                : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-5 max-w-3xl text-sm leading-relaxed shadow-sm text-[#666] dark:text-slate-100 markdown-body';

            div.innerHTML = `
                ${!isUser ? avatar : ''}
                <div class="${bubbleClass}">
                    ${formattedText}
                    ${campaignHtml}
                    ${panelsHtml}
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
            const mapSec = document.getElementById('mapSection');
            const chatBtn = document.getElementById('viewChatBtn');
            const mapBtn = document.getElementById('viewMapBtn');

            if (view === 'map') {
                chatSec.classList.add('hidden');
                mapSec.classList.remove('hidden');
                mapSec.classList.add('flex');
                mapBtn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg bg-white dark:bg-slate-900 text-[#F4920D] shadow-xs transition flex items-center gap-1';
                chatBtn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition';
                if (map) setTimeout(() => map.invalidateSize(), 200);
            } else {
                mapSec.classList.remove('flex');
                mapSec.classList.add('hidden');
                chatSec.classList.remove('hidden');
                chatBtn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg bg-white dark:bg-slate-900 text-[#F4920D] shadow-xs transition';
                mapBtn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition flex items-center gap-1';
            }
        }

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
            const sideTitle = document.getElementById('sideMapTitle');
            const sideSubtitle = document.getElementById('sideMapSubtitle');
            const pdfBtn = document.getElementById('sidePdfDownloadBtn');
            const modeToggle = document.getElementById('mapModeToggle');
            const tabsBar = document.getElementById('sideMonthTabsBar');
            const mobileBadge = document.getElementById('mobilePinBadge');

            if (campaignPlan && campaignPlan.months && campaignPlan.months.length > 0) {
                currentCampaignPlan = campaignPlan;
                activeMonthIdx = 0;

                sideTitle.innerText = "Plan Média & Cartographie";
                const totalFaces = campaignPlan.summary?.total_faces_deployed || (campaignPlan.months.length * 5);
                const clientPart = campaignPlan.client_name ? ` · Client : ${campaignPlan.client_name}` : '';
                sideSubtitle.innerText = `${campaignPlan.months.length} mois · ${totalFaces} faces déployées${clientPart}`;

                if (campaignPlan.pdf_url) {
                    pdfBtn.href = campaignPlan.pdf_url;
                    pdfBtn.classList.remove('hidden');
                } else {
                    pdfBtn.classList.add('hidden');
                }

                modeToggle.classList.remove('hidden');
                tabsBar.classList.remove('hidden');

                // Génération des onglets mensuels
                let tabsHtml = '';
                campaignPlan.months.forEach((m, idx) => {
                    const isAct = idx === 0;
                    tabsHtml += `
                        <button type="button" onclick="selectCampaignMonth(${idx})" id="sideMonthBtn_${idx}" 
                                class="side-month-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 ${isAct ? 'bg-[#F4920D] text-white shadow-xs' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200/80 dark:border-slate-700'}">
                            📅 ${m.period_human} (${m.panels?.length || 5} faces)
                        </button>
                    `;
                });
                tabsBar.innerHTML = tabsHtml;

                if (mobileBadge) {
                    mobileBadge.innerText = totalFaces;
                    mobileBadge.classList.remove('hidden');
                }

                selectCampaignMonth(0);
            } else if (panels && panels.length > 0) {
                currentCampaignPlan = null;
                sideTitle.innerText = "Sélection Recommandée";
                sideSubtitle.innerText = `${panels.length} panneaux qualifiés en Wallonie`;
                pdfBtn.classList.add('hidden');
                modeToggle.classList.add('hidden');
                tabsBar.classList.add('hidden');

                if (mobileBadge) {
                    mobileBadge.innerText = panels.length;
                    mobileBadge.classList.remove('hidden');
                }

                displayPanelsOnSideMap(panels, null, null);
            }
        }

        function selectCampaignMonth(idx) {
            if (!currentCampaignPlan || !currentCampaignPlan.months[idx]) return;
            activeMonthIdx = idx;

            // Mise à jour de l'apparence des onglets
            const btns = document.querySelectorAll('.side-month-btn');
            btns.forEach((b, i) => {
                if (i === idx) {
                    b.className = 'side-month-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 bg-[#F4920D] text-white shadow-xs';
                } else {
                    b.className = 'side-month-btn px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200/80 dark:border-slate-700';
                }
            });

            const m = currentCampaignPlan.months[idx];
            const renderImg = document.getElementById('renderMapImage');
            if (renderImg && m.map_url) {
                renderImg.src = m.map_url;
            }

            displayPanelsOnSideMap(m.panels, m.stats, m.period_human);
        }

        function displayPanelsOnSideMap(panels, stats = null, periodLabel = null) {
            if (!recommendationLayer || !map) return;
            recommendationLayer.clearLayers();
            markersMap = {};

            const listHeader = document.getElementById('sideListHeader');
            const listTitle = document.getElementById('sideListTitle');
            const listCount = document.getElementById('sideListCount');
            const overlayText = document.getElementById('mapOverlayText');
            const listEl = document.getElementById('sidePanelsList');

            if (!panels || panels.length === 0) {
                if (listHeader) listHeader.classList.add('hidden');
                listEl.innerHTML = '<p class="text-xs text-slate-400 p-2 text-center">Aucun panneau sélectionné.</p>';
                return;
            }

            if (listHeader) listHeader.classList.remove('hidden');
            const count = panels.length;
            if (listTitle) listTitle.innerText = periodLabel ? `Emplacements · ${periodLabel}` : `Emplacements sélectionnés`;
            if (listCount) listCount.innerText = `${count} faces`;

            if (periodLabel) {
                overlayText.innerText = `${count} faces actives · ${periodLabel}`;
            } else {
                overlayText.innerText = `${count} faces sélectionnées`;
            }

            const bounds = [];
            let listCardsHtml = '';

            panels.forEach((p, idx) => {
                const num = idx + 1;
                const panelId = String(p.id || p.remorque || '').replace('.0', '');
                const lat = parseFloat(p.lat);
                const lng = parseFloat(p.lng);
                const photoUrl = p.photo || p.image_url || `https://remorquepublicitaire.be/wp-content/uploads/2021/07/${panelId}in.jpg`;
                const axe = p.axe_routier || p.code_route || '';
                const dir = p.direction ? `· Vers ${p.direction}` : '';
                const distKm = (p.distance_km !== null && p.distance_km !== undefined && p.distance_km > 0) ? `📍 ${p.distance_km} km` : '';

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
                            <div style="color:#64748b; font-size:11px; font-weight:500;">${axe} ${dir}</div>
                            ${distKm ? `<div style="color:#059669; font-size:11px; font-weight:600; margin-top:3px;">${distKm}</div>` : ''}
                            <img src="${photoUrl}" style="width:100%; border-radius:8px; margin-top:6px; max-height:95px; object-fit:cover;" onerror="this.remove()" />
                            <div style="margin-top:6px; text-align:right;">
                                <a href="${p.lien || '#'}" target="_blank" style="color:#F4920D; font-weight:700; text-decoration:none; font-size:11px;">Fiche remorque &rarr;</a>
                            </div>
                        </div>
                    `);
                    recommendationLayer.addLayer(marker);
                    markersMap[panelId] = marker;
                }

                // Carte compacte dans la liste latérale
                listCardsHtml += `
                    <div id="sideCard_${panelId}" onclick="focusPanelOnMap('${panelId}')" 
                         class="cursor-pointer p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 hover:border-[#F4920D] dark:hover:border-[#F4920D] hover:shadow-sm transition-all text-xs flex items-center justify-between gap-2.5 group">
                        <div class="flex items-center gap-2.5 min-w-0">
                            <span class="w-6 h-6 rounded-full bg-[#F4920D] group-hover:bg-[#FF5B34] text-white font-extrabold flex items-center justify-center shrink-0 text-xs shadow-2xs transition-colors">
                                ${num}
                            </span>
                            <div class="min-w-0">
                                <div class="font-bold text-slate-900 dark:text-white truncate">
                                    #${panelId} ${p.ville || ''}
                                </div>
                                <div class="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                                    ${axe} ${dir}
                                </div>
                            </div>
                        </div>
                        <div class="text-right shrink-0 flex flex-col items-end">
                            ${distKm ? `<span class="text-[11px] font-semibold text-slate-500 dark:text-slate-400">${distKm}</span>` : ''}
                            <span class="text-[10px] text-[#F4920D] font-semibold mt-0.5 group-hover:underline">Localiser &rarr;</span>
                        </div>
                    </div>
                `;
            });

            listEl.innerHTML = listCardsHtml;

            // Recadrage dynamique de la carte
            if (bounds.length > 0) {
                setTimeout(() => {
                    map.invalidateSize();
                    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
                }, 100);
            }
        }

        function focusPanelOnMap(panelId) {
            const marker = markersMap[panelId];
            if (marker && map) {
                map.flyTo(marker.getLatLng(), 14, { duration: 0.8 });
                marker.openPopup();
            }

            // Highlight side card
            document.querySelectorAll('[id^="sideCard_"]').forEach(c => {
                c.classList.remove('ring-2', 'ring-[#F4920D]', 'bg-amber-50/50', 'dark:bg-amber-950/20');
            });
            const card = document.getElementById(`sideCard_${panelId}`);
            if (card) {
                card.classList.add('ring-2', 'ring-[#F4920D]', 'bg-amber-50/50', 'dark:bg-amber-950/20');
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        window.addEventListener('DOMContentLoaded', initLeafletMap);
    </script>

    <!-- TOAST NOTIFICATION LOGS -->
    <div id="logsToast" class="fixed bottom-5 right-5 z-50 transform translate-y-10 opacity-0 pointer-events-none transition-all duration-300 bg-slate-900/95 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-lg border border-slate-700 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-emerald-400"></i>
        <span id="logsToastMsg">Logs copiés dans le presse-papier !</span>
    </div>

    <!-- MODAL LOGS DE CONVERSATION (Discret) -->
    <div id="logsModal" onclick="if(event.target === this) closeConversationLogsModal()" class="fixed inset-0 z-50 hidden flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
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
</body>
</html>"""
            self.wfile.write(html_content.encode("utf-8"))
            return

        self._set_headers(404)
        self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        if self.path == "/api/chat":
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

                res = coordinator.process_message(user_msg, conversation_history=history)
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
