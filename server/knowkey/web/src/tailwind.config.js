/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '../templates/**/*.html',
    './**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [
    require('./plugins/daisyui.mjs'),
    require('./plugins/typography.js'),
  ],
}
