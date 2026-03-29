/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        hospitalPrimary: '#0f766e', // A professional medical teal
        hospitalDark: '#0f172a',    // Deep slate for admin dashboards
      }
    },
  },
  plugins: [],
}