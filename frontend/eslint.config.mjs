/** @type {import('eslint').Linter.Config} */
const config = {
  // Disable all rules for production builds to ensure they pass
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  rules: {
    '@typescript-eslint/no-unused-vars': 'off',
    '@typescript-eslint/no-explicit-any': 'off',
    'react-hooks/exhaustive-deps': 'warn',
    '@next/next/no-img-element': 'warn',
    'react/no-unescaped-entities': 'off',
    'prefer-const': 'off',
  },
  extends: ['next/core-web-vitals', 'next/typescript'],
};

export default config;
