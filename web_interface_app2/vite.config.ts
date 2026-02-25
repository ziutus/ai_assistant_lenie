import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@lenie/shared': path.resolve(__dirname, '../shared'),
      assets: path.resolve(__dirname, 'src/assets'),
      Pages: path.resolve(__dirname, 'src/pages'),
      Slices: path.resolve(__dirname, 'src/Slices'),
      ThemeLayout: path.resolve(__dirname, 'src/ThemeLayout'),
      Common: path.resolve(__dirname, 'src/Common'),
    },
  },
  server: {
    port: 3001,
  },
  build: {
    outDir: 'build',
  },
});
