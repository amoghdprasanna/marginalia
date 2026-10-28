import '@fontsource-variable/atkinson-hyperlegible-next';
import '@fontsource-variable/atkinson-hyperlegible-mono';
import '@/src/ui/theme.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/src/ui/App';

const root = document.getElementById('root');
if (root === null) throw new Error('Marginalia: the side panel has no #root');
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
