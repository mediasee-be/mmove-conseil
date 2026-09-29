"""
M Move Synchronization Manager (Dual Cadence)
Gère les deux rythmes de synchronisation demandés :
1. Vérification de la liste des panneaux : 1x par semaine (7 jours)
2. Vérification des disponibilités : 1x par heure (3600 secondes)

Fonctionne en tâche de fond non-bloquante (daemon thread) et met à jour
la mémoire vive du moteur sans interrompre les requêtes utilisateurs.
"""

import os
import glob
import json
import time
import shutil
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

SYNC_STATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../data/sync_state.json")
)
DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../data/mmove_db.json")
)
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")

DISPO_INTERVAL_SECONDS = 3600        # 1 heure
PANELS_INTERVAL_SECONDS = 7 * 86400  # 1 semaine (7 jours)

class SyncManager:
    """Gestionnaire de synchronisation à double cadence (Hebdomadaire & Horaire)."""

    def __init__(self, engine_tools=None):
        self.engine_tools = engine_tools
        self.state = self._load_state()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _load_state(self) -> Dict[str, Any]:
        """Charge l'état des dernières synchronisations."""
        now = time.time()
        default_state = {
            "last_panels_check": now,
            "last_dispo_check": now,
            "last_panels_updated": None,
            "last_dispo_updated": None,
            "panels_interval_sec": PANELS_INTERVAL_SECONDS,
            "dispo_interval_sec": DISPO_INTERVAL_SECONDS,
            "status": "idle",
            "history": []
        }
        if os.path.exists(SYNC_STATE_PATH):
            try:
                with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # S'assurer que les clés minimales existent
                    for k, v in default_state.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception as e:
                print(f"[SyncManager] Erreur lecture état: {e}")
        return default_state

    def _save_state(self):
        """Persiste l'état de synchronisation."""
        os.makedirs(os.path.dirname(SYNC_STATE_PATH), exist_ok=True)
        try:
            with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SyncManager] Erreur sauvegarde état: {e}")

    def log_event(self, action: str, details: str, updated: bool = False):
        """Enregistre un événement dans l'historique."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "updated": updated
        }
        self.state["history"].append(event)
        if len(self.state["history"]) > 50:
            self.state["history"] = self.state["history"][-50:]
        self._save_state()

    def check_disponibilites(self, force: bool = False) -> Dict[str, Any]:
        """
        Cadence Horaire (1x par heure) :
        Vérifie et met à jour les réservations et statuts de disponibilité.
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.state.get("last_dispo_check", 0)

            if not force and elapsed < DISPO_INTERVAL_SECONDS:
                remaining = int(DISPO_INTERVAL_SECONDS - elapsed)
                return {
                    "status": "skipped",
                    "reason": f"Vérification horaire déjà effectuée. Prochaine dans {remaining}s",
                    "last_check": self.state.get("last_dispo_check")
                }

            self.state["status"] = "checking_dispo"
            updated = False
            details = []

            # 1. Vérifier si de nouveaux plannings Excel existent dans ~/Downloads ou data/
            newest_2026 = self._find_newest_file("Mmove*2026*.xlsx")
            newest_2027 = self._find_newest_file("Mmove*2027*.xlsx")

            local_2026 = os.path.join(DATA_DIR, "Mmove_2026.xlsx")
            local_2027 = os.path.join(DATA_DIR, "Mmove_2027.xlsx")

            if newest_2026 and newest_2026 != local_2026:
                if os.path.getmtime(newest_2026) > os.path.getmtime(local_2026):
                    shutil.copy2(newest_2026, local_2026)
                    updated = True
                    details.append(f"Planning 2026 actualisé depuis {os.path.basename(newest_2026)}")

            if newest_2027 and newest_2027 != local_2027:
                if os.path.getmtime(newest_2027) > os.path.getmtime(local_2027):
                    shutil.copy2(newest_2027, local_2027)
                    updated = True
                    details.append(f"Planning 2027 actualisé depuis {os.path.basename(newest_2027)}")

            # 2. Si un fichier a été actualisé ou si rebuild forcé, réexécuter le build_database
            if updated or force:
                from ..build_database import build_unified_database
                build_unified_database()
                if self.engine_tools:
                    self.engine_tools.reload()
                self.state["last_dispo_updated"] = now
                msg = "Disponibilités actualisées : " + ", ".join(details or ["rebuild complet"])
            else:
                msg = "Disponibilités vérifiées : aucune modification détectée"

            self.state["last_dispo_check"] = now
            self.state["status"] = "idle"
            self.log_event("VERIF_DISPO_HORAIRE", msg, updated=updated)
            return {
                "status": "success",
                "updated": updated,
                "message": msg,
                "timestamp": now
            }

    def check_panneaux(self, force: bool = False) -> Dict[str, Any]:
        """
        Cadence Hebdomadaire (1x par semaine) :
        Vérifie et met à jour l'inventaire des panneaux (ID, GPS, actifs, photos, axes).
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.state.get("last_panels_check", 0)

            if not force and elapsed < PANELS_INTERVAL_SECONDS:
                remaining_days = round((PANELS_INTERVAL_SECONDS - elapsed) / 86400, 1)
                return {
                    "status": "skipped",
                    "reason": f"Vérification hebdomadaire déjà effectuée. Prochaine dans {remaining_days} jours",
                    "last_check": self.state.get("last_panels_check")
                }

            self.state["status"] = "checking_panels"
            updated = False

            # Vérifier date de modification du CSV de réseau
            csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../mmove_network_enriched.csv"))
            csv_mtime = os.path.getmtime(csv_path) if os.path.exists(csv_path) else 0

            # Si le CSV est plus récent que la dernière mise à jour de panneaux
            last_up = self.state.get("last_panels_updated") or 0
            if csv_mtime > last_up or force:
                from ..build_database import build_unified_database
                build_unified_database()
                if self.engine_tools:
                    self.engine_tools.reload()
                self.state["last_panels_updated"] = now
                updated = True
                msg = "Inventaire hebdomadaire des panneaux actualisé et rechargé en mémoire"
            else:
                msg = "Inventaire des panneaux vérifié : liste conforme et à jour"

            self.state["last_panels_check"] = now
            self.state["status"] = "idle"
            self.log_event("VERIF_PANNEAUX_HEBDO", msg, updated=updated)
            return {
                "status": "success",
                "updated": updated,
                "message": msg,
                "timestamp": now
            }

    def _find_newest_file(self, pattern: str) -> Optional[str]:
        """Recherche le fichier le plus récent correspondant au motif."""
        candidates = []
        for d in [DATA_DIR, DOWNLOADS_DIR]:
            if os.path.exists(d):
                candidates.extend(glob.glob(os.path.join(d, pattern)))
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    def get_summary(self) -> Dict[str, Any]:
        """Retourne un résumé formaté des statuts de synchronisation pour l'UI et l'API."""
        now = time.time()
        
        last_dispo = self.state.get("last_dispo_check", now)
        next_dispo_sec = max(0, DISPO_INTERVAL_SECONDS - (now - last_dispo))
        next_dispo_str = f"dans {int(next_dispo_sec // 60)} min" if next_dispo_sec >= 60 else f"dans {int(next_dispo_sec)}s"

        last_panels = self.state.get("last_panels_check", now)
        next_panels_sec = max(0, PANELS_INTERVAL_SECONDS - (now - last_panels))
        next_panels_days = round(next_panels_sec / 86400, 1)

        return {
            "dispo": {
                "cadence": "Toutes les heures",
                "intervalle_secondes": DISPO_INTERVAL_SECONDS,
                "derniere_verification": datetime.fromtimestamp(last_dispo).strftime("%Y-%m-%d %H:%M:%S"),
                "prochaine_verification": next_dispo_str,
                "derniere_mise_a_jour": datetime.fromtimestamp(self.state["last_dispo_updated"]).strftime("%Y-%m-%d %H:%M:%S") if self.state.get("last_dispo_updated") else "Initiale"
            },
            "panneaux": {
                "cadence": "1x par semaine",
                "intervalle_jours": 7,
                "derniere_verification": datetime.fromtimestamp(last_panels).strftime("%Y-%m-%d %H:%M:%S"),
                "prochaine_verification": f"dans {next_panels_days} jours",
                "derniere_mise_a_jour": datetime.fromtimestamp(self.state["last_panels_updated"]).strftime("%Y-%m-%d %H:%M:%S") if self.state.get("last_panels_updated") else "Initiale"
            },
            "total_remorques_actives": len(self.engine_tools.trailers) if self.engine_tools else 132,
            "statut_daemon": "Actif" if self._running else "En attente",
            "derniers_evenements": self.state.get("history", [])[-5:]
        }

    def start_scheduler(self):
        """Démarre la boucle de vérification en tâche de fond (daemon)."""
        if self._running:
            return
        self._running = True

        def _worker():
            print("[SyncManager] Démarrage du planificateur de synchronisation (Dispo: 1h, Panneaux: 7j)")
            while self._running:
                try:
                    now = time.time()
                    # 1. Vérification horaire des disponibilités
                    if (now - self.state.get("last_dispo_check", 0)) >= DISPO_INTERVAL_SECONDS:
                        print("[SyncManager] Déclenchement de la vérification horaire des disponibilités...")
                        self.check_disponibilites()

                    # 2. Vérification hebdomadaire des panneaux
                    if (now - self.state.get("last_panels_check", 0)) >= PANELS_INTERVAL_SECONDS:
                        print("[SyncManager] Déclenchement de la vérification hebdomadaire des panneaux...")
                        self.check_panneaux()
                except Exception as e:
                    print(f"[SyncManager] Erreur dans le worker: {e}")

                # Pause de 60 secondes entre chaque cycle d'inspection
                time.sleep(60)

        self._thread = threading.Thread(target=_worker, daemon=True, name="SyncScheduler")
        self._thread.start()

    def stop_scheduler(self):
        """Arrête le worker de synchronisation."""
        self._running = False
