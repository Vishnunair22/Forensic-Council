/* eslint-disable @typescript-eslint/no-unused-vars */

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

// React 18 does not include the HTML `inert` attribute in its type definitions.
// The attribute is now baseline-available in all modern browsers and is the
// correct way to prevent both keyboard focus and AT access to off-screen content
// (replacing the misuse of aria-hidden on interactive regions).
declare module "react" {
  interface HTMLAttributes<T> {
    inert?: boolean | undefined;
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
