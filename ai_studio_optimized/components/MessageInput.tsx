import React, { useState, useRef, useEffect } from 'react';
import { SendIcon } from './Icons';
import { Sparkles } from 'lucide-react';

interface MessageInputProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
}

const QUICK_SUGGESTIONS = [
  "Magasin de bricolage près de Namur en mai 2026",
  "Concessionnaire auto sur la N4 ou E411",
  "Quand est libre le panneau #114 ?",
  "5 règles d'or pour un visuel percutant 8m²",
];

export const MessageInput: React.FC<MessageInputProps> = ({ onSendMessage, isLoading }) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim());
      setInput('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleSuggestionClick = (promptText: string) => {
    if (isLoading) return;
    onSendMessage(promptText);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  return (
    <div className="p-4 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
      <div className="max-w-4xl mx-auto space-y-2.5">
        {/* Suggestions rapides en 1 clic */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
          <span className="flex items-center gap-1 text-gray-400 shrink-0 mr-1 font-medium">
            <Sparkles className="w-3.5 h-3.5 text-primary-500" />
            Idées :
          </span>
          {QUICK_SUGGESTIONS.map((suggestion, idx) => (
            <button
              key={idx}
              type="button"
              disabled={isLoading}
              onClick={() => handleSuggestionClick(suggestion)}
              className="shrink-0 px-2.5 py-1 rounded-full bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-gray-600 disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>

        {/* Formulaire d'envoi */}
        <form onSubmit={handleSubmit} className="flex items-end space-x-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question (ex: Panneaux disponibles à Wavre en septembre)..."
            disabled={isLoading}
            rows={1}
            className="flex-grow p-3 bg-gray-100 dark:bg-gray-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none disabled:opacity-50 text-gray-900 dark:text-gray-100 placeholder-gray-400"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="p-3 bg-primary-600 hover:bg-primary-500 text-white rounded-xl disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition duration-150 flex-shrink-0 shadow-sm"
            aria-label="Envoyer"
          >
            <SendIcon className="h-5 w-5" />
          </button>
        </form>
      </div>
    </div>
  );
};
