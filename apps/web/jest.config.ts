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
      branches: 50,
      functions: 50,
      lines: 60,
      statements: 60,
    },
    // Critical modules keep modest branch gates until the E2E suite covers the live stream.
    "./src/lib/api/": { branches: 45, lines: 75 },
  },
  coverageReporters: ["text", "lcov", "html", "json-summary"],
  coverageDirectory: "coverage",
};

export default createJestConfig(config);
