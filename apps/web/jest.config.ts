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
      branches: 55,
      functions: 60,
      lines: 75,
      statements: 75,
    },
    // Critical modules require higher coverage
    "./src/lib/api.ts": { branches: 90, lines: 95 },
    "./src/hooks/useInvestigation.ts": { branches: 60, lines: 40 },
    "./src/components/evidence/FileUploadSection.tsx": { branches: 80, lines: 85 },
  },
  coverageReporters: ["text", "lcov", "html", "json-summary"],
  coverageDirectory: "coverage",
};

export default createJestConfig(config);
