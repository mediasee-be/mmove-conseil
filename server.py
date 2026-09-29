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

        # Interface Web interactive locale
        if self.path == "/" or self.path == "/index.html":
            self._set_headers(200, "text/html; charset=utf-8")
            html_content = """<!DOCTYPE html>
<html lang="fr" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M Move - Conseil en Affichage 8m²</title>
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
                            orange: '#F4920D',
                            cyan: '#2EA3F2',
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
        .markdown-body {
            line-height: 1.6;
            font-size: 0.925rem;
        }
        .markdown-body h1, .markdown-body h2, .markdown-body h3 {
            font-weight: 700;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            color: #1e3a8a;
        }
        .dark .markdown-body h1, .dark .markdown-body h2, .dark .markdown-body h3 {
            color: #93c5fd;
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
        }
        .markdown-body p {
            margin-bottom: 0.75rem;
        }
        .markdown-body p:last-child {
            margin-bottom: 0;
        }
        .markdown-body a {
            color: #2563eb;
            text-decoration: underline;
            font-weight: 600;
        }
        .dark .markdown-body a {
            color: #60a5fa;
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
<body class="bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 flex flex-col h-screen font-sans transition-colors duration-200">
    <!-- HEADER -->
    <header class="bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 px-4 py-3 flex items-center justify-between shadow-sm z-10 shrink-0">
        <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#F4920D] to-[#2EA3F2] flex items-center justify-center shadow text-white font-extrabold text-xl shrink-0">
                M
            </div>
            <div>
                <h1 class="text-base md:text-lg font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
                    <span>M Move</span>
                    <span class="text-xs px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-semibold border border-blue-200 dark:border-blue-800">Conseil 8m²</span>
                </h1>
                <p class="text-xs text-slate-500 dark:text-slate-400">132 Remorques en Wallonie &middot; Disponibilités &amp; Visibilité en direct</p>
            </div>
        </div>

        <div class="flex items-center space-x-2">
            <!-- Sync Live Badge -->
            <div id="statsBadge" class="hidden sm:flex text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 py-1.5 rounded-xl text-slate-600 dark:text-slate-300 items-center space-x-2 shadow-inner">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>132 remorques actives</span>
            </div>

            <!-- Sync Button -->
            <button onclick="triggerSync('all')" title="Forcer la vérification immédiate des disponibilités" class="text-xs bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 rounded-xl text-blue-600 dark:text-blue-400 transition flex items-center space-x-1 font-medium">
                <i class="fa-solid fa-arrows-rotate" id="syncIcon"></i>
                <span class="hidden md:inline">Sync</span>
            </button>

            <!-- Dark / Light Mode Toggle -->
            <button onclick="toggleDarkMode()" title="Changer le thème (Clair / Sombre)" class="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 transition flex items-center justify-center">
                <i id="themeIcon" class="fa-solid fa-moon text-slate-600 dark:text-amber-400 text-sm"></i>
            </button>
        </div>
    </header>

    <!-- CHAT MESSAGES AREA -->
    <div id="chatMessages" class="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 max-w-5xl mx-auto w-full">
        <!-- Message initial de bienvenue -->
        <div class="flex items-start space-x-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F4920D] to-[#2EA3F2] flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm">
                IA
            </div>
            <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-5 max-w-3xl text-sm leading-relaxed shadow-sm text-slate-800 dark:text-slate-100">
                <p class="font-bold text-blue-600 dark:text-blue-400 mb-2 flex items-center gap-1.5">
                    <i class="fa-solid fa-sparkles text-amber-500"></i> Conseiller Commercial M Move
                </p>
                Bonjour ! Je suis votre conseiller expert pour le réseau de remorques publicitaires 8m² M Move en Wallonie.<br><br>
                Quelle zone, quel axe routier ou quelle période souhaitez-vous couvrir pour votre prochaine campagne ?
            </div>
        </div>
    </div>

    <!-- BOTTOM INPUT BAR -->
    <div class="p-3 md:p-4 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 z-10 shrink-0">
        <div class="max-w-5xl mx-auto space-y-2.5">
            <!-- Suggestions rapides en 1 clic (comme AI Studio) -->
            <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
                <span class="flex items-center gap-1 text-slate-400 shrink-0 font-medium mr-1">
                    <i class="fa-solid fa-wand-magic-sparkles text-amber-500"></i> Idées :
                </span>
                <button type="button" onclick="sendSuggestion('Magasin de bricolage près de Namur en mai 2026')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition border border-slate-200 dark:border-slate-700">
                    📍 Bricolage près de Namur
                </button>
                <button type="button" onclick="sendSuggestion('Concessionnaire auto sur la N4 ou E411')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition border border-slate-200 dark:border-slate-700">
                    🚗 Concession auto sur N4 / E411
                </button>
                <button type="button" onclick="sendSuggestion('Disponibilités remorques à Wierde et Naninne')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition border border-slate-200 dark:border-slate-700">
                    📅 Disponibilités Wierde & Naninne
                </button>
                <button type="button" onclick="sendSuggestion('Quand est libre le panneau #114 ?')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition border border-slate-200 dark:border-slate-700">
                    🔍 Dispo panneau #114
                </button>
                <button type="button" onclick="sendSuggestion('5 règles d\'or pour un visuel percutant 8m²')" class="shrink-0 px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition border border-slate-200 dark:border-slate-700">
                    💡 5 règles d'or visuel 8m²
                </button>
            </div>

            <!-- Formulaire de saisie -->
            <form id="chatForm" class="flex items-end space-x-2.5">
                <textarea id="messageInput" rows="1" placeholder="Posez votre question (ex: Remorques disponibles à Wavre en septembre)..." 
                    class="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-white placeholder-slate-400 resize-none max-h-36 leading-normal" required></textarea>
                <button type="submit" id="sendBtn" class="bg-blue-600 hover:bg-blue-500 active:scale-95 text-white px-5 py-3 rounded-2xl font-semibold text-sm transition shadow-sm flex items-center justify-center shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
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
            const faceColor = (p.face === 'IN') 
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
                : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 border-indigo-300 dark:border-indigo-800';

            return `
            <div class="bg-white dark:bg-slate-800/95 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700/80 overflow-hidden hover:shadow-md hover:border-blue-500 transition-all text-sm flex flex-col group">
                <!-- 1. Photo de la remorque 8m² avec badges -->
                <div class="relative w-full h-36 bg-slate-900 overflow-hidden">
                    <img src="${photoUrl}" 
                         alt="Remorque #${panelId} - ${p.ville || ''}" 
                         class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                         onerror="this.onerror=null; this.src='https://remorquepublicitaire.be/wp-content/uploads/2021/07/logo-mmove.png'; this.classList.add('object-contain', 'p-4');" />
                    
                    ${isDirect ? `
                    <div class="absolute top-2 left-2 bg-emerald-600/95 backdrop-blur-sm text-white text-[11px] font-bold px-2.5 py-0.5 rounded-md shadow-sm border border-emerald-400/40 flex items-center space-x-1">
                        <span>🎯 Implantation directe</span>
                    </div>` : ''}

                    <div class="absolute top-2 right-2 bg-black/75 backdrop-blur-sm text-white text-[11px] font-semibold px-2 py-0.5 rounded-full border border-white/20">
                        8m² Recto/Verso
                    </div>

                    ${distText ? `
                    <div class="absolute bottom-2 left-2 bg-blue-600/90 backdrop-blur-sm text-white text-[11px] font-semibold px-2 py-0.5 rounded-md shadow-sm">
                        ${distText}
                    </div>` : ''}
                </div>

                <!-- 2. Corps de la carte -->
                <div class="p-4 space-y-3 flex-1 flex flex-col justify-between">
                    <div>
                        <!-- En-tête : Titre & Badge Face -->
                        <div class="flex justify-between items-start gap-2 mb-1.5">
                            <div>
                                <a href="${linkUrl}" target="_blank" rel="noopener noreferrer" 
                                   class="font-bold text-base text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1.5 group-hover:text-blue-700 dark:group-hover:text-blue-300">
                                    <span>#${panelId} - ${p.ville || 'Wallonie'}</span>
                                    <i class="fa-solid fa-arrow-up-right-from-square text-xs text-blue-400"></i>
                                </a>
                                ${p.localisation ? `<p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-medium">${p.localisation}</p>` : ''}
                            </div>
                            <span class="px-2 py-0.5 rounded-full text-xs font-bold shrink-0 border ${faceColor}">
                                Face ${p.face || 'IN/OUT'}
                            </span>
                        </div>

                        <!-- Axe routier & Direction -->
                        <div class="space-y-1 text-slate-600 dark:text-slate-300 text-xs mt-2">
                            ${p.axe_routier ? `
                            <div class="flex items-center space-x-2">
                                <i class="fa-solid fa-road text-slate-400 dark:text-slate-500 w-3.5 text-center"></i>
                                <span class="font-semibold text-slate-700 dark:text-slate-200">${p.axe_routier}</span>
                            </div>` : ''}
                            ${p.direction ? `
                            <div class="flex items-center space-x-2">
                                <i class="fa-solid fa-compass text-slate-400 dark:text-slate-500 w-3.5 text-center"></i>
                                <span>Direction <span class="font-medium text-slate-700 dark:text-slate-200">${p.direction}</span></span>
                            </div>` : ''}
                        </div>

                        <!-- Fréquentation & OTS -->
                        ${(freqFormatted || otsFormatted) ? `
                        <div class="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-700 flex items-center gap-3 text-xs">
                            ${freqFormatted ? `
                            <span class="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 font-semibold" title="Fréquentation moyenne">
                                <i class="fa-solid fa-car text-blue-500"></i>
                                ${freqFormatted} véh./j
                            </span>` : ''}
                            ${otsFormatted ? `
                            <span class="flex items-center gap-1.5 text-purple-600 dark:text-purple-400 font-semibold" title="Opportunité de visibilité mensuelle">
                                <i class="fa-solid fa-eye text-purple-500"></i>
                                ${otsFormatted} OTS/mois
                            </span>` : ''}
                        </div>` : ''}

                        <!-- Contexte de visibilité -->
                        ${p.contexte_visibilite ? `
                        <div class="mt-2 bg-slate-50 dark:bg-slate-700/50 p-2.5 rounded-xl border border-slate-200/70 dark:border-slate-600/50 text-[11px] text-slate-600 dark:text-slate-300 italic">
                            👁️ ${p.contexte_visibilite}
                        </div>` : ''}
                    </div>

                    <!-- Footer Disponibilité & Bouton Réserver -->
                    <div class="pt-2">
                        ${p.prochaine_dispo ? `
                        <div class="bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 text-xs px-3 py-2 rounded-xl flex items-center justify-between font-medium">
                            <span class="flex items-center space-x-1.5">
                                <i class="fa-regular fa-calendar-check text-emerald-600 dark:text-emerald-400 text-sm"></i>
                                <span>Dispo dès : <b>${p.prochaine_dispo}</b></span>
                            </span>
                            <a href="${linkUrl}" target="_blank" rel="noopener noreferrer" 
                               class="text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 hover:text-emerald-900 dark:hover:text-white underline">
                                Réserver ↗
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
                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F4920D] to-[#2EA3F2] flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm mt-1">
                    IA
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
                <div class="mt-3 text-[11px] text-slate-400 dark:text-slate-500 flex flex-wrap gap-x-3 gap-y-1 border-t border-slate-200/80 dark:border-slate-700/80 pt-2 font-mono">
                    <span>⚡ Réponse: ${timing.total_ms}ms</span>
                    <span>&middot; NLU: ${timing.extraction_ms}ms</span>
                    <span>&middot; Géo/Dispo: ${timing.engine_ms}ms</span>
                    <span>&middot; Synthèse: ${timing.synthesis_ms}ms</span>
                </div>`;
            }

            const bubbleClass = isUser 
                ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl text-sm shadow-sm' 
                : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-5 max-w-3xl text-sm leading-relaxed shadow-sm text-slate-800 dark:text-slate-100 markdown-body';

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
                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F4920D] to-[#2EA3F2] flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm opacity-70">
                    <i class="fa-solid fa-spinner fa-spin"></i>
                </div>
                <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 text-sm text-slate-500 dark:text-slate-400 flex items-center space-x-3 shadow-sm">
                    <span class="animate-pulse flex items-center gap-2">
                        <i class="fa-solid fa-magnifying-glass-location text-blue-500"></i>
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
