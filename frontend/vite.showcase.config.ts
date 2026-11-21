import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base:'./',
  root:'showcase',
  envDir:'../..',
  plugins:[react()],
  build:{
    outDir:'../../.calisma/web-build',
    emptyOutDir:true,
  },
});
