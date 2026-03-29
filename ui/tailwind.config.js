/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                condensed: ['"Barlow Condensed"', 'ui-sans-serif', 'sans-serif'],
                ui: ['Barlow', 'ui-sans-serif', 'sans-serif'],
            },
            colors: {
                opal: {
                    50: '#f0f7f7',
                    100: '#daebeb',
                    200: '#b9dada',
                    500: '#4da6a6',
                    600: '#3d8585',
                    700: '#326d6d',
                    800: '#285858',
                    900: '#1d4040',
                },
                synth: {
                    purple: '#1a1a2e',
                    blue: '#00d2ff',
                    pink: '#ff007f',
                    dark: '#050505',
                }
            },
            backgroundImage: {
                'grid-pattern': "url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHZpZXdCb3g9IjAgMCA0MCA0MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIHN0cm9rZT0iIzMzMyIgc3Ryb2tlLXdpZHRoPSIxIj48cGF0aCBkPSJNMCA0MGg0MCIvPjxwYXRoIGQ9Ik00MCAwdjQwIi8+PC9nPjwvZz48L3N2Zz4=')",
            }
        },
    },
    plugins: [],
}
