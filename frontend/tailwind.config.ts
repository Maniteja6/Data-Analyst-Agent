import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // DataPilot design tokens — deep navy sidebar, violet accent, clean canvas
        dp: {
          navy:    '#1A1A3E',
          'navy-light': '#23235A',
          violet:  '#5B4FE8',
          'violet-light': '#7B6FFF',
          'violet-dim':   '#EEEDfe',
          canvas:  '#F5F4F1',
          surface: '#FFFFFF',
          border:  '#E2E0D8',
          muted:   '#888780',
          text:    '#1E1E1C',
          'text-secondary': '#5F5E5A',
          teal:    '#0F9B8E',
          amber:   '#F59E0B',
          rose:    '#EF4444',
          emerald: '#10B981',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.65rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        'dp': '10px',
      },
      boxShadow: {
        'dp-card': '0 1px 3px 0 rgba(0,0,0,.06), 0 1px 2px -1px rgba(0,0,0,.04)',
        'dp-elevated': '0 4px 16px 0 rgba(0,0,0,.10)',
      },
      animation: {
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
        'fade-in':   'fadeIn 0.2s ease-out',
        'slide-up':  'slideUp 0.25s ease-out',
      },
      keyframes: {
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.3' },
          '40%':           { transform: 'scale(1)',   opacity: '1'   },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to:   { opacity: '1', transform: 'translateY(0)'   },
        },
      },
    },
  },
  plugins: [],
} satisfies Config