/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: '#0b0f19',
        cardBg: 'rgba(17, 24, 39, 0.7)',
        accentColor: '#4f46e5', // Indigo-600
        highlightColor: '#06b6d4', // Cyan-500
      },
      backdropBlur: {
        xs: '2px',
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
