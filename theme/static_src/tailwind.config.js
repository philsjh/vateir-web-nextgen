/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "../../templates/**/*.html",
    "../../apps/**/*.py",
    "../../apps/**/*.html",
    "../../static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
          950: "#022c22",
        },
        gold: {
          50: "#fffbeb",
          100: "#fef3c7",
          200: "#fde68a",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
          700: "#b45309",
        },
        // Dark theme surfaces
        surface: {
          DEFAULT: "#0a0f1a",
          50: "#f0f4f8",
          100: "#e2e8f0",
          200: "#cbd5e1",
          300: "#94a3b8",
          400: "#64748b",
          500: "#475569",
          600: "#1e293b",
          700: "#162032",
          800: "#0f172a",
          900: "#0a0f1a",
          950: "#060a12",
        },
        glass: {
          light: "rgba(255, 255, 255, 0.08)",
          medium: "rgba(255, 255, 255, 0.12)",
          heavy: "rgba(255, 255, 255, 0.18)",
          border: "rgba(255, 255, 255, 0.10)",
          // Light mode glass
          "light-bg": "rgba(255, 255, 255, 0.65)",
          "light-medium": "rgba(255, 255, 255, 0.80)",
          "light-heavy": "rgba(255, 255, 255, 0.90)",
          "light-border": "rgba(0, 0, 0, 0.08)",
        },
      },
      backgroundImage: {
        "gradient-brand":
          "linear-gradient(135deg, var(--gradient-from, #059669), var(--gradient-to, #10b981))",
        "gradient-brand-hover":
          "linear-gradient(135deg, var(--gradient-from-hover, #047857), var(--gradient-to-hover, #059669))",
        "gradient-irish":
          "linear-gradient(135deg, #059669, #34d399)",
        "gradient-hero":
          "linear-gradient(135deg, #022c22 0%, #064e3b 25%, #059669 50%, #34d399 75%, #fbbf24 100%)",
        "gradient-hero-light":
          "linear-gradient(135deg, #ecfdf5 0%, #d1fae5 25%, #a7f3d0 50%, #6ee7b7 75%, #fef3c7 100%)",
        "gradient-mesh":
          "radial-gradient(at 40% 20%, rgba(16, 185, 129, 0.15) 0px, transparent 50%), radial-gradient(at 80% 0%, rgba(6, 78, 59, 0.2) 0px, transparent 50%), radial-gradient(at 0% 50%, rgba(5, 150, 105, 0.1) 0px, transparent 50%)",
        "gradient-mesh-light":
          "radial-gradient(at 40% 20%, rgba(16, 185, 129, 0.08) 0px, transparent 50%), radial-gradient(at 80% 0%, rgba(6, 78, 59, 0.06) 0px, transparent 50%), radial-gradient(at 0% 50%, rgba(5, 150, 105, 0.05) 0px, transparent 50%)",
        "gradient-radar":
          "conic-gradient(from 0deg, transparent 0deg, rgba(16, 185, 129, 0.3) 10deg, transparent 40deg)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      backdropBlur: {
        xs: "2px",
      },
      animation: {
        "radar-sweep": "radarSweep 4s linear infinite",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "glow": "glow 2s ease-in-out infinite alternate",
      },
      keyframes: {
        radarSweep: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        glow: {
          from: { boxShadow: "0 0 5px rgba(16, 185, 129, 0.2), 0 0 20px rgba(16, 185, 129, 0.1)" },
          to: { boxShadow: "0 0 10px rgba(16, 185, 129, 0.4), 0 0 40px rgba(16, 185, 129, 0.2)" },
        },
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0, 0, 0, 0.12)",
        "glass-lg": "0 16px 48px rgba(0, 0, 0, 0.16)",
        "glow-brand": "0 0 15px rgba(16, 185, 129, 0.3), 0 0 45px rgba(16, 185, 129, 0.1)",
        "glow-brand-sm": "0 0 8px rgba(16, 185, 129, 0.2)",
        "inner-light": "inset 0 1px 0 rgba(255, 255, 255, 0.05)",
      },
    },
  },
  plugins: [],
};
