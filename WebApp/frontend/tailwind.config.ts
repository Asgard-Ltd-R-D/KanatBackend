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
        // Brand accent, re-hued from Tailwind's generic blue to a deliberate
        // steel-blue: deeper and more desaturated, reading as a precision
        // instrument rather than a SaaS default. The darkest shade matches the
        // range-report masthead (#13283f), so the app and its PDFs are one system.
        // Every existing `blue-*` class takes these.
        blue: {
          50: '#eef3fb',
          100: '#dae5f4',
          200: '#bacbe8',
          300: '#8fa9d5',
          400: '#5f81bd',
          500: '#3f63a6',
          600: '#34538f',
          700: '#2b4475',
          800: '#243a60',
          900: '#13283f',
          950: '#0d1b2c',
        },
      },
      boxShadow: {
        // A crisp, low, cool-tinted elevation — not the generic soft grey blur
        card: '0 1px 2px rgba(19,40,63,0.06), 0 1px 1px rgba(19,40,63,0.04)',
      },
    },
  },
  plugins: [],
} satisfies Config
