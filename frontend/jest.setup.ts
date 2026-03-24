import '@testing-library/jest-dom';
import React from 'react';

// Mock window.scrollTo since JSDOM doesn't implement it
window.scrollTo = jest.fn();
global.scrollTo = jest.fn();

// Mock useSound globally to avoid errors during test rendering
jest.mock('@/hooks/useSound', () => ({
  useSound: () => ({
    playSound: jest.fn(),
  }),
}));

// Mock framer-motion globally to simplify test rendering and avoid layout/animation errors
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: (_target, tag: string) => {
      return ({ children, ...props }: any) => {
        // Strip framer-motion specific props that might cause React warnings on native tags
        const cleanProps = { ...props };
        [
          'whileHover', 'whileTap', 'whileInView', 'initial', 'animate', 'exit', 
          'transition', 'viewport', 'drag', 'layout'
        ].forEach(p => delete cleanProps[p]);
        
        return React.createElement(tag, cleanProps, children);
      };
    },
  }),
  AnimatePresence: ({ children }: any) => children,
  useReducedMotion: () => false,
}));
