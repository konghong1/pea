/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 统一设计系统：主操作为中性墨色，语义彩色仅 purple/lime
        pea: {
          brand: '#171717', // 主操作（中性黑/白，取代原青蓝）
          brandStrong: '#000000',
          purple: '#8b5cf6', // AI / 生成态信号
          lime: '#34d399', // 成功/完成态
          accent: '#8b5cf6', // 兼容旧 to-pea-accent 用法
        },
      },
      fontFamily: {
        sans: [
          'Geist',
          'Inter',
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
