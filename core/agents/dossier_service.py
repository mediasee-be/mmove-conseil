"""
Service de gestion des dossiers de propositions commerciales M Move.
Gère l'enregistrement, l'archivage, la recherche et l'isolation des dossiers :
- Chaque commercial n'accède qu'à ses propres dossiers.
- Les administrateurs (Corentin Hubert, Direction) ont une vue globale sur tous les dossiers avec possibilité de filtrer.
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from core.agents.salesperson_service import SalespersonService

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOSSIERS_DIR = os.path.join(BASE_DIR, "data", "dossiers")


class DossierService:
    """Gère le stockage et l'accès sécurisé aux dossiers clients de propositions."""

    def __init__(self, dossiers_dir: str = DOSSIERS_DIR, salesperson_service: Optional[SalespersonService] = None):
        self.dossiers_dir = dossiers_dir
        os.makedirs(self.dossiers_dir, exist_ok=True)
        self.sales_service = salesperson_service or SalespersonService()

    def _sanitize_slug(self, text: str) -> str:
        """Génère un slug propre pour les identifiants et noms de fichiers."""
        if not text:
            return "sans_nom"
        return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")[:20]

    def save_dossier(
        self,
        salesperson_id: str,
        client_name: str,
        campaign_plan: Dict[str, Any],
        candidate_panels: Optional[List[Dict[str, Any]]] = None,
        user_message: str = "",
        status: str = "Proposition générée"
    ) -> Dict[str, Any]:
        """
        Enregistre un dossier commercial avec sa proposition, ses panneaux et son PDF.
        """
        sp = self.sales_service.get(salesperson_id)
        sp_initials = sp.get("initials", "DR")
        sp_name = sp.get("name", "Commercial")

        now_ts = int(time.time())
        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
        client_slug = self._sanitize_slug(client_name)
        dossier_id = f"dos_{sp_initials.lower()}_{client_slug}_{now_ts}"

        summary = campaign_plan.get("summary", {}) if campaign_plan else {}
        months = campaign_plan.get("months", []) if campaign_plan else []
        periods = campaign_plan.get("periods", []) if campaign_plan else []
        pdf_url = campaign_plan.get("pdf_url") if campaign_plan else ""

        # Extraction des panneaux recommandés
        panels_summary = []
        if candidate_panels:
            for p in candidate_panels:
                panels_summary.append({
                    "id": str(p.get("id") or p.get("remorque") or "").replace(".0", ""),
                    "ville": p.get("ville", ""),
                    "axe_routier": p.get("axe_routier") or p.get("code_route") or "",
                    "direction": p.get("direction", ""),
                    "frequentation": p.get("frequentation", 0),
                    "ots": p.get("ots", 0),
                    "lat": p.get("lat"),
                    "lng": p.get("lng"),
                    "photo": p.get("photo") or p.get("image_url") or "",
                    "lien": p.get("lien") or ""
                })

        dossier_data = {
            "id": dossier_id,
            "created_at": date_str,
            "timestamp": now_ts,
            "salesperson_id": sp_initials,
            "salesperson_name": sp_name,
            "salesperson_initials": sp_initials,
            "client_name": client_name or "Client Partenaire",
            "location": summary.get("location", "Wallonie"),
            "periods": periods,
            "months_count": len(months),
            "faces_count": summary.get("total_faces_deployed", len(candidate_panels or [])),
            "total_ots": summary.get("total_cumulative_ots", 0),
            "avg_veh_per_day": summary.get("avg_veh_per_day", 0),
            "pdf_url": pdf_url,
            "panels": panels_summary,
            "campaign_plan": campaign_plan,
            "user_message": user_message,
            "status": status
        }

        file_path = os.path.join(self.dossiers_dir, f"{dossier_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(dossier_data, f, ensure_ascii=False, indent=2)
            logger.info("Dossier sauvegardé avec succès : %s pour %s", dossier_id, sp_name)
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde du dossier %s : %s", dossier_id, e)

        return dossier_data

    def get_dossier(self, dossier_id: str, requesting_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Récupère un dossier en vérifiant les droits d'accès."""
        file_path = os.path.join(self.dossiers_dir, f"{dossier_id}.json")
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Vérification des droits d'accès : le propriétaire ou un admin
            if requesting_user_id:
                is_admin = self.sales_service.is_admin(requesting_user_id)
                owner_id = data.get("salesperson_id", "")
                user_req = str(requesting_user_id).upper()
                if not is_admin and owner_id.upper() != user_req:
                    logger.warning("Accès refusé au dossier %s pour l'utilisateur %s", dossier_id, requesting_user_id)
                    return None

            return data
        except Exception as e:
            logger.error("Erreur lecture dossier %s : %s", dossier_id, e)
            return None

    def list_dossiers(
        self,
        requesting_user_id: Optional[str] = None,
        filter_salesperson: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Liste les dossiers en appliquant la politique de confidentialité :
        - Un commercial ne voit que ses propres dossiers.
        - Un admin peut voir tous les dossiers ou filtrer par commercial.
        """
        dossiers = []
        if not os.path.exists(self.dossiers_dir):
            return []

        is_admin = self.sales_service.is_admin(requesting_user_id)
        user_req = str(requesting_user_id).strip().upper() if requesting_user_id else ""

        for fname in os.listdir(self.dossiers_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.dossiers_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        d = json.load(f)

                    owner_id = d.get("salesperson_id", "").upper()

                    # Règle d'accès
                    if not is_admin:
                        # Commercial standard : voit uniquement ses dossiers
                        if owner_id != user_req:
                            continue
                    else:
                        # Admin : peut filtrer par commercial si demandé
                        if filter_salesperson and filter_salesperson.upper() not in ["ALL", "TOUS", ""]:
                            if owner_id != filter_salesperson.upper():
                                continue

                    # Version allégée pour affichage en liste
                    dossiers.append({
                        "id": d.get("id"),
                        "created_at": d.get("created_at"),
                        "timestamp": d.get("timestamp", 0),
                        "salesperson_id": d.get("salesperson_id"),
                        "salesperson_name": d.get("salesperson_name"),
                        "salesperson_initials": d.get("salesperson_initials"),
                        "client_name": d.get("client_name"),
                        "location": d.get("location"),
                        "periods": d.get("periods"),
                        "faces_count": d.get("faces_count", 0),
                        "total_ots": d.get("total_ots", 0),
                        "pdf_url": d.get("pdf_url"),
                        "status": d.get("status", "Proposition générée")
                    })
                except Exception as e:
                    logger.warning("Erreur chargement résumé dossier %s : %s", fname, e)

        # Tri par date décroissante (les plus récents en premier)
        dossiers.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return dossiers

    def get_dossier_by_pdf(self, pdf_filename: str) -> Optional[Dict[str, Any]]:
        """Recherche si un dossier enregistré correspond déjà à ce fichier PDF."""
        if not pdf_filename or not os.path.exists(self.dossiers_dir):
            return None
        clean_name = os.path.basename(pdf_filename)
        for fname in os.listdir(self.dossiers_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.dossiers_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pdf_url = data.get("pdf_url", "")
                    if clean_name in pdf_url:
                        return data
                except Exception:
                    continue
        return None

    def delete_dossier(self, dossier_id: str, requesting_user_id: Optional[str] = None) -> bool:
        """Supprime un dossier si l'utilisateur est le propriétaire ou admin."""
        d = self.get_dossier(dossier_id, requesting_user_id=requesting_user_id)
        if not d:
            return False

        # Supprimer le PDF associé s'il se trouve dans data/pdf/
        pdf_url = d.get("pdf_url", "")
        if pdf_url:
            pdf_fname = os.path.basename(pdf_url.split("file=")[-1] if "file=" in pdf_url else pdf_url)
            pdf_path = os.path.join(BASE_DIR, "data", "pdf", pdf_fname)
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    logger.info("PDF associé supprimé : %s", pdf_path)
                except Exception as e:
                    logger.warning("Erreur suppression PDF associé %s : %s", pdf_path, e)

        file_path = os.path.join(self.dossiers_dir, f"{dossier_id}.json")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info("Dossier %s supprimé par %s", dossier_id, requesting_user_id)
                return True
        except Exception as e:
            logger.error("Erreur suppression dossier %s : %s", dossier_id, e)
        return False

