import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral greys in place of Tailwind's blue-tinted slate, so dark mode
        // is a classic dark grey (as Discord's): the page 950, cards 900,
        // fields and hovers 800. Every `slate-*` class takes these. 500 is
        // secondary text on white, 400 on dark: both readable (WCAG AA, 4.5:1)
        // there, 400 on the 800 fields too.
        slate: {
          50: '#f7f7f8',
          100: '#ebedef',
          200: '#dcdee1',
          300: '#c4c9ce',
          400: '#a3a8b0',
          500: '#72767e',
          600: '#5c5f66',
          700: '#4e5058',
          800: '#383a40',
          900: '#2b2d31',
          950: '#1e1f22',
        },
      },
    },
  },
  plugins: [],
} satisfies Config
