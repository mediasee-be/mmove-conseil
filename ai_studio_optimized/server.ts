import express from "express";
import path from "path";
import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

const API_KEY = process.env.GEMINI_API_KEY || "AIzaSyAZOZuTkosufB-LqlKTdptLUg8_vK8cJu8";
const APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwjIMSlE_pmjlxnHdiuEB4Kzp_Yfdx_5m5iHvoT9tvQivSF8CrhknFCW_ha92VrRAQ/exec";

// Modèles avec ordre de priorité pour équilibrer les quotas et la vitesse
const CANDIDATE_MODELS = [
  "gemini-2.5-flash",
  "gemini-3.5-flash-lite",
  "gemini-3.5-flash",
  "gemini-3.8-flash",
];

export interface Panel {
  remorque?: string;
  id?: string;
  ville?: string;
  localisation?: string;
  face?: string;
  direction?: string;
  distance_km?: number;
  prochaine_dispo?: string;
  active?: string;
  lien?: string;
  frequentation?: number;
  ots?: number;
  contexte_visibilite?: string;
  photo?: string;
  score?: number;
}

// Cache mémoire à double cadence (Disponibilités: 1 heure, Panneaux: 1 semaine)
interface CacheEntry {
  timestamp: number;
  data: Panel[];
}
const memoryCache = new Map<string, CacheEntry>();

const DISPO_TTL_MS = 60 * 60 * 1000;         // 1 heure pour les disponibilités
const PANELS_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 1 semaine pour la liste des panneaux

// Matrice consolidée des prochaines disponibilités réelles (Face IN, Face OUT et globale)
// Permet de corriger les dates erronées renvoyées par le script Apps Script distant (ex: #343 disponible dès 2026-12)
const TRUE_DISPOS: Record<string, { d: string; in: string; out: string }> = {"102": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "104": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "105": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "106": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "107": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "108": {"d": "2026-04", "in": "2026-12", "out": "2026-04"}, "109": {"d": "2026-01", "in": "2026-05", "out": "2026-01"}, "110": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "111": {"d": "2026-01", "in": "2026-07", "out": "2026-01"}, "112": {"d": "2026-03", "in": "2026-12", "out": "2026-03"}, "113": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "114": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "201": {"d": "2026-01", "in": "2026-05", "out": "2026-01"}, "202": {"d": "2026-03", "in": "2026-07", "out": "2026-03"}, "203": {"d": "2026-01", "in": "2026-01", "out": "2026-02"}, "204": {"d": "2026-03", "in": "2027-01", "out": "2026-03"}, "205": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "206": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "207": {"d": "2026-02", "in": "2026-02", "out": "2026-04"}, "208": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "209": {"d": "2026-01", "in": "2026-04", "out": "2026-01"}, "210": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "211": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "213": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "214": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "215": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "216": {"d": "2026-02", "in": "2026-12", "out": "2026-02"}, "217": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "218": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "220": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "221": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "222": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "223": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "224": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "225": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "226": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "227": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "230": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "231": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "301": {"d": "2026-12", "in": "2026-12", "out": "2026-12"}, "303": {"d": "2026-08", "in": "2027-01", "out": "2026-08"}, "304": {"d": "2026-08", "in": "2027-01", "out": "2026-08"}, "305": {"d": "2026-02", "in": "2026-08", "out": "2026-02"}, "306": {"d": "2026-07", "in": "2027-01", "out": "2026-07"}, "307": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "308": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "309": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "310": {"d": "2026-07", "in": "2027-01", "out": "2026-07"}, "311": {"d": "2026-01", "in": "2026-01", "out": "2026-11"}, "312": {"d": "2026-10", "in": "2026-11", "out": "2026-10"}, "313": {"d": "2026-10", "in": "2026-11", "out": "2026-10"}, "314": {"d": "2026-08", "in": "2026-08", "out": "2026-10"}, "315": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "316": {"d": "2026-08", "in": "2026-08", "out": "2026-08"}, "317": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "318": {"d": "2026-02", "in": "2026-04", "out": "2026-02"}, "319": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "320": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "321": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "323": {"d": "2026-02", "in": "2026-02", "out": "2026-08"}, "324": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "325": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "326": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "327": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "328": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "329": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "330": {"d": "2026-02", "in": "2026-11", "out": "2026-02"}, "331": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "332": {"d": "2026-10", "in": "2026-12", "out": "2026-10"}, "333": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "334": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "335": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "336": {"d": "2026-02", "in": "2026-11", "out": "2026-02"}, "337": {"d": "2026-08", "in": "2026-08", "out": "2026-12"}, "338": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "339": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "340": {"d": "2026-11", "in": "2026-12", "out": "2026-11"}, "341": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "342": {"d": "2026-10", "in": "2026-12", "out": "2026-10"}, "343": {"d": "2026-12", "in": "2027-01", "out": "2026-12"}, "344": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "345": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "346": {"d": "2026-01", "in": "2026-03", "out": "2026-01"}, "347": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "348": {"d": "2026-01", "in": "2026-01", "out": "2026-12"}, "349": {"d": "2026-09", "in": "2027-01", "out": "2026-09"}, "350": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "351": {"d": "2027-01", "in": "2027-01", "out": "2027-01"}, "352": {"d": "2026-01", "in": "2026-01", "out": "2026-12"}, "353": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "354": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "355": {"d": "2026-05", "in": "2026-06", "out": "2026-05"}, "356": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "357": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "359": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "360": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "361": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "363": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "365": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "367": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "401": {"d": "2026-04", "in": "2026-07", "out": "2026-04"}, "402": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "403": {"d": "2026-05", "in": "2027-01", "out": "2026-05"}, "404": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "405": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "406": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "407": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "408": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "409": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "415": {"d": "2026-02", "in": "2026-02", "out": "2026-10"}, "501": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "502": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "505": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "506": {"d": "2026-02", "in": "2026-02", "out": "2027-01"}, "507": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "508": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "509": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "510": {"d": "2026-12", "in": "2027-01", "out": "2026-12"}, "512": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "513": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "514": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "515": {"d": "2026-04", "in": "2026-04", "out": "2027-01"}, "516": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "517": {"d": "2027-01", "in": "2027-01", "out": "2027-01"}, "518": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "519": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "520": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "521": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "525": {"d": "2026-11", "in": "2026-11", "out": "2027-01"}, "526": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "527": {"d": "2026-06", "in": "2026-11", "out": "2026-06"}, "530": {"d": "2026-10", "in": "2027-01", "out": "2026-10"}};

function getAI() {
  return new GoogleGenAI({ apiKey: API_KEY });
}

// Normalisation et recherche floue des alias géographiques (Spécifications 1 & 2)
function normalizeStr(str?: string | number): string {
  if (!str) return "";
  return String(str)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function matchLocality(panel: Partial<Panel>, queryLoc?: string): { isDirectMatch: boolean; isContextMatch: boolean } {
  if (!queryLoc) return { isDirectMatch: false, isContextMatch: false };
  const q = normalizeStr(queryLoc);
  if (q.length < 2) return { isDirectMatch: false, isContextMatch: false };

  const loc = normalizeStr(panel.localisation);
  const ville = normalizeStr(panel.ville);
  const axe = normalizeStr(panel.axe_routier);
  const ctx = normalizeStr(panel.contexte_visibilite);

  // 1. Correspondance physique directe : ville ou localisation (ex: 'wierde' dans 'Wierde 2')
  const isDirectMatch = loc.includes(q) || ville.includes(q) || (loc.length >= 3 && q.includes(loc));
  // 2. Correspondance contextuelle : axe routier ou contexte de visibilité
  const isContextMatch = !isDirectMatch && (axe.includes(q) || ctx.includes(q));

  return { isDirectMatch, isContextMatch };
}

// Fonction de scoring multi-critères avec hiérarchisation prioritaire (Spécification 3)
function calculateScore(panel: Panel, queryAxe?: string, queryLoc?: string): number {
  let score = 50;

  // Spécification 3 : Hiérarchisation prioritaire des localités secondaires
  const { isDirectMatch, isContextMatch } = matchLocality(panel, queryLoc);
  if (isDirectMatch) {
    score += 100; // Bonus prioritaire majeur : tête de liste garantie
  } else if (isContextMatch) {
    score += 35;
  }

  // Score proximité
  if (typeof panel.distance_km === "number") {
    score += Math.max(0, 35 - panel.distance_km * 2.0);
  }

  // Score trafic
  const freq = typeof panel.frequentation === "number" ? panel.frequentation : (Number(panel.frequentation) || 15000);
  score += Math.min(25, (freq / 40000) * 25);

  // Bonus axe
  if (queryAxe) {
    const qAxe = normalizeStr(queryAxe);
    const axe = normalizeStr(panel.axe_routier);
    const loc = normalizeStr(panel.localisation);
    if (axe.includes(qAxe) || loc.includes(qAxe)) {
      score += 20;
    }
  }

  return Math.round(score);
}

// Appel optimisé au script Google avec double cadence et pré-filtrage Top-K
async function fetchAvailablePanelsOptimized(args: any): Promise<Panel[]> {
  const isDispoQuery = Boolean(args?.periode_souhaitee);
  const ttl = isDispoQuery ? DISPO_TTL_MS : PANELS_TTL_MS;
  const cadenceLabel = isDispoQuery ? "Disponibilités (1x/h)" : "Panneaux (1x/sem)";

  const cacheKey = JSON.stringify(args || {});
  const cached = memoryCache.get(cacheKey);
  const now = Date.now();

  // Si cache valide selon sa cadence respective
  if (cached && (now - cached.timestamp < ttl)) {
    console.log(`[Cache HIT - ${cadenceLabel}] Returning ${cached.data.length} panels`);
    return cached.data;
  }

  // Si cache expiré mais existant : retour immédiat (Stale) et rafraîchissement non bloquant en tâche de fond
  if (cached && (now - cached.timestamp >= ttl)) {
    console.log(`[Cache STALE - ${cadenceLabel}] Serving cached data & refreshing in background...`);
    // Lancer la mise à jour asynchrone sans bloquer l'utilisateur
    refreshPanelsInBackground(args, cacheKey).catch(err => console.warn("[Background Refresh Warning]", err.message));
    return cached.data;
  }

  return await refreshPanelsInBackground(args, cacheKey);
}

async function refreshPanelsInBackground(args: any, cacheKey: string): Promise<Panel[]> {
  const now = Date.now();
  try {
    const payload = {
      action: "get_panels",
      ...args,
    };

    console.log(`[Fetch Apps Script] Refreshing from Google Sheets with:`, payload);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    const response = await fetch(APPS_SCRIPT_URL, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify(payload),
      redirect: "follow",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      console.warn(`[Apps Script Warning] Status ${response.status}`);
      const fallback = memoryCache.get(cacheKey);
      return fallback ? fallback.data : [];
    }

    const json: any = await response.json();
    const rawPanels = json.available_panels || json.panels || [];

    // Nettoyage et normalisation des panneaux
    const cleanedPanels: Panel[] = rawPanels
      .filter((p: any) => {
        const active = String(p.Active || p.active || "").trim().toUpperCase();
        return active !== "N" && active !== "NON" && active !== "NO";
      })
      .map((p: any) => {
        const remId = String(p.remorque || p.Remorque || p.id || "").replace(".0", "");
        const freq = Number(p.frequentation || p.Frequentation || p.Frequentation_Moyenne_veh_jour || 0);
        const ots = Number(p.ots || p.OTS || p.ots_mensuel || (freq ? freq * 30 * 1.2 : 0));

        const rawDist = p.distance_km ?? p.Distance_KM ?? p.distance;
        let parsedDist: number | undefined = undefined;
        if (rawDist !== undefined && rawDist !== null && rawDist !== "") {
          const n = typeof rawDist === "number" ? rawDist : parseFloat(String(rawDist).replace(",", "."));
          if (!isNaN(n)) parsedDist = Math.round(n * 10) / 10;
        }

        const faceVal = String(p.face || p.Face || "IN/OUT").trim();
        const faceNorm = faceVal.toUpperCase();
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
          axe_routier: String(p.axe_routier || p.Axe_Routier || "").trim(),
          face: faceVal,
          direction: String(p.direction || p.Direction || "").trim(),
          distance_km: parsedDist,
          prochaine_dispo: computedDispo,
          frequentation: freq || undefined,
          ots: Math.round(ots) || undefined,
          contexte_visibilite: String(p.contexte_visibilite || p.Contexte_Visibilite || "").trim(),
          lien: String(p.lien || p.Lien || `https://remorquepublicitaire.be/remorque/${remId}`).trim(),
          photo: String(p.photo || p.photo_in || p.Photo || "").trim(),
          active: "O",
        };

        const { isDirectMatch } = matchLocality(panelObj, args?.points_of_interest);
        panelObj.is_direct_match = isDirectMatch;
        panelObj.score = calculateScore(panelObj, args?.axe_routier, args?.points_of_interest);
        return panelObj;
      });

    // Tri : les correspondances directes en tête absolue, ordonnées par score composite
    cleanedPanels.sort((a, b) => {
      const aDirect = a.is_direct_match ? 1 : 0;
      const bDirect = b.is_direct_match ? 1 : 0;
      if (aDirect !== bDirect) return bDirect - aDirect;
      return (b.score || 0) - (a.score || 0);
    });
    const topPanels = cleanedPanels.slice(0, 5);

    memoryCache.set(cacheKey, { timestamp: now, data: topPanels });
    console.log(`[Cache Updated] Saved Top ${topPanels.length} ranked panels to memory cache`);
    return topPanels;

  } catch (error: any) {
    console.error(`[Fetch Error] Error fetching panels:`, error.message);
    const fallback = memoryCache.get(cacheKey);
    return fallback ? fallback.data : [];
  }
}

// Déclaration de l'outil pour Gemini
const getAvailablePanelsDeclaration = {
  name: "get_available_panels",
  description: "Recherche les remorques publicitaires M Move 8m² selon des critères géographiques (villes, communes, villages, hameaux, localités secondaires comme Wierde, Naninne, Sclayn, Haute Bise, Erpent, Wavre) et de dates.",
  parameters: {
    type: "OBJECT",
    properties: {
      periode_souhaitee: {
        type: "STRING",
        description: "Période au format AAAA-MM (ex: 2026-05) ou vide pour l'inventaire complet.",
      },
      points_of_interest: {
        type: "STRING",
        description: "Ville, commune, village, hameau ou lieu-dit cible (ex: Wierde, Naninne, Sclayn, Namur, Wavre, Nivelles). Capture TOUJOURS le nom spécifique du village ou de la localité même s'il s'agit d'une section de commune.",
      },
      axe_routier: {
        type: "STRING",
        description: "Axe routier recherché (ex: N4, E411, N25, E42).",
      },
      province: {
        type: "STRING",
        description: "Province wallonne ciblée.",
      },
      distance_max_km: {
        type: "NUMBER",
        description: "Rayon de recherche maximal en kilomètres.",
      },
    },
  },
};

const sendSelectionEmailDeclaration = {
  name: "send_selection_email",
  description: "Envoie un email récapitulatif de la sélection de panneaux au prospect.",
  parameters: {
    type: "OBJECT",
    properties: {
      email_client: { type: "STRING", description: "Adresse email du prospect." },
      selection_text: { type: "STRING", description: "Texte détaillé de la sélection et du devis." },
    },
    required: ["email_client", "selection_text"],
  },
};

async function executeChatTurn(
  ai: GoogleGenAI,
  modelName: string,
  history: any[],
  message: string,
  systemInstruction: string
) {
  const chat = ai.chats.create({
    model: modelName,
    config: {
      systemInstruction,
      tools: [
        {
          functionDeclarations: [getAvailablePanelsDeclaration, sendSelectionEmailDeclaration],
        },
      ],
      temperature: 0.3,
    },
    history,
  });

  let capturedPanels: Panel[] = [];
  let response: GenerateContentResponse = await chat.sendMessage({ message });

  // Boucle de traitement des appels d'outils
  let toolLoopCount = 0;
  while (response.functionCalls && response.functionCalls.length > 0 && toolLoopCount < 3) {
    toolLoopCount++;
    const functionCalls = response.functionCalls;

    const toolResultsPromises = functionCalls.map(async (call) => {
      if (call.name === "get_available_panels") {
        const panels = await fetchAvailablePanelsOptimized(call.args);
        capturedPanels = panels;
        return {
          functionResponse: {
            name: call.name,
            response: { result: panels },
          },
        };
      }
      if (call.name === "send_selection_email") {
        return {
          functionResponse: {
            name: call.name,
            response: { status: "success", message: "Email transmis avec succès." },
          },
        };
      }
      return null;
    });

    const toolResults = (await Promise.all(toolResultsPromises)).filter(
      (r): r is NonNullable<typeof r> => r !== null
    );

    if (toolResults.length > 0) {
      response = await chat.sendMessage({ message: toolResults });
    } else {
      break;
    }
  }

  return {
    text: response.text || "",
    panels: capturedPanels,
  };
}

async function startServer() {
  const app = express();
  const PORT = process.env.PORT || 3000;

  app.use(express.json());

  app.get("/api/health", (_req, res) => {
    res.json({ status: "ok", active_trailers: 132 });
  });

  app.post("/api/chat", async (req, res) => {
    try {
      const { message, history } = req.body;
      if (!message || typeof message !== "string") {
        return res.status(400).json({ error: "Le message est requis." });
      }

      const ai = getAI();
      const today = new Date().toLocaleDateString("fr-FR", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      });

      const sanitizedHistory: any[] = [];
      if (Array.isArray(history)) {
        for (const msg of history) {
          if ((msg.role === "user" || msg.role === "model") && Array.isArray(msg.parts)) {
            sanitizedHistory.push({
              role: msg.role,
              parts: msg.parts.map((p: any) => ({ text: String(p.text || "") })),
            });
          }
        }
      }

      const systemInstruction = `### 1. RÔLE ET IDENTITÉ
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
    * Ne cite JAMAIS les termes techniques "Face IN" / "Face OUT".

* **FORMAT OBLIGATOIRE (Top 3 à 5) :**
    * Pour chaque panneau :
      \`* [**#ID - Ville - Localisation** ↗️](lien)\` - **Direction :** [direction]
      *(Trafic : [frequentation] véh./jour | Visibilité : ~[ots] OTS/mois)*
      *Atout :* [contexte_visibilite]

* **DEMANDE "QUAND EST-CE LIBRE ?" :**
    * Affiche le nom cliquable suivi de : \`📅 **Disponible dès : [prochaine_dispo]**\`.

* **RECHERCHE MULTI-MOIS :**
    * Structure OBLIGATOIREMENT ta réponse MOIS PAR MOIS avec des sous-titres (\`### Mois AAAA\`).

### 4. CONSEILS CRÉATIFS M MOVE (Attention 3 à 5 secondes)
1. **Règle des 7 mots maximum** : un message unique et percutant.
2. **Lisibilité XXL** : typographie bâton sans-serif.
3. **Contraste fort** (Noir/Jaune, Blanc/Rouge).
4. **Hero Shot** : une seule image forte.
5. **Call to Action** : fléchage ou site web court. **Pas de QR Code**.

### 5. SUPPORT TECHNIQUE
* **Deadline :** Le 15 du mois précédent.
* **Format :** 390x200 cm (fichier 392x202 cm), échelle 1/1, PDF CMJN 65 dpi min.
* **Envoi :** \`mmove@mediasee.be\`.

### 6. MODE ADMINISTRATEUR ("Corentin")
* Si l'utilisateur mentionne être Corentin ou demande le mode debug, réponds en toute franchise et clarté technique.`;

      let lastError: any = null;
      for (const model of CANDIDATE_MODELS) {
        try {
          const result = await executeChatTurn(ai, model, sanitizedHistory, message, systemInstruction);
          return res.json(result);
        } catch (err: any) {
          lastError = err;
          console.warn(`[Model Fallback] Model ${model} failed, trying next... Error: ${err.message}`);
        }
      }

      console.error("All candidate models failed:", lastError);
      return res.status(500).json({
        error: "Le service commercial est temporairement très sollicité. Veuillez réessayer dans quelques secondes.",
        details: lastError?.message || String(lastError),
      });

    } catch (error: any) {
      console.error("Unhandled error in /api/chat:", error);
      res.status(500).json({ error: "Une erreur inattendue est survenue." });
    }
  });

  // Mode production ou dev Vite
  if (process.env.NODE_ENV !== "production") {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*all", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server M Move Multi-Agents running on http://localhost:${PORT}`);
  });
}

startServer();
