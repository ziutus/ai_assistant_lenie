import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    screens: {
      sm: '576px',
      md: '768px',
      lg: '992px',
      xl: '1200px',
      xxl: '1400px',
    },
    extend: {
      fontFamily: {
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

export default config;
