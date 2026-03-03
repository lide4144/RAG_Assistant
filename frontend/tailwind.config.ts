import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#141923',
        paper: '#f4f1e8',
        accent: '#0d9488',
        accentDark: '#0f766e'
      }
    }
  },
  plugins: []
};

export default config;
