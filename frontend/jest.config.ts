/**
 * Jest Configuration
 * =================
 */

import type { Config } from 'jest';

const config: Config = {
  testEnvironment: 'jsdom',
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: 'tsconfig.json',
      },
    ],
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  setupFilesAfterEnv: ['@testing-library/jest-dom'],
  testMatch: [
    // New location: tests/frontend/**
    '<rootDir>/../tests/frontend/**/*.test.ts',
    '<rootDir>/../tests/frontend/**/*.test.tsx',
    '<rootDir>/../tests/frontend/**/*.spec.ts',
    '<rootDir>/../tests/frontend/**/*.spec.tsx',
    // Legacy fallback: src/__tests__/**
    '**/__tests__/**/*.test.ts',
    '**/__tests__/**/*.test.tsx',
  ],
  roots: ['<rootDir>/src', '<rootDir>/../tests/frontend'],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/index.ts',
    '!src/app/favicon.ico',
  ],
  coverageThreshold: {
    global: {
      statements: 60,
      branches: 50,
      functions: 60,
      lines: 60,
    },
  },
  testTimeout: 15000,
};

export default config;
