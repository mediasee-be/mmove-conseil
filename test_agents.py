"""
Banc de test et Benchmark du Système Multi-Agents M Move
Mesure la latence totale, le temps d'extraction, la vitesse du moteur géo-dispo,
la qualité des réponses commerciales et l'absence d'erreurs de quota.
"""

import time
import json
from core.agents.coordinator import CoordinatorAgent

TEST_QUERIES = [
    {
        "title": "Test 1 : Requête non structurée (Secteur + Ville + Mois)",
        "query": "Bonjour, je cherche 3 panneaux pour un magasin de bricolage près de Namur en mai 2026",
    },
    {
        "title": "Test 2 : Multi-axes et multi-mois (Fin d'année)",
        "query": "Je suis un concessionnaire automobile et je veux des emplacements à fort trafic sur la N4 ou la E411 pour la fin d'année",
    },
    {
        "title": "Test 3 : Vérification de disponibilité par ID de remorque",
        "query": "Quand est libre le panneau #114 ?",
    },
    {
        "title": "Test 4 : Identification d'emplacement par point d'intérêt",
        "query": "C'est quel panneau qui se trouve près de la clinique d'Ottignies ?",
    },
    {
        "title": "Test 5 : Conseil créatif pur",
        "query": "Quels sont vos meilleurs conseils pour concevoir un visuel d'affichage 8m² percutant ?",
    }
]

def run_benchmarks():
    print("=" * 70)
    print("🚀 DÉMARRAGE DU BENCHMARK MULTI-AGENTS M MOVE")
    print("=" * 70)

    coordinator = CoordinatorAgent()
    results = []

    for idx, t in enumerate(TEST_QUERIES, start=1):
        print(f"\n--- {t['title']} ---")
        print(f"Message utilisateur : \"{t['query']}\"")

        start = time.time()
        try:
            resp = coordinator.process_message(t["query"])
            total_time = round(time.time() - start, 2)
            timing = resp.get("timing", {})
            panels = resp.get("panels", [])

            print(f"✅ Terminé en {total_time}s !")
            print(f"   ⏱️  Extraction NLU : {timing.get('extraction_ms')} ms")
            print(f"   ⏱️  Moteur Déterministe : {timing.get('engine_ms')} ms")
            print(f"   ⏱️  Synthèse Commerciale : {timing.get('synthesis_ms')} ms")
            print(f"   🎯 Intention détectée : {resp.get('extracted', {}).get('intent')}")
            print(f"   📊 Panneaux qualifiés retournés : {len(panels)}")
            for p in panels:
                print(f"      - #{p['id']} {p['ville']} - {p['localisation']} (Trafic: {p['frequentation']:,} v/j, Score: {p.get('score')})")

            print(f"\n📝 Extrait de la réponse commerciale :")
            preview_lines = resp["text"].split("\n")[:8]
            print("\n".join(preview_lines))
            if len(resp["text"].split("\n")) > 8:
                print("   ...")

            results.append({
                "query": t["query"],
                "total_time": total_time,
                "timing": timing,
                "panels_count": len(panels),
                "status": "SUCCESS"
            })
        except Exception as e:
            print(f"❌ Erreur sur la requête : {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "query": t["query"],
                "error": str(e),
                "status": "ERROR"
            })

    print("\n" + "=" * 70)
    print("📈 RÉSUMÉ GLOBAL DU BENCHMARK")
    print("=" * 70)
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    avg_total = sum(r["total_time"] for r in results if r["status"] == "SUCCESS") / max(1, success_count)
    avg_engine = sum(r["timing"]["engine_ms"] for r in results if r["status"] == "SUCCESS") / max(1, success_count)
    
    print(f"Taux de succès : {success_count}/{len(TEST_QUERIES)}")
    print(f"Temps de réponse moyen global : {avg_total:.2f} secondes (ancien système : ~25 secondes)")
    print(f"Temps moyen moteur déterministe : {avg_engine:.2f} ms")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmarks()
