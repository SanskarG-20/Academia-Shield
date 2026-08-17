import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  action?: React.ReactNode;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({ 
  children, 
  className = '', 
  title, 
  action,
  noPadding = false
}) => {
  return (
    <div className={`bg-white dark:bg-dark-card border border-slate-200/60 dark:border-slate-700/50 rounded-2xl shadow-soft hover:shadow-lift transition-all duration-300 overflow-hidden ${className}`}>
      {(title || action) && (
        <div className="px-6 py-4 border-b border-slate-100/80 dark:border-slate-700/40 flex justify-between items-center">
          {title && <h3 className="font-semibold text-slate-800 dark:text-white tracking-tight">{title}</h3>}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-6'}>
        {children}
      </div>
    </div>
  );
};
