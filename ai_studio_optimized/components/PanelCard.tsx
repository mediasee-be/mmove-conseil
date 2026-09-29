import React from 'react';
import type { Panel } from '../types';
import { PinIcon, RoadIcon, CompassIcon } from './Icons';
import { Car, Eye, Calendar, ExternalLink } from 'lucide-react';

interface PanelCardProps {
  panel: Panel;
}

export const PanelCard: React.FC<PanelCardProps> = ({ panel }) => {
  const panelId = String(panel.id || panel.remorque || "").replace('.0', '');
  const faceColor = panel.face === 'IN' 
    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800' 
    : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 border border-indigo-300 dark:border-indigo-800';

  const hasAddress = panel.adresse || panel.ville || panel.code_postal || panel.localisation;
  const linkUrl = panel.lien || `https://remorquepublicitaire.be/remorque/${panelId}`;

  // Formattage du trafic et de l'OTS
  const formatNumber = (val?: string | number) => {
    if (!val) return null;
    const num = Number(val);
    return isNaN(num) ? String(val) : num.toLocaleString('fr-FR');
  };

  const formattedFreq = formatNumber(panel.frequentation);
  const formattedOts = formatNumber(panel.ots);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden hover:border-primary-500 transition-all text-sm flex flex-col">
      {/* 1. Photo de la remorque 8m² */}
      {panel.photo && (
        <div className="relative w-full h-36 bg-gray-900 overflow-hidden group">
          <img
            src={panel.photo}
            alt={`Remorque #${panelId} - ${panel.ville || ''}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              // Masque l'image si indisponible
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
          {panel.is_direct_match && (
            <div className="absolute top-2 left-2 bg-emerald-600/95 backdrop-blur-sm text-white text-[11px] font-bold px-2 py-0.5 rounded-md shadow flex items-center space-x-1 border border-emerald-400/40">
              <span>🎯 Implantation directe</span>
            </div>
          )}
          <div className="absolute top-2 right-2 bg-black/75 backdrop-blur-sm text-white text-[11px] font-semibold px-2 py-0.5 rounded-full border border-white/20">
            8m² Recto/Verso
          </div>
          {panel.distance_km !== undefined && (
            <div className="absolute bottom-2 left-2 bg-primary-600/90 backdrop-blur-sm text-white text-xs font-semibold px-2 py-0.5 rounded-md shadow">
              📍 à {panel.distance_km} km
            </div>
          )}
        </div>
      )}

      <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
        <div>
          {/* En-tête : ID, Ville et Badge Face */}
          <div className="flex justify-between items-start gap-2 mb-2">
            <div>
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-base text-primary-600 dark:text-primary-400 hover:underline flex items-center space-x-1"
                title="Consulter la fiche technique"
              >
                <span>#{panelId} - {panel.ville || 'Wallonie'}</span>
                <ExternalLink className="h-3.5 w-3.5 ml-1 inline shrink-0" />
              </a>
              {panel.localisation && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{panel.localisation}</p>
              )}
            </div>
            <span className={`px-2 py-0.5 rounded-full text-xs font-bold shrink-0 ${faceColor}`}>
              Face {panel.face || 'IN/OUT'}
            </span>
          </div>

          {/* Axe routier et Direction */}
          <div className="space-y-1.5 text-gray-600 dark:text-gray-300 text-xs">
            {panel.axe_routier && (
              <div className="flex items-center space-x-2">
                <RoadIcon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 shrink-0" />
                <span className="font-semibold text-gray-700 dark:text-gray-200">{panel.axe_routier}</span>
              </div>
            )}
            {panel.direction && (
              <div className="flex items-center space-x-2">
                <CompassIcon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 shrink-0" />
                <span>Direction {panel.direction}</span>
              </div>
            )}
          </div>

          {/* Statistiques d'audience (Trafic & OTS) */}
          {(formattedFreq || formattedOts) && (
            <div className="mt-3 pt-2 border-t border-gray-100 dark:border-gray-700/60 flex items-center gap-3 text-xs">
              {formattedFreq && (
                <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400 font-semibold" title="Fréquentation moyenne">
                  <Car className="h-3.5 w-3.5" />
                  {formattedFreq} véh./j
                </span>
              )}
              {formattedOts && (
                <span className="flex items-center gap-1 text-purple-600 dark:text-purple-400 font-semibold" title="Opportunité de visibilité mensuelle">
                  <Eye className="h-3.5 w-3.5" />
                  {formattedOts} OTS/mois
                </span>
              )}
            </div>
          )}

          {/* Contexte de visibilité */}
          {panel.contexte_visibilite && (
            <div className="mt-2.5 bg-gray-50 dark:bg-gray-700/50 p-2 rounded-lg border border-gray-200/60 dark:border-gray-600/50 text-[11px] text-gray-600 dark:text-gray-300 italic">
              👁️ {panel.contexte_visibilite}
            </div>
          )}
        </div>

        {/* Disponibilités */}
        <div className="pt-2">
          {panel.prochaine_dispo && (
            <div className="bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 text-xs px-2.5 py-1.5 rounded-lg flex items-center justify-between font-medium">
              <span className="flex items-center space-x-1.5">
                <Calendar className="h-3.5 w-3.5 shrink-0" />
                <span>Dispo : <b>{panel.prochaine_dispo}</b></span>
              </span>
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] underline hover:text-emerald-900 dark:hover:text-white"
              >
                Réserver
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
