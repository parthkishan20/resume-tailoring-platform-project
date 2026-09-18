/**
 * ESLint configuration.
 *
 * eslintrc format rather than flat config: `eslint-config-next@14` does not
 * ship a flat config, and Next 14's own `next lint` reads eslintrc.
 *
 * `recommended-type-checked` is the baseline, so the linter sees types and can
 * catch the `any` leakage and unawaited promises that this codebase has (D-40,
 * D-60). Relaxations live in `overrides`, scoped to a path, never global.
 */
module.exports = {
  root: true,
  extends: [
    "next/core-web-vitals",
    "plugin:@typescript-eslint/recommended-type-checked",
    "prettier",
  ],
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint"],
  parserOptions: {
    project: "./tsconfig.json",
    tsconfigRootDir: __dirname,
  },
  rules: {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    "@typescript-eslint/consistent-type-imports": [
      "error",
      { prefer: "type-imports", fixStyle: "inline-type-imports" },
    ],
    "@typescript-eslint/no-misused-promises": [
      "error",
      { checksVoidReturn: { attributes: false } },
    ],
    eqeqeq: ["error", "always", { null: "ignore" }],
    "no-console": ["error", { allow: ["warn", "error"] }],
    "prefer-const": "error",
    "no-var": "error",
  },
  overrides: [
    {
      // Build config files are plain JS and are not in tsconfig's include
      // list, so typed linting cannot run on them.
      files: ["*.js", "*.cjs", "*.mjs"],
      extends: ["plugin:@typescript-eslint/disable-type-checked"],
      parserOptions: { project: null },
      env: { node: true },
    },
    {
      // --- LEGACY LAYOUT ---------------------------------------------------
      // `src/components`, `src/lib` and `src/app` are the pre-restructure flat
      // tree. Waves 2 and 3 move them to `src/features/*` and
      // `src/design-system/*`; anything written under those new paths gets the
      // full rule set from its first line.
      //
      // Seven rules are off HERE ONLY. Counts measured 2026-09-18:
      //   no-unsafe-assignment    4   \
      //   no-unsafe-member-access 3    |  D-60: zero runtime validation of any
      //   no-unsafe-argument      2    |  API response. Closed by 2.2 (zod at
      //   no-unsafe-return        0   /   the boundary).
      //   no-unsafe-call          0
      //   no-floating-promises    5      D-40: no AbortController anywhere.
      //                                  Closed by 2.2.
      //   no-unused-vars          1      One dead `Button` import in
      //                                  ResumeListPanel.tsx. Task 0.15.
      files: [
        "src/components/**/*.ts",
        "src/components/**/*.tsx",
        "src/lib/**/*.ts",
        "src/lib/**/*.tsx",
        "src/app/**/*.ts",
        "src/app/**/*.tsx",
      ],
      rules: {
        "@typescript-eslint/no-unsafe-assignment": "off",
        "@typescript-eslint/no-unsafe-member-access": "off",
        "@typescript-eslint/no-unsafe-argument": "off",
        "@typescript-eslint/no-unsafe-return": "off",
        "@typescript-eslint/no-unsafe-call": "off",
        "@typescript-eslint/no-floating-promises": "off",
        "@typescript-eslint/no-unused-vars": "off",
      },
    },
    {
      // Test doubles are deliberately loose about types, and a mock's `async`
      // method usually has nothing to await. Permanent, not debt.
      files: [
        "src/**/__tests__/**/*.ts",
        "src/**/__tests__/**/*.tsx",
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
        "jest.setup.ts",
      ],
      env: { jest: true },
      rules: {
        "@typescript-eslint/no-unsafe-assignment": "off",
        "@typescript-eslint/no-unsafe-member-access": "off",
        "@typescript-eslint/no-unsafe-argument": "off",
        "@typescript-eslint/no-unsafe-return": "off",
        "@typescript-eslint/no-unsafe-call": "off",
        "@typescript-eslint/require-await": "off",
        "@typescript-eslint/unbound-method": "off",
      },
    },
  ],
  ignorePatterns: ["node_modules/", "out/", ".next/", "next-env.d.ts", "*.tsbuildinfo"],
};
