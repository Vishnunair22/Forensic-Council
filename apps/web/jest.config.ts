import type { Config } from 'jest';
import nextJest from 'next/jest.js';

const createJestConfig = nextJest({
  dir: './',
});

const config: Config = {
  testEnvironment: 'jest-environment-jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  roots: ['<rootDir>/src', '<rootDir>/tests'],
  moduleDirectories: ['node_modules', '<rootDir>/node_modules'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  // testMatch covers src/ and tests/ (including tests/accessibility/**) via roots above.
  // Explicit pattern ensures jest-axe unit specs are always picked up. (P2-A11Y-001 fix, audit v6→v7)
  testMatch: [
    '**/*.test.ts',
    '**/*.test.tsx',
  ],
  // Ignore the standalone Next.js bundle to avoid Jest haste map
  // collisions on the app's package name.
  modulePathIgnorePatterns: ['<rootDir>/.next/standalone'],
  collectCoverage: true,
  coverageProvider: 'v8',
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 50,
      lines: 60,
      statements: 60,
    },
    "./src/lib/api/": { branches: 45, lines: 75 },
    "./src/hooks/useInvestigation.ts": { branches: 45, lines: 70 },
    "./src/hooks/useSimulation.ts": { branches: 45, lines: 70 },
    "./src/hooks/useResult.ts": { branches: 45, lines: 70 },
    "./src/lib/investigationStorage.ts": { branches: 70, lines: 85 },
  },
  coverageReporters: ["text", "lcov", "html", "json-summary"],
  coverageDirectory: "coverage",
};

export default createJestConfig(config);
