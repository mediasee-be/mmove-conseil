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
            res = {
                "status": "ok",
                "trailers_count": len(coordinator.engine.trailers),
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
    <style>
        body {
            color: #666666;
        }
        .dark body {
            color: #cbd5e1;
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
                <span class="text-xs text-[#666] dark:text-slate-400 font-medium hidden sm:inline">132 Remorques Wallonie</span>
            </div>
        </div>

        <div class="flex items-center space-x-2">
            <!-- Sync Live Badge -->
            <div id="statsBadge" class="hidden sm:flex text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 py-1.5 rounded-xl text-[#666] dark:text-slate-300 items-center space-x-2 shadow-inner">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>132 remorques actives</span>
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
        </div>
    </header>

    <!-- CHAT MESSAGES AREA -->
    <div id="chatMessages" class="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 max-w-5xl mx-auto w-full">
        <!-- Message initial de bienvenue -->
        <div class="flex items-start space-x-3">
            <div class="w-9 h-9 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xs shrink-0 mt-0.5">
                <img src="/static/bot-avatar.png" alt="Conseiller M Move" class="w-full h-full object-cover object-top">
            </div>
            <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-5 max-w-3xl text-sm leading-relaxed shadow-sm text-[#666] dark:text-slate-200">
                <p class="font-bold text-[#F4920D] mb-2 flex items-center gap-1.5">
                    <i class="fa-solid fa-sparkles text-[#FF5B34]"></i> Conseiller Commercial M Move
                </p>
                Bonjour ! Je suis votre conseiller expert pour le réseau de remorques publicitaires 8m² M Move en Wallonie.<br><br>
                Quelle zone, quel axe routier ou quelle période souhaitez-vous couvrir pour votre prochaine campagne ?
            </div>
        </div>
    </div>

    <!-- BOTTOM INPUT BAR -->
    <div class="p-3 md:p-4 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 z-10 shrink-0">
        <div class="max-w-5xl mx-auto space-y-2.5">
            <!-- Suggestions rapides en 1 clic -->
            <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
                <span class="flex items-center gap-1 text-[#666] dark:text-slate-400 shrink-0 font-medium mr-1">
                    <i class="fa-solid fa-wand-magic-sparkles text-[#F4920D]"></i> Idées :
                </span>
                <button type="button" onclick="sendSuggestion('Magasin de bricolage près de Namur en mai 2026')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                    📍 Bricolage près de Namur
                </button>
                <button type="button" onclick="sendSuggestion('Concessionnaire auto sur la N4 ou E411')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                    🚗 Concession auto sur N4 / E411
                </button>
                <button type="button" onclick="sendSuggestion('Disponibilités remorques à Wierde et Naninne')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                    📅 Disponibilités Wierde & Naninne
                </button>
                <button type="button" onclick="sendSuggestion('Quand est libre le panneau #114 ?')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                    🔍 Dispo panneau #114
                </button>
                <button type="button" onclick="sendSuggestion('5 règles d\'or pour un visuel percutant 8m²')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-[#F4920D]/10 dark:bg-slate-800 dark:hover:bg-[#F4920D]/10 text-[#666] dark:text-slate-200 hover:text-[#F4920D] dark:hover:text-[#F4920D] hover:border-[#F4920D]/40 transition border border-slate-200 dark:border-slate-700">
                    💡 5 règles d'or visuel 8m²
                </button>
            </div>

            <!-- Formulaire de saisie -->
            <form id="chatForm" class="flex items-end space-x-2.5">
                <textarea id="messageInput" rows="1" placeholder="Posez votre question (ex: Remorques disponibles à Wavre en septembre)..." 
                    class="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#F4920D] focus:border-[#F4920D] text-slate-900 dark:text-white placeholder-slate-400 resize-none max-h-36 leading-normal" required></textarea>
                <button type="submit" id="sendBtn" class="bg-gradient-to-r from-[#F4920D] to-[#FF5B34] hover:opacity-95 active:scale-95 text-white px-5 py-3 rounded-2xl font-semibold text-sm transition shadow-sm flex items-center justify-center shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
                    <i class="fa-solid fa-paper-plane text-sm"></i>
                </button>
            </form>
        </div>
    </div>

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
                const s = data.synchronisation;
                document.getElementById('statsBadge').innerHTML = `
                    <span class="flex items-center space-x-1.5">
                        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        <span class="font-bold text-slate-900 dark:text-white">${data.trailers_count}</span>
                        <span class="text-slate-500 dark:text-slate-400">remorques</span>
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
                document.getElementById('statsBadge').innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>132 remorques &middot; Synchronisation active</span>';
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

                appendMessage('model', data.text, data.panels, data.timing);
                history.push({ role: 'model', text: data.text });
            } catch (err) {
                removeLoading(loadingId);
                appendMessage('model', "Une erreur réseau est survenue. Veuillez réessayer dans quelques instants.");
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

        function appendMessage(role, text, panels = [], timing = null) {
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

            let panelsHtml = '';
            if (panels && panels.length > 0) {
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
    </script>
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
