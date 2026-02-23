/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    screens: {
      sm: '576px',
      // => @media (min-width: 576px) { ... }

      md: '768px',
      // => @media (min-width: 768px) { ... }

      lg: '992px',
      // => @media (min-width: 992px) { ... }

      xl: '1200px',
      // => @media (min-width: 1200px) { ... }

      xxl: '1400px',
      // => @media (min-width: 1400px) { ... }
    },
    extend: {
      fontFamily: {
        // Add your custom fonts
        dmSans: ['var(--font-DMSans)', 'sans-serif'],
        clashDisplay: ['var(--font-clash-display)', 'sans-serif'],
        raleway: ['var(--font-raleway)', 'sans-serif'],
        spaceGrotesk: ['var(--font-space-grotesk)', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },

      colors: {
        colorCodGray: '#191919',
        colorOrangyRed: '#FE330A',
        colorLinenRuffle: '#EFEAE3',
        colorViolet: '#321CA4',
        colorGreen: '#39FF14',
      },
    },
  },
  plugins: [],
};
