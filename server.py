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
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M Move - Conseil Multi-Agents</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-900 text-gray-100 flex flex-col h-screen font-sans">
    <header class="bg-gray-800 border-b border-gray-700 p-4 flex items-center justify-between shadow-md">
        <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center font-bold text-lg text-white">M</div>
            <div>
                <h1 class="text-xl font-bold tracking-wide">M Move - Conseil en Affichage 8m²</h1>
                <p class="text-xs text-blue-400">Architecture Multi-Agents Découplée &middot; Latence < 2s &middot; 132 Remorques Wallonie</p>
            </div>
        </div>
        <div class="flex items-center space-x-2">
            <div id="statsBadge" class="text-xs bg-gray-800 border border-gray-700 px-3 py-1.5 rounded-xl text-gray-300 flex items-center space-x-3">
                <span>Chargement du statut de synchronisation...</span>
            </div>
            <button onclick="triggerSync('all')" title="Forcer la vérification immédiate" class="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 px-2.5 py-1.5 rounded-xl text-blue-400 hover:text-white transition flex items-center space-x-1">
                <i class="fa-solid fa-arrows-rotate"></i>
                <span>Sync</span>
            </button>
        </div>
    </header>

    <div id="chatMessages" class="flex-1 overflow-y-auto p-4 space-y-4 max-w-5xl mx-auto w-full">
        <div class="flex items-start space-x-3">
            <div class="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white shrink-0">IA</div>
            <div class="bg-gray-800 border border-gray-700 rounded-2xl p-4 max-w-2xl text-sm leading-relaxed shadow-sm">
                <p class="font-semibold text-blue-400 mb-1">Agent Commercial M Move :</p>
                Bonjour ! Je suis votre conseiller expert pour les remorques d'affichage publicitaire 8m² M Move en Wallonie.<br><br>
                Quelle zone, quel axe routier ou quelle période souhaitez-vous couvrir pour votre prochaine campagne ?
            </div>
        </div>
    </div>

    <div class="p-4 bg-gray-800 border-t border-gray-700">
        <form id="chatForm" class="max-w-5xl mx-auto flex space-x-3">
            <input id="messageInput" type="text" placeholder="Ex: Je cherche 3 panneaux pour un magasin de bricolage près de Namur en mai 2026..." 
                class="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 text-white placeholder-gray-500" required>
            <button type="submit" id="sendBtn" class="bg-blue-600 hover:bg-blue-500 px-6 py-3 rounded-xl font-semibold text-sm transition flex items-center space-x-2">
                <span>Envoyer</span>
                <i class="fa-solid fa-paper-plane text-xs"></i>
            </button>
        </form>
    </div>

    <script>
        async function loadSyncStatus() {
            try {
                const r = await fetch('/api/health');
                const data = await r.json();
                const s = data.synchronisation;
                document.getElementById('statsBadge').innerHTML = `
                    <span class="flex items-center space-x-1">
                        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        <span class="font-bold text-white">${data.trailers_count}</span>
                        <span class="text-gray-400">remorques</span>
                    </span>
                    <span class="text-gray-600">|</span>
                    <span title="Dernière: ${s.dispo.derniere_verification}">
                        <i class="fa-regular fa-clock text-blue-400"></i> Dispo : <b>1x/h</b> <span class="text-gray-400">(${s.dispo.prochaine_verification})</span>
                    </span>
                    <span class="text-gray-600">|</span>
                    <span title="Dernière: ${s.panneaux.derniere_verification}">
                        <i class="fa-regular fa-calendar text-purple-400"></i> Panneaux : <b>1x/sem</b> <span class="text-gray-400">(${s.panneaux.prochaine_verification})</span>
                    </span>
                `;
            } catch (e) {
                document.getElementById('statsBadge').innerText = "132 remorques &middot; Synchronisation active";
            }
        }
        loadSyncStatus();
        setInterval(loadSyncStatus, 30000);

        async function triggerSync(type) {
            const badge = document.getElementById('statsBadge');
            badge.innerHTML = '<span class="text-blue-400 animate-pulse"><i class="fa-solid fa-arrows-rotate fa-spin mr-1"></i> Synchronisation en cours...</span>';
            try {
                await fetch('/api/sync/trigger', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: type })
                });
                await loadSyncStatus();
            } catch (err) {
                alert("Erreur lors de la synchronisation");
                loadSyncStatus();
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const chatForm = document.getElementById('chatForm');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        let history = [];

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = messageInput.value.trim();
            if (!msg) return;

            // Message utilisateur
            messageInput.value = '';
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
                appendMessage('model', "Une erreur réseau est survenue. Veuillez vérifier la connexion.");
            } finally {
                sendBtn.disabled = false;
            }
        });

        function appendMessage(role, text, panels = [], timing = null) {
            const div = document.createElement('div');
            div.className = `flex items-start space-x-3 ${role === 'user' ? 'justify-end' : ''}`;

            const isUser = role === 'user';
            const avatar = isUser ? '' : `<div class="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white shrink-0">IA</div>`;
            const bg = isUser ? 'bg-blue-700 text-white' : 'bg-gray-800 border border-gray-700 text-gray-200';

            let panelsHtml = '';
            if (panels && panels.length > 0) {
                panelsHtml = '<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">';
                panels.forEach(p => {
                    const directBadge = p.is_direct_match ? '<span class="text-[10px] bg-emerald-900/80 text-emerald-300 font-bold px-2 py-0.5 rounded-full border border-emerald-600">🎯 Direct</span>' : '';
                    const distBadge = (p.distance_km !== null && p.distance_km !== undefined) ? `<span class="text-[10px] bg-gray-800 text-gray-300 px-2 py-0.5 rounded-full">📍 ${p.distance_km} km</span>` : '';
                    panelsHtml += `
                    <div class="bg-gray-900 border ${p.is_direct_match ? 'border-emerald-500' : 'border-gray-700'} rounded-xl p-3 flex flex-col justify-between hover:border-blue-500 transition">
                        <div>
                            <div class="flex justify-between items-start mb-1 gap-1">
                                <span class="font-bold text-blue-400">#${p.id || p.remorque} - ${p.ville}</span>
                                <div class="flex items-center space-x-1">
                                    ${directBadge}
                                    ${distBadge}
                                    <span class="text-xs bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded-full">${p.frequentation ? p.frequentation.toLocaleString() + ' véh/j' : '8m²'}</span>
                                </div>
                            </div>
                            <p class="text-xs text-gray-400 mb-2 font-medium text-white">${p.localisation} &middot; <span class="text-gray-400">Direction: ${p.direction}</span></p>
                            <p class="text-xs text-gray-300 italic mb-2">${p.contexte_visibilite || ''}</p>
                        </div>
                        <div class="flex justify-between items-center pt-2 border-t border-gray-800 text-xs">
                            <span class="text-emerald-400 font-medium">📅 ${p.prochaine_dispo || 'Dispo'}</span>
                            <a href="${p.lien}" target="_blank" class="text-blue-400 hover:underline">Fiche ↗️</a>
                        </div>
                    </div>`;
                });
                panelsHtml += '</div>';
            }

            let timingHtml = '';
            if (timing) {
                timingHtml = `<div class="mt-2 text-[11px] text-gray-500 flex space-x-3 border-t border-gray-700/60 pt-1">
                    <span>⚡ Total: ${timing.total_ms}ms</span>
                    <span>NLU: ${timing.extraction_ms}ms</span>
                    <span>Géo/Dispo: ${timing.engine_ms}ms</span>
                    <span>Synthèse: ${timing.synthesis_ms}ms</span>
                </div>`;
            }

            div.innerHTML = `
                ${!isUser ? avatar : ''}
                <div class="${bg} rounded-2xl p-4 max-w-2xl text-sm leading-relaxed shadow-sm whitespace-pre-line">
                    ${text}
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
            div.className = 'flex items-center space-x-3 text-gray-400 text-sm';
            div.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-blue-600/50 flex items-center justify-center text-xs text-white">...</div>
                <div class="animate-pulse">Analyse de la demande & vérification des 132 remorques...</div>
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
