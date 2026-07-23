/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 对齐 pea-canvas-v12.html 设计令牌
        pea: {
          brand: '#1fa2dc', // 主强调色（青蓝）
          brandStrong: '#0b86bd', // 浅色背景上的可读变体
          purple: '#8b5cf6', // AI / 次强调（紫）
          lime: '#34d399', // 第三强调（青柠）
          accent: '#8b5cf6', // 兼容旧 to-pea-accent 用法
        },
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          '"PingFang SC"',
          '"Noto Sans CJK SC"',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};
