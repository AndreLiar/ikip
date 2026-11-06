// Flat ESLint config (ESLint 9). Minimal root baseline; apps extend it with
// framework plugins (e.g. Next.js in apps/web) when their code lands.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['**/node_modules/**', '**/.next/**', '**/dist/**', '**/out/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
