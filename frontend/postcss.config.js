/**
 * Tailwind v4 (decision D6). `@tailwindcss/postcss` replaces the `tailwindcss`
 * PostCSS plugin and bundles its own vendor prefixing via Lightning CSS, so
 * `autoprefixer` is no longer needed here.
 */
module.exports = { plugins: { "@tailwindcss/postcss": {} } };
