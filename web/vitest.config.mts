import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(import.meta.url);

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
  ssr: {
    // Prevent Vite from externalizing common Node built-ins used in tests,
    // avoiding the deprecated CommonJS native loader deprecation warning.
    noExternal: ['next', 'react', 'react-dom', 'lucide-react'],
  },
  resolve: {
    alias: {
      // import.meta.dirname is the ESM-native replacement for __dirname
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
    // Include the full standard condition set so Vite/Vitest can resolve
    // packages that publish condition-tagged ESM/CJS entry points without
    // emitting the CommonJS/ESM native loader deprecation warning.
    conditions: ['node', 'import', 'default', 'browser', 'workerd'],
  },
});
