import json
import os

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

service_code = """import { GoogleGenAI, FunctionDeclaration, Type, Chat, GenerateContentResponse, Content } from "@google/genai";
import type { Panel } from '../types';

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

// --- Déclarations des Outils ---

const getAvailablePanelsDeclaration: FunctionDeclaration = {
  name: 'get_available_panels',
  description: "Recherche les panneaux publicitaires de 8m² en Wallonie selon des critères spécifiques (ville, village, hameau, axe routier, distance, période). Retourne pour chaque face la prochaine disponibilité exacte.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      periode_souhaitee: {
        type: Type.STRING,
        description: "La période de réservation souhaitée au format AAAA-MM. OBLIGATOIRE pour tester la disponibilité. FACULTATIF pour consulter l'inventaire.",
      },
      province: {
        type: Type.STRING,
        description: "Filtre par province wallonne (ex: 'Liège', 'Namur', 'Hainaut', 'Luxembourg', 'Brabant wallon').",
      },
      axe_routier: {
        type: Type.STRING,
        description: "Filtre par un axe routier spécifique (ex: 'E411', 'N4').",
      },
      direction_souhaitee: {
        type: Type.STRING,
        description: "Filtre par la direction du flux de trafic (ex: 'Bruxelles -> Luxembourg').",
      },
      points_of_interest: {
        type: Type.ARRAY,
        items: { type: Type.STRING },
        description: "Une liste d'adresses, villes, villages ou sections de communes (ex: 'Wierde', 'Sclayn', 'Haute Bise', 'Naninne', 'Namur').",
      },
      distance_max_km: {
        type: Type.NUMBER,
        description: "Le rayon de recherche maximum en kilomètres autour des points d'intérêt. Par défaut: 15.",
      },
      travel_time_min: {
        type: Type.NUMBER,
        description: "Temps de trajet en minutes depuis les points d'intérêt, à convertir en distance.",
      },
    },
    required: [],
  },
};

const sendSelectionEmailDeclaration: FunctionDeclaration = {
  name: 'send_selection_email',
  description: "Envoie un email récapitulatif de la sélection de panneaux au client.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      email_client: {
        type: Type.STRING,
        description: "L'adresse email du client destinataire.",
      },
      selection_text: {
        type: Type.STRING,
        description: "Le texte formaté (liste des panneaux, IDs, villes, directions) à inclure dans le corps de l'email.",
      },
    },
    required: ['email_client', 'selection_text'],
  },
};

// Matrice consolidée des disponibilités réelles (Face IN, Face OUT et globale)
// Résout le bug du script Apps Script distant qui exigeait les deux faces libres en même temps
const TRUE_DISPOS: Record<string, { d: string; in: string; out: string }> = """ + dispos_json + """;

// Normalisation insensible aux accents et à la casse
function normalizeStr(str: string): string {
  return (str || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .replace(/[^a-z0-9]/g, " ")
    .replace(/\\s+/g, " ")
    .trim();
}

// Indexation et recherche floue des alias géographiques (Villages, sections, zonings)
function matchLocality(panel: any, pointsOfInterest?: any): { isDirectMatch: boolean; bonus: number } {
  if (!pointsOfInterest) return { isDirectMatch: false, bonus: 0 };

  const queries: string[] = Array.isArray(pointsOfInterest)
    ? pointsOfInterest.map((p) => String(p))
    : String(pointsOfInterest).split(/[;,]/);

  const locNorm = normalizeStr(panel.localisation || "");
  const villeNorm = normalizeStr(panel.ville || "");
  const axeNorm = normalizeStr(panel.axe_routier || "");
  const ctxNorm = normalizeStr(panel.contexte_visibilite || "");
  const combinedBag = `${locNorm} ${villeNorm} ${axeNorm} ${ctxNorm}`;

  for (const rawQ of queries) {
    const q = normalizeStr(rawQ);
    if (!q || q.length < 3) continue;

    if (locNorm.includes(q) || villeNorm === q) {
      return { isDirectMatch: true, bonus: 100.0 };
    }
    if (combinedBag.includes(q)) {
      return { isDirectMatch: false, bonus: 35.0 };
    }
  }

  return { isDirectMatch: false, bonus: 0 };
}

// Cache mémoire client (TTL 30 minutes)
interface CacheEntry {
  timestamp: number;
  data: Panel[];
}
const clientCache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 30 * 60 * 1000;

const API_URL = "https://script.google.com/macros/s/AKfycbwjIMSlE_pmjlxnHdiuEB4Kzp_Yfdx_5m5iHvoT9tvQivSF8CrhknFCW_ha92VrRAQ/exec";

const getAvailablePanels = async (args: any): Promise<Panel[]> => {
  try {
    console.log("[geminiService] Calling get_available_panels with args:", args);
    const cacheKey = JSON.stringify(args || {});
    const now = Date.now();
    const cached = clientCache.get(cacheKey);
    if (cached && (now - cached.timestamp < CACHE_TTL_MS)) {
      console.log("[geminiService Cache Hit] Returning", cached.data.length, "panels");
      return cached.data;
    }

    const payload = {
      ...args,
      action: 'get_panels',
    };

    if (payload.points_of_interest && Array.isArray(payload.points_of_interest)) {
      payload.points_of_interest = payload.points_of_interest.join(';');
    }

    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload),
      redirect: 'follow',
    });

    if (!response.ok) {
      console.error("get_available_panels response not ok:", response.status);
      return [];
    }

    const text = await response.text();
    let data: any;
    try {
      data = JSON.parse(text);
    } catch (e) {
      console.error("Failed to parse get_available_panels JSON:", text);
      return [];
    }

    const rawPanels: any[] = data?.available_panels || data?.panels || [];
    if (!Array.isArray(rawPanels)) return [];

    const cleanedPanels: Panel[] = rawPanels
      .filter((p: any) => {
        const activeVal = String(p.active ?? p.Active ?? "Y").trim().toUpperCase();
        return activeVal === "Y" || activeVal === "O" || activeVal === "OUI";
      })
      .map((p: any) => {
        const remId = String(p.remorque || p.id || p.ID || "").replace(/\\.0$/, "").trim();
        const faceVal = String(p.face || p.Face || "IN/OUT").trim();
        const faceNorm = faceVal.toUpperCase();

        const freq = Number(p.frequentation || p.Frequentation || p.Frequentation_Moyenne_veh_jour || 0);
        const ots = Number(p.ots || p.OTS || p.ots_mensuel || (freq ? freq * 30 * 1.2 : 0));

        const rawDist = p.distance_km ?? p.Distance_Km ?? p.distance;
        let parsedDist: number | undefined = undefined;
        if (rawDist !== undefined && rawDist !== null && rawDist !== "") {
          const n = typeof rawDist === "number" ? rawDist : parseFloat(String(rawDist).replace(",", "."));
          if (!isNaN(n)) parsedDist = Math.round(n * 10) / 10;
        }

        // CORRECTION VRAIE DISPONIBILITÉ FACE PAR FACE
        const trueDispo = TRUE_DISPOS[remId];
        let computedDispo = String(p.prochaine_dispo || p.Prochaine_Dispo || p.disponibilite || "").trim();
        if (trueDispo) {
          if (faceNorm === "IN" && trueDispo.in) {
            computedDispo = trueDispo.in;
          } else if (faceNorm === "OUT" && trueDispo.out) {
            computedDispo = trueDispo.out;
          } else if (trueDispo.d) {
            computedDispo = trueDispo.d;
          }
        }

        const panelObj: Panel = {
          id: remId,
          remorque: remId,
          ville: String(p.ville || p.Ville || "").trim(),
          localisation: String(p.localisation || p.Localisation || "").trim(),
          axe_routier: String(p.axe_routier || p.Axe_Routier || p.axe || "").trim(),
          direction: String(p.direction || p.Direction || "").trim(),
          face: faceVal,
          distance_km: parsedDist,
          prochaine_dispo: computedDispo,
          frequentation: freq || undefined,
          ots: Math.round(ots) || undefined,
          contexte_visibilite: String(p.contexte_visibilite || p.Contexte_Visibilite || "").trim(),
          lien: String(p.lien || p.Lien || p.url || `https://remorquepublicitaire.be/remorque/${remId}`).trim(),
          photo: String(p.photo || p.photo_in || p.Photo || "").trim(),
          active: "O",
        };

        const { isDirectMatch, bonus } = matchLocality(panelObj, args?.points_of_interest);
        panelObj.is_direct_match = isDirectMatch;

        // Calcul score composite
        const distScore = parsedDist !== undefined ? Math.max(0, 100 - parsedDist * 5) : 50;
        const freqScore = Math.min(100, (freq / 35000) * 100);
        panelObj.score = (distScore * 0.4) + (freqScore * 0.3) + bonus;

        return panelObj;
      });

    // Tri hiérarchisé : correspondances directes en tête absolue, puis par score composite
    cleanedPanels.sort((a, b) => {
      const aDirect = a.is_direct_match ? 1 : 0;
      const bDirect = b.is_direct_match ? 1 : 0;
      if (aDirect !== bDirect) return bDirect - aDirect;
      return (b.score || 0) - (a.score || 0);
    });

    const topPanels = cleanedPanels.slice(0, 5);
    clientCache.set(cacheKey, { timestamp: now, data: topPanels });
    console.log("[geminiService] Top 5 panels returned:", topPanels.map(p => `#${p.id} (${p.localisation}) face=${p.face} dispo=${p.prochaine_dispo}`));
    return topPanels;
  } catch (error) {
    console.error("Error calling get_available_panels:", error);
    return [];
  }
};

const sendSelectionEmail = async (args: any): Promise<any> => {
  try {
    console.log("Calling send_selection_email with args:", args);
    const email = args.email_client || args.email || args.email_address || args.recipient;
    const selection = args.selection_text || args.selection || args.text || args.message || args.content;

    const payload = {
      ...args,
      action: 'send_email',
      email: email,
      selection_text: selection,
    };

    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload),
      redirect: 'follow',
    });

    if (!response.ok) return { status: 'error', message: 'Erreur HTTP' };
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch (e) {
      return { status: 'success', raw: text };
    }
  } catch (error) {
    console.error("Error sending email:", error);
    return { status: 'error', message: String(error) };
  }
};

export const startChat = async (): Promise<Chat> => {
  const today = new Date().toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  const chat = ai.chats.create({
    model: 'gemini-2.5-flash',
    config: {
      tools: [
        { functionDeclarations: [getAvailablePanelsDeclaration, sendSelectionEmailDeclaration] },
        { googleMaps: {} }
      ],
      toolConfig: { includeServerSideToolInvocations: true },
      systemInstruction: `### 1. RÔLE ET IDENTITÉ
Tu es l'**Agent Commercial Expert** de la société **M Move** (remorquepublicitaire.be).
* **Ta mission :** Vendre des campagnes d'affichage 8m² et conseiller les prospects sur leur stratégie et leur créativité.
* **Ton Ton :** Professionnel, dynamique, expert, chaleureux.
* **Date actuelle de référence : ${today}**

### 2. ARGUMENTS COMMERCIAUX
* **PUISSANCE :** N°1 en Wallonie, +300 faces, couverture complète.
* **VISIBILITÉ :** Format 8m² immanquable, non noyé dans la masse, visible 24h/24.
* **SERVICE "TOUT COMPRIS" :** Prix incluant location, impression, placement, et **toutes les taxes régionales et communales incluses**.
* **FLEXIBILITÉ :** Ciblage ultra-précis au plus près des clients.

### 3. RÈGLES TECHNIQUES & FORMATAGE DES RÉSULTATS
* **Recherche (\`get_available_panels\`) :**
    * Ajoute toujours \`", Belgique"\` aux lieux pour le géocodage.
    * **RÈGLE CRITIQUE :** Ne proposer QUE les remorques actives.
    * Ne cite JAMAIS les termes techniques "Face IN" / "Face OUT" dans le corps du texte si non demandé.

* **FORMAT OBLIGATOIRE (Top 3 à 5) :**
    * Pour chaque panneau :
      \`* [**#ID - Ville - Localisation** ↗️](lien)\` - **Direction :** [direction]
      *(Trafic : [frequentation] véh./jour | Visibilité : ~[ots] OTS/mois)*
      *Atout :* [contexte_visibilite]

* **DEMANDE "QUAND EST-CE LIBRE ?" :**
    * Affiche le nom cliquable suivi de : \`📅 **Disponible dès : [prochaine_dispo]**\` (indique fidèlement la date renvoyée par le panneau, ex: 2026-12 pour Décembre 2026).

* **BLOC JSON DES CARTES (OBLIGATOIRE EN FIN DE MESSAGE) :**
    * À la fin de ta réponse, génère TOUJOURS le bloc de code JSON suivant avec les panneaux sélectionnés :
\`\`\`json
[
  {
    "id": "[ID]",
    "remorque": "[ID]",
    "ville": "[Ville]",
    "localisation": "[Localisation]",
    "face": "[Face]",
    "direction": "[Direction]",
    "axe_routier": "[Axe]",
    "prochaine_dispo": "[AAAA-MM]",
    "distance_km": [distance],
    "frequentation": [frequentation],
    "ots": [ots],
    "contexte_visibilite": "[Atout]",
    "lien": "[Lien]"
  }
]
\`\`\`

### 4. CONSEILS CRÉATIFS M MOVE (Attention 3 à 5 secondes)
1. **Règle des 7 mots maximum** : un message unique et percutant.
2. **Lisibilité XXL** : typographie bâton sans-serif très grasse.
3. **Contraste fort** (Noir/Jaune, Blanc/Rouge).
4. **Hero Shot** : une seule image forte.
5. **Call to Action** : fléchage ou site web court. **Pas de QR Code**.

### 5. SUPPORT TECHNIQUE
* **Deadline :** Le 15 du mois précédent.
* **Format :** 390x200 cm (fichier 392x202 cm), échelle 1/1, PDF CMJN 65 dpi min.
* **Envoi :** \`mmove@mediasee.be\`.

### 6. MODE ADMINISTRATEUR ("Corentin")
* Si l'utilisateur mentionne être Corentin ou demande le mode debug, réponds avec franchise et clarté technique.`,
    },
  });
  return chat;
};

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

async function sendMessageWithRetry(chat: Chat, payload: { message: string | any[] }): Promise<GenerateContentResponse> {
  let lastError: any = null;
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await chat.sendMessage(payload);
    } catch (error: any) {
      lastError = error;
      const isQuotaError =
        error?.status === 429 ||
        error?.code === 429 ||
        error?.message?.includes('429') ||
        error?.message?.includes('RESOURCE_EXHAUSTED');

      if (isQuotaError && attempt < MAX_RETRIES) {
        console.warn(`[Quota Exceeded] Attempt ${attempt} failed. Retrying in ${RETRY_DELAY_MS * attempt}ms...`);
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS * attempt));
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

export const sendMessage = async (chat: Chat, message: string): Promise<GenerateContentResponse> => {
  let response: GenerateContentResponse = await sendMessageWithRetry(chat, { message });

  let loopCount = 0;
  while (response.functionCalls && response.functionCalls.length > 0 && loopCount < 3) {
    loopCount++;
    const functionCalls = response.functionCalls;

    const toolResultsPromises = functionCalls.map(async (call) => {
      if (call.name === 'get_available_panels') {
        const result = await getAvailablePanels(call.args);
        return {
          functionResponse: {
            name: call.name,
            response: { result: result },
          },
        };
      }
      if (call.name === 'send_selection_email') {
        const result = await sendSelectionEmail(call.args);
        return {
          functionResponse: {
            name: call.name,
            response: { result: result },
          },
        };
      }
      return null;
    });

    const toolResults = (await Promise.all(toolResultsPromises)).filter(
      (result): result is NonNullable<typeof result> => result !== null
    );

    if (toolResults.length > 0) {
      response = await sendMessageWithRetry(chat, { message: toolResults });
    } else {
      break;
    }
  }

  return response;
};

export const getPanelsFromResponse = (text: string | undefined): Panel[] => {
  if (!text) return [];
  const jsonMatch = text.match(/```json\\s*([\\s\\S]*?)\\s*```/);
  if (jsonMatch && jsonMatch[1]) {
    try {
      const data = JSON.parse(jsonMatch[1]);
      if (Array.isArray(data)) {
        return data as Panel[];
      }
    } catch (e) {
      console.error("Failed to parse JSON panels:", e);
    }
  }
  return [];
};
"""

os.makedirs('ai_studio_optimized/services', exist_ok=True)
with open('ai_studio_optimized/services/geminiService.ts', 'w') as f:
    f.write(service_code)

print("SUCCESS: Generated ai_studio_optimized/services/geminiService.ts")
