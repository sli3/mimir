import js from '@eslint/js'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default [
  { ignores: ['dist', 'node_modules', 'coverage'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    settings: {
      react: { version: '18.3' },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,

      // Vite's fast-refresh plugin: warn (not error) if a file exports
      // both components and non-component values, since that pattern
      // breaks fast refresh but is not a correctness bug.
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // React 18 + new JSX transform (Vite's @vitejs/plugin-react) does
      // not require React in scope for JSX.
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',

      // Genuine bug-catchers worth keeping strict rather than relaxed.
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-undef': 'error',
    },
  },
  {
    // Test files: allow Vitest/Testing Library globals (describe, it,
    // expect, vi, etc.) without needing an explicit import in every file.
    files: ['**/tests/**/*.{js,jsx}', '**/*.test.{js,jsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.vitest,
      },
    },
  },
  {
    // @react-three/fiber renders Three.js scene-graph JSX (mesh, group,
    // etc.), whose props (position, args, intensity, transparent,
    // depthWrite, blending...) are legitimate r3f/Three.js properties,
    // not DOM attributes. react/no-unknown-property has no r3f
    // awareness and flags all of these as errors. Disabled for the
    // files that actually use r3f rather than globally, so the rule
    // still catches genuine unknown-DOM-property mistakes everywhere
    // else (e.g. a typo'd HTML attribute in a regular component).
    files: ['**/VectorSpacePage.jsx', '**/*Scene*.jsx', '**/*3d*.jsx'],
    rules: {
      'react/no-unknown-property': 'off',
    },
  },
]