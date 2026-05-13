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
  collectCoverage: process.env.JEST_COVERAGE === "1",
  coverageProvider: 'v8',
  coverageThreshold: {
    global: {
      branches: 40,
      functions: 25,
      lines: 40,
      statements: 40,
    },
    "./src/lib/api/": { branches: 10, lines: 40 },
    "./src/hooks/useInvestigation.ts": { branches: 40, lines: 45 },
    "./src/hooks/useSimulation.ts": { branches: 35, lines: 50 },
    "./src/hooks/useResult.ts": { branches: 10, lines: 10 },
    "./src/lib/investigationStorage.ts": { branches: 50, lines: 50 },
  },
  coverageReporters: ["text", "lcov", "html", "json-summary"],
  coverageDirectory: "coverage",
};

export default createJestConfig(config);
