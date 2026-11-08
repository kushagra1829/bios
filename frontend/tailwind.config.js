/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        midnight: {
          DEFAULT: "#142438",
          50: "#f4f6f9",
          100: "#e5e9f0",
          200: "#cbd4e0",
          300: "#a3b4c9",
          400: "#738eae",
          500: "#4f6e93",
          600: "#3d5575",
          700: "#32455f",
          800: "#2a394e",
          900: "#142438",
          950: "#0b1522",
        },
        intelligence: {
          DEFAULT: "#3478F6",
          50: "#eff6ff",
          100: "#dbeafe",
          500: "#3478F6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        trust: {
          DEFAULT: "#16A085",
          50: "#f0fdf9",
          100: "#ccfbef",
          500: "#16A085",
          600: "#0d846c",
        },
        cloud: {
          DEFAULT: "#F2F5F9",
          dark: "#E4E9F2",
        },
        warning: {
          DEFAULT: "#E5A12B",
          50: "#fef9ee",
          100: "#fdf0d3",
          500: "#E5A12B",
          600: "#c78417",
        },
        critical: {
          DEFAULT: "#DC5252",
          50: "#fef2f2",
          100: "#fee2e2",
          500: "#DC5252",
          600: "#b93838",
        },
      },
    },
  },
  plugins: [],
};

