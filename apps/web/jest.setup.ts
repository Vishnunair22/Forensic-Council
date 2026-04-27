import '@testing-library/jest-dom';
import { toHaveNoViolations } from 'jest-axe';

// @ts-ignore
expect.extend(toHaveNoViolations);

// Polyfill missing browser globals for Jest
if (typeof CloseEvent === 'undefined') {
  global.CloseEvent = class CloseEvent extends Event {
    code: number; reason: string; wasClean: boolean;
    constructor(type: string, init?: CloseEventInit) {
      super(type, init);
      this.code = init?.code ?? 0;
      this.reason = init?.reason ?? '';
      this.wasClean = init?.wasClean ?? false;
    }
  } as typeof CloseEvent;
}

// Mock browser APIs when the active Jest environment provides a window.
if (typeof window !== "undefined") {
  window.scrollTo = jest.fn();
  global.scrollTo = jest.fn();

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

// Mock useSound globally to avoid errors during test rendering
jest.mock('@/hooks/useSound', () => ({
  useSound: () => ({
    playSound: jest.fn(),
  }),
}));

// Mock framer-motion — useScroll/useTransform require a real DOM scroll context
jest.mock('framer-motion', () => {
  const React = require('react');
  const stripMotionProps = (props: Record<string, unknown>) => {
    const {
      animate,
      exit,
      initial,
      layout,
      transition,
      variants,
      viewport,
      whileHover,
      whileInView,
      whileTap,
      ...rest
    } = props;
    return rest;
  };
  return {
    motion: new Proxy({}, {
      get: (_: unknown, tag: string) =>
        React.forwardRef(({ children, ...props }: React.HTMLAttributes<HTMLElement>, ref: React.Ref<HTMLElement>) =>
          React.createElement(tag, { ...stripMotionProps(props), ref }, children)
        ),
    }),
    useScroll: () => ({ scrollYProgress: { get: () => 0 } }),
    useTransform: (_: unknown, __: unknown, output: unknown[]) => ({ get: () => output[0] }),
    AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  };
});
