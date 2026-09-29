import json

with open('data/mmove_db.json') as f:
    db = json.load(f)

mapping = {}
for rem_id, t in sorted(db.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
    mapping[rem_id] = {
        'd': t.get('prochaine_dispo') or '2026-01',
        'in': t.get('prochaine_dispo_in') or '2026-01',
        'out': t.get('prochaine_dispo_out') or '2026-01'
    }

dispos_json = json.dumps(mapping)

with open('ai_studio_optimized/services/geminiService_original.ts') as f:
    code = f.read()

# Strip any metadata prefix before import { GoogleGenAI
import_idx = code.find('import { GoogleGenAI')
if import_idx != -1:
    code = code[import_idx:]

# Fix trailing A
code = code.strip()
if code.endswith(';A'):
    code = code[:-2] + ';'

# Injection of TRUE_DISPOS and matchLocality
injection = f"""// Matrice des disponibilités réelles (Face IN, Face OUT et globale)
const TRUE_DISPOS: Record<string, {{ d: string; in: string; out: string }}> = {dispos_json};

function normalizeStr(str: string): string {{
  return (str || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\\u0300-\\u036f]/g, '')
    .replace(/[^a-z0-9]/g, ' ')
    .replace(/\\s+/g, ' ')
    .trim();
}}

function matchLocality(panel: any, pointsOfInterest?: any): {{ isDirectMatch: boolean; bonus: number }} {{
  if (!pointsOfInterest) return {{ isDirectMatch: false, bonus: 0 }};
  const queries: string[] = Array.isArray(pointsOfInterest)
    ? pointsOfInterest.map((p) => String(p))
    : String(pointsOfInterest).split(/[;,]/);

  const locNorm = normalizeStr(panel.localisation || '');
  const villeNorm = normalizeStr(panel.ville || '');
  const axeNorm = normalizeStr(panel.axe_routier || '');
  const ctxNorm = normalizeStr(panel.contexte_visibilite || '');
  const combinedBag = `${{locNorm}} ${{villeNorm}} ${{axeNorm}} ${{ctxNorm}}`;

  for (const rawQ of queries) {{
    const q = normalizeStr(rawQ);
    if (!q || q.length < 3) continue;
    if (locNorm.includes(q) || villeNorm === q) {{
      return {{ isDirectMatch: true, bonus: 100.0 }};
    }}
    if (combinedBag.includes(q)) {{
      return {{ isDirectMatch: false, bonus: 35.0 }};
    }}
  }}
  return {{ isDirectMatch: false, bonus: 0 }};
}}
"""

# Locate the return inside getAvailablePanels
marker_start = "if (data && data.available_panels && Array.isArray(data.available_panels)) {"
marker_end = "return [];\n    } catch (error) {"

idx_start = code.find(marker_start)
idx_end = code.find(marker_end, idx_start)
assert idx_start != -1 and idx_end != -1, f"Markers not found: start={idx_start}, end={idx_end}"

replacement = """if (data && data.available_panels && Array.isArray(data.available_panels)) {
            const parsedPanels: Panel[] = data.available_panels
              .filter((p: any) => {
                const activeVal = String(p.active ?? p.Active ?? p.actif ?? 'Y').trim().toUpperCase();
                return activeVal === 'Y' || activeVal === 'O' || activeVal === 'OUI' || activeVal === 'DISPONIBLE';
              })
              .map((p: any) => {
                const remId = String(p.remorque || p.id || p.ID || '').replace(/\\.0$/, '').trim();
                const faceVal = String(p.face || p.Face || 'IN').trim();
                const faceNorm = faceVal.toUpperCase();

                // Correction avec TRUE_DISPOS
                const trueDispo = TRUE_DISPOS[remId];
                let computedDispo = String(p.prochaine_dispo || p.Prochaine_Dispo || p.disponibilite || '').trim();
                if (trueDispo) {
                  if (faceNorm === 'IN' && trueDispo.in) {
                    computedDispo = trueDispo.in;
                  } else if (faceNorm === 'OUT' && trueDispo.out) {
                    computedDispo = trueDispo.out;
                  } else if (trueDispo.d) {
                    computedDispo = trueDispo.d;
                  }
                }

                const rawDist = p.distance_km ?? p.Distance_Km ?? p.distance;
                let parsedDist: number | undefined = undefined;
                if (rawDist !== undefined && rawDist !== null && rawDist !== '') {
                  const n = typeof rawDist === 'number' ? rawDist : parseFloat(String(rawDist).replace(',', '.'));
                  if (!isNaN(n)) parsedDist = Math.round(n * 10) / 10;
                }

                const freq = Number(p.frequentation || p.Frequentation || 0);
                const ots = Number(p.ots || p.OTS || (freq ? freq * 30 * 1.2 : 0));

                const panelObj: any = {
                  id: remId,
                  remorque: remId,
                  province: p.province || p.Province || '',
                  axe_routier: p.axe_routier || p.Axe_Routier || p.axe || '',
                  direction: p.direction || p.Direction || '',
                  face: faceVal,
                  adresse: p.adresse || p.Adresse || '',
                  ville: p.ville || p.Ville || '',
                  code_postal: p.code_postal || p.Code_Postal || p.cp || '',
                  localisation: p.localisation || p.Localisation || '',
                  lien: p.lien || p.Lien || p.url || ('https://remorquepublicitaire.be/remorque/' + remId),
                  distance_km: parsedDist,
                  prochaine_dispo: computedDispo,
                  active: 'O',
                  frequentation: freq || undefined,
                  ots: Math.round(ots) || undefined,
                  contexte_visibilite: p.contexte_visibilite || p.Contexte_Visibilite || '',
                  photo: p.photo || p.Photo || '',
                };

                const { isDirectMatch, bonus } = matchLocality(panelObj, args?.points_of_interest);
                panelObj.is_direct_match = isDirectMatch;
                const distScore = parsedDist !== undefined ? Math.max(0, 100 - parsedDist * 5) : 50;
                const freqScore = Math.min(100, (freq / 35000) * 100);
                panelObj.score = (distScore * 0.4) + (freqScore * 0.3) + bonus;

                return panelObj as Panel;
              });

            // Tri par pertinence : Direct Match en tête absolue, puis score
            parsedPanels.sort((a: any, b: any) => {
              const aDirect = a.is_direct_match ? 1 : 0;
              const bDirect = b.is_direct_match ? 1 : 0;
              if (aDirect !== bDirect) return bDirect - aDirect;
              return (b.score || 0) - (a.score || 0);
            });

            const top5 = parsedPanels.slice(0, 5);
            console.log('[getAvailablePanels] Returning top 5 panels:', top5.map((p: any) => '#' + p.id + ' ' + p.localisation + ' (' + p.face + ') -> dispo: ' + p.prochaine_dispo));
            return top5;
        }
        """

new_code = code[:idx_start] + replacement + code[idx_end:]

# Inject TRUE_DISPOS before const API_URL =
new_code = new_code.replace("const API_URL =", injection + "\nconst API_URL =")

# Ensure API_KEY fallback
# Keep original API key line: const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

with open('ai_studio_optimized/services/geminiService.ts', 'w') as f:
    f.write(new_code)

print("SUCCESS: Wrote patched ai_studio_optimized/services/geminiService.ts")
