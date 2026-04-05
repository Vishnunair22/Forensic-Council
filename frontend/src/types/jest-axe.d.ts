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
