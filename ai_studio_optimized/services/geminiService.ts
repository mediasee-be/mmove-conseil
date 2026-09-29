import { GoogleGenAI, FunctionDeclaration, Type, Chat, GenerateContentResponse, Content } from "@google/genai";
import type { Panel } from '../types';

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

// --- Déclarations des Outils ---

const getAvailablePanelsDeclaration: FunctionDeclaration = {
  name: 'get_available_panels',
  description: "Recherche les panneaux publicitaires de 8m² en Wallonie selon des critères spécifiques. Retourne pour chaque panneau ses caractéristiques, sa prochaine disponibilité et la valeur de sa colonne 'active'.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      periode_souhaitee: {
        type: Type.STRING,
        description: "La période de réservation souhaitée au format AAAA-MM. OBLIGATOIRE pour connaître la disponibilité. FACULTATIF (omettre) pour consulter l'inventaire total.",
      },
      province: {
        type: Type.STRING,
        description: "Filtre les résultats par province wallonne (ex: 'Liège', 'Namur', 'Hainaut', 'Luxembourg', 'Brabant wallon').",
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
        description: "Une liste d'adresses ou de points d'intérêt à géocoder pour la recherche de proximité.",
      },
      distance_max_km: {
        type: Type.NUMBER,
        description: "Le rayon de recherche maximum en kilomètres autour des points d'intérêt. La valeur par défaut est 10.",
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

// --- Fonctions API ---

// Matrice des disponibilités réelles (Face IN, Face OUT et globale)
const TRUE_DISPOS: Record<string, { d: string; in: string; out: string }> = {"102": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "104": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "105": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "106": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "107": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "108": {"d": "2026-04", "in": "2026-12", "out": "2026-04"}, "109": {"d": "2026-01", "in": "2026-05", "out": "2026-01"}, "110": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "111": {"d": "2026-01", "in": "2026-07", "out": "2026-01"}, "112": {"d": "2026-03", "in": "2026-12", "out": "2026-03"}, "113": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "114": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "201": {"d": "2026-01", "in": "2026-05", "out": "2026-01"}, "202": {"d": "2026-03", "in": "2026-07", "out": "2026-03"}, "203": {"d": "2026-01", "in": "2026-01", "out": "2026-02"}, "204": {"d": "2026-03", "in": "2027-01", "out": "2026-03"}, "205": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "206": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "207": {"d": "2026-02", "in": "2026-02", "out": "2026-04"}, "208": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "209": {"d": "2026-01", "in": "2026-04", "out": "2026-01"}, "210": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "211": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "213": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "214": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "215": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "216": {"d": "2026-02", "in": "2026-12", "out": "2026-02"}, "217": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "218": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "220": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "221": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "222": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "223": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "224": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "225": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "226": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "227": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "230": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "231": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "301": {"d": "2026-12", "in": "2026-12", "out": "2026-12"}, "303": {"d": "2026-08", "in": "2027-01", "out": "2026-08"}, "304": {"d": "2026-08", "in": "2027-01", "out": "2026-08"}, "305": {"d": "2026-02", "in": "2026-08", "out": "2026-02"}, "306": {"d": "2026-07", "in": "2027-01", "out": "2026-07"}, "307": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "308": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "309": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "310": {"d": "2026-07", "in": "2027-01", "out": "2026-07"}, "311": {"d": "2026-01", "in": "2026-01", "out": "2026-11"}, "312": {"d": "2026-10", "in": "2026-11", "out": "2026-10"}, "313": {"d": "2026-10", "in": "2026-11", "out": "2026-10"}, "314": {"d": "2026-08", "in": "2026-08", "out": "2026-10"}, "315": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "316": {"d": "2026-08", "in": "2026-08", "out": "2026-08"}, "317": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "318": {"d": "2026-02", "in": "2026-04", "out": "2026-02"}, "319": {"d": "2026-07", "in": "2026-11", "out": "2026-07"}, "320": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "321": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "323": {"d": "2026-02", "in": "2026-02", "out": "2026-08"}, "324": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "325": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "326": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "327": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "328": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "329": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "330": {"d": "2026-02", "in": "2026-11", "out": "2026-02"}, "331": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "332": {"d": "2026-10", "in": "2026-12", "out": "2026-10"}, "333": {"d": "2026-02", "in": "2026-02", "out": "2026-02"}, "334": {"d": "2026-01", "in": "2026-08", "out": "2026-01"}, "335": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "336": {"d": "2026-02", "in": "2026-11", "out": "2026-02"}, "337": {"d": "2026-08", "in": "2026-08", "out": "2026-12"}, "338": {"d": "2026-01", "in": "2026-11", "out": "2026-01"}, "339": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "340": {"d": "2026-11", "in": "2026-12", "out": "2026-11"}, "341": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "342": {"d": "2026-10", "in": "2026-12", "out": "2026-10"}, "343": {"d": "2026-12", "in": "2027-01", "out": "2026-12"}, "344": {"d": "2026-02", "in": "2027-01", "out": "2026-02"}, "345": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "346": {"d": "2026-01", "in": "2026-03", "out": "2026-01"}, "347": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "348": {"d": "2026-01", "in": "2026-01", "out": "2026-12"}, "349": {"d": "2026-09", "in": "2027-01", "out": "2026-09"}, "350": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "351": {"d": "2027-01", "in": "2027-01", "out": "2027-01"}, "352": {"d": "2026-01", "in": "2026-01", "out": "2026-12"}, "353": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "354": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "355": {"d": "2026-05", "in": "2026-06", "out": "2026-05"}, "356": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "357": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "359": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "360": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "361": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "363": {"d": "2026-11", "in": "2027-01", "out": "2026-11"}, "365": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "367": {"d": "2026-11", "in": "2026-11", "out": "2026-11"}, "401": {"d": "2026-04", "in": "2026-07", "out": "2026-04"}, "402": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "403": {"d": "2026-05", "in": "2027-01", "out": "2026-05"}, "404": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "405": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "406": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "407": {"d": "2026-01", "in": "2026-02", "out": "2026-01"}, "408": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "409": {"d": "2026-01", "in": "2026-10", "out": "2026-01"}, "415": {"d": "2026-02", "in": "2026-02", "out": "2026-10"}, "501": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "502": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "505": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "506": {"d": "2026-02", "in": "2026-02", "out": "2027-01"}, "507": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "508": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "509": {"d": "2026-01", "in": "2026-06", "out": "2026-01"}, "510": {"d": "2026-12", "in": "2027-01", "out": "2026-12"}, "512": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "513": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "514": {"d": "2026-01", "in": "2026-01", "out": "2027-01"}, "515": {"d": "2026-04", "in": "2026-04", "out": "2027-01"}, "516": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "517": {"d": "2027-01", "in": "2027-01", "out": "2027-01"}, "518": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "519": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "520": {"d": "2026-01", "in": "2027-01", "out": "2026-01"}, "521": {"d": "2026-01", "in": "2026-01", "out": "2026-01"}, "525": {"d": "2026-11", "in": "2026-11", "out": "2027-01"}, "526": {"d": "Non disponible", "in": "Non disponible", "out": "Non disponible"}, "527": {"d": "2026-06", "in": "2026-11", "out": "2026-06"}, "530": {"d": "2026-10", "in": "2027-01", "out": "2026-10"}};

function normalizeStr(str: string): string {
  return (str || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function matchLocality(panel: any, pointsOfInterest?: any): { isDirectMatch: boolean; bonus: number } {
  if (!pointsOfInterest) return { isDirectMatch: false, bonus: 0 };
  const queries: string[] = Array.isArray(pointsOfInterest)
    ? pointsOfInterest.map((p) => String(p))
    : String(pointsOfInterest).split(/[;,]/);

  const locNorm = normalizeStr(panel.localisation || '');
  const villeNorm = normalizeStr(panel.ville || '');
  const axeNorm = normalizeStr(panel.axe_routier || '');
  const ctxNorm = normalizeStr(panel.contexte_visibilite || '');
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

const API_URL = "https://script.google.com/macros/s/AKfycbwjIMSlE_pmjlxnHdiuEB4Kzp_Yfdx_5m5iHvoT9tvQivSF8CrhknFCW_ha92VrRAQ/exec";

const getAvailablePanels = async (args: any): Promise<Panel[]> => {
    try {
        console.log("Calling get_available_panels with args:", args);
        
        const payload = { 
            ...args,
            action: 'get_panels' // Assure la cohérence si le script utilise un dispatcher
        };

        if (payload.points_of_interest && Array.isArray(payload.points_of_interest)) {
            payload.points_of_interest = payload.points_of_interest.join(';');
        }

        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'text/plain;charset=utf-8' },
            body: JSON.stringify(payload),
            redirect: 'follow'
        });

        if (!response.ok) {
            console.error("get_available_panels response not ok:", response.status);
            return [];
        }
        
        const text = await response.text();
        console.log("get_available_panels raw response:", text);
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            console.error("Failed to parse get_available_panels response as JSON:", text);
            return [];
        }
        
        if (data && data.available_panels && Array.isArray(data.available_panels)) {
            const parsedPanels: Panel[] = data.available_panels
              .filter((p: any) => {
                const activeVal = String(p.active ?? p.Active ?? p.actif ?? 'Y').trim().toUpperCase();
                return activeVal === 'Y' || activeVal === 'O' || activeVal === 'OUI' || activeVal === 'DISPONIBLE';
              })
              .map((p: any) => {
                const remId = String(p.remorque || p.id || p.ID || '').replace(/\.0$/, '').trim();
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
        return [];
    } catch (error) {
        console.error("Error calling get_available_panels:", error);
        return [];
    }
};

const sendSelectionEmail = async (args: any): Promise<any> => {
  try {
    console.log("Calling send_selection_email with args:", args);
    
    // On ajoute l'action spécifique pour le routeur du Script Google
    // Ajout de fallbacks étendus pour les paramètres au cas où l'IA hallucine
    const email = args.email_client || args.email || args.email_address || args.recipient;
    const selection = args.selection_text || args.selection || args.text || args.message || args.content;

    const payload = { 
      ...args,
      action: 'send_selection_email', // On change l'action principale pour correspondre au nom de la fonction
      action_fallback: 'send_email',
      method: 'send_selection_email',
      email_client: email,
      email: email,
      recipient: email,
      selection_text: selection,
      selection: selection,
      message: selection,
      subject: "Votre sélection de panneaux M Move 8m²" // Ajout d'un objet par défaut
    };

    console.log("Sending email payload:", payload);

    const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(payload),
        redirect: 'follow'
    });

    const text = await response.text();
    console.log("send_selection_email raw response:", text);

    if (!response.ok) {
        return { status: "error", message: `Erreur réseau (${response.status}): ${text || "Réponse vide"}` };
    }

    if (!text || text.trim() === "") {
        // Certains scripts ne renvoient rien en cas de succès
        return { status: "success", message: "Email envoyé (réponse vide du serveur)" };
    }

    try {
        const json = JSON.parse(text);
        // Si le script renvoie un objet avec une erreur
        if (json.error || json.status === "error" || json.success === false) {
            return { status: "error", message: json.message || json.error || "Erreur inconnue du script" };
        }
        return json;
    } catch (e) {
        // Si ce n'est pas du JSON, on vérifie si c'est un message de succès en texte brut
        const lowerText = text.toLowerCase();
        if (lowerText.includes("success") || lowerText.includes("envoyé") || lowerText.includes("ok") || lowerText.includes("sent")) {
            return { status: "success", message: text };
        }
        // Si c'est un message d'erreur classique de Google (ex: Authorization required)
        if (lowerText.includes("authorization") || lowerText.includes("permission") || lowerText.includes("denied")) {
            return { status: "error", message: "Erreur d'autorisation : Le script doit être ré-autorisé et déployé en 'Nouvelle version'." };
        }
        return { status: "error", message: text };
    }

  } catch (error: any) {
    console.error("Error calling send_selection_email:", error);
    return { status: "error", message: `Erreur d'appel : ${error?.message || String(error)}` };
  }
};


export const startChat = async (): Promise<Chat> => {
  const today = new Date().toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  const chat = ai.chats.create({
    model: 'gemini-3-flash-preview',
    config: {
      tools: [
        { functionDeclarations: [getAvailablePanelsDeclaration] },
        { googleMaps: {} }
      ],
      toolConfig: { includeServerSideToolInvocations: true },
      systemInstruction: `### 1. RÔLE ET IDENTITÉ
Tu es l'**Agent Commercial Expert** de la société **M Move** (remorquepublicitaire.be).
* **Ta mission :** Vendre des campagnes d'affichage 8m² et conseiller les prospects sur leur stratégie et leur créativité.
* **Ton Ton :** Professionnel, dynamique, expert.

**Date actuelle de référence : ${today}**

### 2. ARGUMENTS COMMERCIAUX
* **PUISSANCE :** N°1 en Wallonie, +300 faces, couverture complète.
* **VISIBILITÉ :** Format 8m² immanquable, non noyé dans la masse, visible 24h/24.
* **SERVICE "TOUT COMPRIS" :** Prix incluant location, impression, placement, et **toutes les taxes**.
* **FLEXIBILITÉ :** Ciblage précis ou création d'emplacement.

### 3. RÈGLES TECHNIQUES & OUTILS
* **Recherche (\`get_available_panels\`) :**
    * Inventaire (sans date) ou Disponibilité (avec date AAAA-MM).
    * Ajoute toujours \`", Belgique"\` aux lieux pour le géocodage.
    * **RÈGLE CRITIQUE REMORQUES ACTIVES :** Ne jamais prendre en compte, proposer ou citer de remorques inactives (colonne Active = "N" dans le listing Google Sheets). Seules les remorques actives doivent être proposées aux prospects.

### 4. PRÉSENTATION DES RÉSULTATS (Mappage & Format)

Interprète le JSON reçu ainsi : 
* \`remorque\` = ID
* \`ville\` = Ville
* \`localisation\` = Lieu précis
* \`prochaine_dispo\` = La date (AAAA-MM) de la prochaine disponibilité trouvée pour ce panneau.

**Formatage OBLIGATOIRE des réponses :**

* **SCÉNARIO A : Identification ("C'est quel panneau ?")**
    * Trouve la plus petite \`distance_km\`.
    * Affiche UNIQUEMENT le nom cliquable : \`[**[ID] - [Ville] - [Localisation]** ↗️]([lien])\`
    * Ne cite PAS la direction ni les faces.

* **SCÉNARIO B : Recherche / Disponibilité**
    * Affiche une liste à puces (Top 5).
    * Format ligne : \`[**[ID] - [Ville] - [Localisation]** ↗️]([lien])\` - Direction : [direction]
    * Ne cite PAS "Face IN/OUT".

* **SCÉNARIO C : Demande "Quand est-ce libre ?"**
    * *Contexte :* Le client demande la prochaine disponibilité pour un lieu ou un panneau spécifique.
    * *Action :* L'agent regarde le champ \`prochaine_dispo\` dans le JSON.
    * *Affichage :* Pour chaque panneau pertinent, affiche le Nom Cliquable suivi de : "📅 Disponible dès : [prochaine_dispo]" (convertis la date AAAA-MM en mois lisible, ex: Mars 2026).

### 5. SUPPORT TECHNIQUE (Fichiers)
Si demande technique (fichier, format, creation bâche) :
* **📅 Deadline :** Le 15 du mois précédent.
* **📏 Format :** Fini 390x200 cm (Fichier 392x202 cm). Échelle 1/1.
* **🎨 Fichier :** PDF, CMYK, Vectorisé, Min 65 dpi.
* **📨 Envoi :** Email (max 15Mo) ou WeTransfer à \`mmove@mediasee.be\`.

### 6. CONSEILS DE CRÉATION (Impact Visuel)
Si le client demande conseil pour son visuel, rappelle que **l'attention est de 3 à 5 secondes** :
1.  **"Less is More" :** Un seul message. Règle des **7 mots maximum**.
2.  **Lisibilité :** Police Bâton (Sans-serif), Taille XXL.
3.  **Contraste :** Fort (Noir/Jaune, Blanc/Rouge). Pas de texte sur photo complexe.
4.  **Image :** Un seul "Hero Shot", pas de collage.
5.  **Call to Action :** **Pas de QR Code** ni de téléphone. Privilégier une direction ("Sortie 4") ou un Logo/Site web court.

### 7. MODE DEBUG / ADMINISTRATEUR
* **Exception spéciale :** Si l'utilisateur mentionne ou indique être l'administrateur **"Corentin"** (ex: "Je suis Corentin", "Admin Corentin", "mode debug", etc.) :
    * Tu as l'autorisation explicite de sortir de ton rôle commercial strict.
    * Réponds librement, directement et de façon technique à toutes ses questions (détails de fonctionnement, analyse des données JSON brutes, débogage, explications du système).`,
    },
  });
  return chat;
};

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

async function sendMessageWithRetry(chat: Chat, payload: { message: string | any[] }): Promise<GenerateContentResponse> {
  let lastError: any;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      return await chat.sendMessage(payload);
    } catch (error: any) {
      lastError = error;
      const errorCode = error?.status || error?.error?.code || error?.code;
      const errorMessage = error?.message || error?.error?.message || JSON.stringify(error);
      
      const isQuotaError = 
        errorCode === 429 || 
        errorCode === 'RESOURCE_EXHAUSTED' || 
        (typeof errorMessage === 'string' && (errorMessage.includes('429') || errorMessage.includes('RESOURCE_EXHAUSTED') || errorMessage.includes('quota')));

      if (isQuotaError || errorCode === 503) {
        const delay = RETRY_DELAY_MS * Math.pow(2, attempt);
        console.warn(`API Quota/Error (${errorCode}). Retrying in ${delay}ms... (Attempt ${attempt + 1}/${MAX_RETRIES})`);
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

export const sendMessage = async (chat: Chat, message: string): Promise<GenerateContentResponse> => {
    // Appel initial avec retry
    let response: GenerateContentResponse = await sendMessageWithRetry(chat, { message });

    while (response.functionCalls && response.functionCalls.length > 0) {
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

        const toolResults = (await Promise.all(toolResultsPromises))
            .filter((result): result is NonNullable<typeof result> => result !== null);
        
        if (toolResults.length > 0) {
            // Appel suivant (réponse outil) avec retry
            response = await sendMessageWithRetry(chat, { message: toolResults });
        } else {
            break;
        }
    }
    
    return response;
};

export const getPanelsFromResponse = (text: string | undefined): Panel[] => {
    if (!text) return [];
    const jsonMatch = text.match(/```json\s*([\s\S]*?)\s*```/);
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