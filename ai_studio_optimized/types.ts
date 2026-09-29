export interface GroundingChunk {
  web?: { uri?: string; title?: string };
  maps?: { uri?: string; title?: string };
}

export interface Panel {
  id: string;
  remorque?: string;
  province?: string;
  axe_routier?: string;
  direction?: string;
  face?: 'IN' | 'OUT' | string;
  adresse?: string;
  ville?: string;
  code_postal?: string;
  localisation?: string;
  lien?: string;
  distance_km?: number;
  prochaine_dispo?: string;
  dispo_in?: string;
  dispo_out?: string;
  status_in?: 'disponible' | 'reserve' | string;
  status_out?: 'disponible' | 'reserve' | string;
  faces_disponibles?: ('IN' | 'OUT' | string)[];
  active?: string;
  frequentation?: string | number;
  ots?: string | number;
  contexte_visibilite?: string;
  photo?: string;
  photo_in?: string;
  photo_out?: string;
  score?: number;
  is_direct_match?: boolean;
}

export interface ChatMessage {
  role: 'user' | 'model';
  parts: { text: string }[];
  panels?: Panel[];
  groundingChunks?: GroundingChunk[];
}
