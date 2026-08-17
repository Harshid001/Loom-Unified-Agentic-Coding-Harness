/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        root: '#080A0F',
        sidebar: '#0C0F15',
        surface: '#10141C',
        elevated: '#151A23',
        hover: '#1A202B',
        'border-subtle': '#1E2530',
        'border-default': '#29313D',
        'border-active': '#5140A8',
        brand: {
          DEFAULT: '#7C5CFF',
          hover: '#9175FF',
          soft: 'rgba(124, 92, 255, 0.12)',
        },
        cyan: {
          DEFAULT: '#35D5FF',
        },
        success: {
          DEFAULT: '#35D399',
        },
        warning: {
          DEFAULT: '#F5B83D',
        },
        danger: {
          DEFAULT: '#FF5F6D',
        },
        text: {
          primary: '#F5F7FA',
          secondary: '#A4ADBA',
          muted: '#697383',
        },
      },
      fontFamily: {
        sans: ['Geist', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
