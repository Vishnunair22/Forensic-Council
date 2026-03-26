import '@testing-library/jest-dom';

// Mock window.scrollTo since JSDOM doesn't implement it
window.scrollTo = jest.fn();
global.scrollTo = jest.fn();

// Mock useSound globally to avoid errors during test rendering
jest.mock('@/hooks/useSound', () => ({
  useSound: () => ({
    playSound: jest.fn(),
  }),
}));

// Mock framer-motion — useScroll/useTransform require a real DOM scroll context
jest.mock('framer-motion', () => {
  const React = require('react');
  return {
    motion: new Proxy({}, {
      get: (_: unknown, tag: string) =>
        React.forwardRef(({ children, ...props }: React.HTMLAttributes<HTMLElement>, ref: React.Ref<HTMLElement>) =>
          React.createElement(tag, { ...props, ref }, children)
        ),
    }),
    useScroll: () => ({ scrollYProgress: { get: () => 0 } }),
    useTransform: (_: unknown, __: unknown, output: unknown[]) => ({ get: () => output[0] }),
    AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  };
});
