import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**", "dist/**"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_", "varsIgnorePattern": "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-non-null-assertion": "error",
      "react-hooks/exhaustive-deps": "error",
      "@next/next/no-img-element": "error",
      "react/no-unescaped-entities": "warn",
      "prefer-const": "error",
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/aria-props": "error",
      "jsx-a11y/role-has-required-aria-props": "error",
      "jsx-a11y/interactive-supports-focus": "warn",

      // ── Design System Enforcement (FRONTEND_DESIGN_SYSTEM.md §2.1) ──────────
      // These rules convert the design doc's enforcement claims from aspirational
      // to actual. They lint className Literal values in JSX.
      "no-restricted-syntax": [
        "warn",
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/\\b(hover:scale-|group-hover:scale-|active:scale-)/]",
          message: "[DS] Scale transforms are banned. Use hover:border-primary/40 for interactive feedback instead.",
        },
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/\\bbackdrop-blur-(sm|md|lg|xl|2xl|3xl|\\[)/]",
          message: "[DS] Inline backdrop-blur-* is banned. Use fc-surface-* CSS classes (which already set backdrop-filter) instead.",
        },
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/\\bbg-black\\/(4|5|6|7|8|9)[0-9]\\b/]",
          message: "[DS] bg-black/X is banned. Use fc-surface-quiet, fc-surface-solid, or bg-surface-* tokens instead.",
        },
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/\\btext-white\\/([1-4][0-9]|5[0-4]|[1-9])\\b/]",
          message: "[DS] text-white/X opacity classes are banned. Use fc-text-primary, fc-text-secondary, fc-text-muted, or fc-text-faint.",
        },
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/\\btext-\\[1[013]px\\]/]",
          message: "[DS] Micro font sizes text-[10px], text-[11px], text-[13px] are banned. Use the fc-eyebrow or text-xs/text-sm scale.",
        },
        {
          selector: "Property[key.name='textShadow'][value.type='Literal'][value.value=/rgba\\((?!0,\\s*0,\\s*0)/]",
          message: "[DS] Colored neon text-shadow (textShadow with non-black rgba) is banned. All shadows must use rgba(0,0,0,X).",
        },
        {
          selector: "Property[key.name='boxShadow'][value.type='Literal'][value.value=/rgba\\((?!0,\\s*0,\\s*0)/]",
          message: "[DS] Colored neon box-shadow is banned. All shadows must use rgba(0,0,0,X). Use border-color for accent emphasis.",
        },
      ],
    },
  },
];

export default eslintConfig;
