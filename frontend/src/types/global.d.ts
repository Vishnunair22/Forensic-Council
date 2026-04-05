export {};

declare global {
  interface Window {
    webkitAudioContext: typeof AudioContext;
  }

  namespace jest {
    interface Matchers<R> {
      toHaveNoViolations(): R;
    }
  }
}

declare module "jest-axe" {
  export function axe(
    container: Element | DocumentFragment,
    options?: Record<string, unknown>,
  ): Promise<{ violations: unknown[] }>;

  export const toHaveNoViolations: (
    received: unknown,
  ) => {
    message: () => string;
    pass: boolean;
  };
}
