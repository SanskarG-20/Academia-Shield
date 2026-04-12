import React from 'react';

interface BlurTextProps {
  text: string;
  className?: string;
  delay?: number;
  animateBy?: 'words' | 'letters';
}

export const BlurText: React.FC<BlurTextProps> = ({ 
  text, 
  className = '', 
  delay = 0,
  animateBy = 'letters' 
}) => {
  const elements = animateBy === 'words' ? text.split(' ') : text.split('');
  
  return (
    <span className={`inline-flex flex-wrap ${className}`}>
      <style>
        {`
          @keyframes blur-reveal {
            0% { filter: blur(10px); opacity: 0; transform: translateY(10px); }
            100% { filter: blur(0); opacity: 1; transform: translateY(0); }
          }
        `}
      </style>
      {elements.map((el, i) => (
        <span
          key={i}
          className="inline-block"
          style={{
            animation: `blur-reveal 0.8s cubic-bezier(0.2, 0.65, 0.3, 0.9) forwards`,
            animationDelay: `${delay + i * (animateBy === 'words' ? 0.1 : 0.03)}s`,
            opacity: 0 // Initial state before animation starts
          }}
        >
          {el === ' ' ? '\u00A0' : el}
          {animateBy === 'words' && i < elements.length - 1 ? '\u00A0' : ''}
        </span>
      ))}
    </span>
  );
};