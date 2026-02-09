/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js}'
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif']
      },
      colors: {
        accent: '#2563EB',
        'text-primary': '#18181B',
        'text-secondary': '#71717A',
        'text-tertiary': '#A1A1AA',
        'border-default': '#E4E4E7',
        'surface': '#F9FAFB',
        'highlight': '#EFF6FF',
        // Leave type colors
        'leave-annual-bg': '#DBEAFE',
        'leave-annual-text': '#2563EB',
        'leave-personal-bg': '#FEF3C7',
        'leave-personal-text': '#B45309',
        'leave-sick-bg': '#FEE2E2',
        'leave-sick-text': '#DC2626',
        'leave-comp-bg': '#D1FAE5',
        'leave-comp-text': '#059669'
      }
    }
  },
  plugins: []
}
