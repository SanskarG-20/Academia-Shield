import React, { useEffect } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children, footer }) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div 
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-md transition-opacity" 
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg transform rounded-2xl bg-white dark:bg-dark-card shadow-2xl transition-all flex flex-col max-h-[90vh] animate-scale-in">
        <div className="flex items-center justify-between border-b border-slate-100/80 dark:border-slate-700/40 px-6 py-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-500 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-6 overflow-y-auto">
          {children}
        </div>
        {footer && (
          <div className="border-t border-slate-100/80 dark:border-slate-700/40 bg-slate-50/80 dark:bg-slate-800/30 px-6 py-4 rounded-b-2xl flex justify-end space-x-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
