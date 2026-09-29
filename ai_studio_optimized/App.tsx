import React, { useState, useEffect } from 'react';
import type { Chat } from '@google/genai';
import { ChatWindow } from './components/ChatWindow';
import { MessageInput } from './components/MessageInput';
import { startChat, sendMessage, getPanelsFromResponse } from './services/geminiService';
import type { ChatMessage, Panel } from './types';
import { LogoIcon } from './components/Icons';

const App: React.FC = () => {
  const [chatSession, setChatSession] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initChat = async () => {
      try {
        const session = await startChat();
        setChatSession(session);
        setMessages([
          {
            role: 'model',
            parts: [{ 
              text: "Bonjour ! Je suis votre Conseiller Commercial M Move pour l'affichage publicitaire 8m² en Wallonie.\n\nQuelle zone, quel axe routier ou quelle période souhaitez-vous couvrir pour votre prochaine campagne ?" 
            }],
          },
        ]);
      } catch (error) {
        console.error("Failed to initialize chat:", error);
        setMessages([
          {
            role: 'model',
            parts: [{ text: "⚠️ Le service est temporairement indisponible. Veuillez rafraîchir la page dans quelques instants." }],
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    };
    initChat();
  }, []);

  const handleSendMessage = async (userInput: string) => {
    if (!chatSession || userInput.trim() === '') return;

    const userMessage: ChatMessage = { role: 'user', parts: [{ text: userInput }] };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setIsLoading(true);

    try {
      // OPTIMISATION CLÉ 1 : Envoi de l'historique complet pour préserver la mémoire multi-tours
      const response = await sendMessage(chatSession, userInput, updatedMessages);
      
      // OPTIMISATION CLÉ 2 : Récupération prioritaire des panneaux structurés renvoyés par server.ts
      let panels: Panel[] = [];
      if (response && Array.isArray((response as any).panels) && (response as any).panels.length > 0) {
        panels = (response as any).panels;
      } else if (response && response.text) {
        panels = getPanelsFromResponse(response.text);
      }

      const modelMessage: ChatMessage = {
        role: 'model',
        parts: [{ text: response.text || "" }],
        panels: panels.length > 0 ? panels : undefined,
      };

      setMessages(prev => [...prev, modelMessage]);
    } catch (error: any) {
      console.error("Error sending message:", error);
      
      let errorText = "Désolé, une erreur est survenue lors du traitement de votre demande. Veuillez réessayer.";
      const errorMsg = error?.message || error?.error?.message || "";
      if (errorMsg.includes("429") || errorMsg.includes("RESOURCE_EXHAUSTED") || errorMsg.includes("quota")) {
        errorText = "⚠️ **Forte affluence** : Le service commercial est temporairement très sollicité. Veuillez patienter une trentaine de secondes avant de relancer votre recherche.";
      }

      const errorMessageObj: ChatMessage = {
        role: 'model',
        parts: [{ text: errorText }],
      };
      setMessages(prev => [...prev, errorMessageObj]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen font-sans bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <header className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex items-center space-x-3">
          <LogoIcon className="h-8 w-8 text-primary-600" />
          <div>
            <h1 className="text-xl font-bold tracking-tight">M Move - Conseil en Affichage 8m²</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">132 Remorques en Wallonie &middot; Disponibilités en direct</p>
          </div>
        </div>
      </header>
      <ChatWindow messages={messages} isLoading={isLoading} />
      <MessageInput onSendMessage={handleSendMessage} isLoading={isLoading} />
    </div>
  );
};

export default App;
