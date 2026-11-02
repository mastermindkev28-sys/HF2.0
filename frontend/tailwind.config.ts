import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#060607", 900: "#0b0b0d", 850: "#111114", 800: "#16161a", 700: "#1e1e23", 600: "#2a2a31", 500: "#3a3a43" },
        fog: { 100: "#f4f4f5", 300: "#c9c9cf", 400: "#9d9da6", 500: "#74747d" },
        accent: { DEFAULT: "#d8ff5c", dim: "#b6d94a" },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Inter", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        display: ["ui-serif", "Iowan Old Style", "Palatino", "Georgia", "serif"],
        mono: ["ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
      boxShadow: { glow: "0 0 0 1px rgba(216,255,92,.35), 0 8px 30px -8px rgba(216,255,92,.25)" },
    },
  },
  plugins: [],
} satisfies Config;
