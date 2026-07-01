/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#040d1a',
        bg2:      '#071428',
        surface:  '#0a1f3d',
        surface2: '#0f2a50',
        teal:     '#00d4aa',
        teal2:    '#00b894',
        amber:    '#f59e0b',
        danger:   '#ef4444',
        blue:     '#3b82f6',
        muted:    '#6b82a8',
        copy:     '#e8f0fe',
      },
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
        body:    ['DM Sans', 'sans-serif'],
      },
      animation: {
        fadeUp:  'fadeUp 0.6s ease both',
        fadeIn:  'fadeIn 0.6s ease both',
        float:   'float 6s ease-in-out infinite',
        pulse2:  'pulse2 2s infinite',
      },
      keyframes: {
        fadeUp:  { from: { opacity: '0', transform: 'translateY(22px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        fadeIn:  { from: { opacity: '0' }, to: { opacity: '1' } },
        float:   { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-13px)' } },
        pulse2:  { '0%,100%': { opacity: '1', transform: 'scale(1)' }, '50%': { opacity: '0.4', transform: 'scale(0.7)' } },
      },
      boxShadow: {
        glow: '0 0 40px rgba(0,212,170,0.15)',
        card: '0 24px 64px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [],
}
