/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // gray + white are driven by CSS variables so a single class on <html>
        // (.light) flips the entire palette between dark and light themes.
        white: 'rgb(var(--c-white) / <alpha-value>)',
        gray: {
          50: 'rgb(var(--c-gray-50) / <alpha-value>)',
          100: 'rgb(var(--c-gray-100) / <alpha-value>)',
          200: 'rgb(var(--c-gray-200) / <alpha-value>)',
          300: 'rgb(var(--c-gray-300) / <alpha-value>)',
          400: 'rgb(var(--c-gray-400) / <alpha-value>)',
          500: 'rgb(var(--c-gray-500) / <alpha-value>)',
          600: 'rgb(var(--c-gray-600) / <alpha-value>)',
          700: 'rgb(var(--c-gray-700) / <alpha-value>)',
          800: 'rgb(var(--c-gray-800) / <alpha-value>)',
          900: 'rgb(var(--c-gray-900) / <alpha-value>)',
          950: 'rgb(var(--c-gray-950) / <alpha-value>)',
        },
        // The accent is now a CSS variable like the gray ramp, so it can invert per theme:
        // graphite on the white UI, light gray on the dark UI. Both keep `text-gray-950` —
        // the class already paired with accent buttons everywhere — as the readable
        // foreground, so the hundreds of existing `bg-gold-primary text-gray-950` usages
        // stay correct without touching a single component.
        // (The `gold-*` names are kept deliberately: renaming them would touch ~200 call
        // sites across the app for no visual gain and a large regression surface.)
        'gold-primary': 'rgb(var(--c-accent) / <alpha-value>)',
        'gold-dark': 'rgb(var(--c-accent-strong) / <alpha-value>)',
        'wa-green': '#25D366',
      },
      fontFamily: {
        cairo: ['Cairo', 'sans-serif'],
        inter: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
}
