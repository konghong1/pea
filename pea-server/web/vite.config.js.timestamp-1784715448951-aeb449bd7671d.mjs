// vite.config.js
import { defineConfig } from "file:///D:/workspace/pea/pea-server/web/node_modules/vite/dist/node/index.js";
import react from "file:///D:/workspace/pea/pea-server/web/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发期把 API/WS 代理到本地 BFF
      "/auth": "http://localhost:4000",
      "/users": "http://localhost:4000",
      "/billing": "http://localhost:4000",
      "/generation": "http://localhost:4000",
      "/files": "http://localhost:4000",
      "/canvases": "http://localhost:4000",
      "/internal": "http://localhost:4000",
      "/ws": { target: "ws://localhost:4000", ws: true }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJEOlxcXFx3b3Jrc3BhY2VcXFxccGVhXFxcXHBlYS1zZXJ2ZXJcXFxcd2ViXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCJEOlxcXFx3b3Jrc3BhY2VcXFxccGVhXFxcXHBlYS1zZXJ2ZXJcXFxcd2ViXFxcXHZpdGUuY29uZmlnLmpzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9EOi93b3Jrc3BhY2UvcGVhL3BlYS1zZXJ2ZXIvd2ViL3ZpdGUuY29uZmlnLmpzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSc7XG5pbXBvcnQgcmVhY3QgZnJvbSAnQHZpdGVqcy9wbHVnaW4tcmVhY3QnO1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgICBwbHVnaW5zOiBbcmVhY3QoKV0sXG4gICAgc2VydmVyOiB7XG4gICAgICAgIHBvcnQ6IDUxNzMsXG4gICAgICAgIHByb3h5OiB7XG4gICAgICAgICAgICAvLyBcdTVGMDBcdTUzRDFcdTY3MUZcdTYyOEEgQVBJL1dTIFx1NEVFM1x1NzQwNlx1NTIzMFx1NjcyQ1x1NTczMCBCRkZcbiAgICAgICAgICAgICcvYXV0aCc6ICdodHRwOi8vbG9jYWxob3N0OjQwMDAnLFxuICAgICAgICAgICAgJy91c2Vycyc6ICdodHRwOi8vbG9jYWxob3N0OjQwMDAnLFxuICAgICAgICAgICAgJy9iaWxsaW5nJzogJ2h0dHA6Ly9sb2NhbGhvc3Q6NDAwMCcsXG4gICAgICAgICAgICAnL2dlbmVyYXRpb24nOiAnaHR0cDovL2xvY2FsaG9zdDo0MDAwJyxcbiAgICAgICAgICAgICcvZmlsZXMnOiAnaHR0cDovL2xvY2FsaG9zdDo0MDAwJyxcbiAgICAgICAgICAgICcvY2FudmFzZXMnOiAnaHR0cDovL2xvY2FsaG9zdDo0MDAwJyxcbiAgICAgICAgICAgICcvaW50ZXJuYWwnOiAnaHR0cDovL2xvY2FsaG9zdDo0MDAwJyxcbiAgICAgICAgICAgICcvd3MnOiB7IHRhcmdldDogJ3dzOi8vbG9jYWxob3N0OjQwMDAnLCB3czogdHJ1ZSB9LFxuICAgICAgICB9LFxuICAgIH0sXG59KTtcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBeVIsU0FBUyxvQkFBb0I7QUFDdFQsT0FBTyxXQUFXO0FBQ2xCLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQ3hCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixRQUFRO0FBQUEsSUFDSixNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUE7QUFBQSxNQUVILFNBQVM7QUFBQSxNQUNULFVBQVU7QUFBQSxNQUNWLFlBQVk7QUFBQSxNQUNaLGVBQWU7QUFBQSxNQUNmLFVBQVU7QUFBQSxNQUNWLGFBQWE7QUFBQSxNQUNiLGFBQWE7QUFBQSxNQUNiLE9BQU8sRUFBRSxRQUFRLHVCQUF1QixJQUFJLEtBQUs7QUFBQSxJQUNyRDtBQUFBLEVBQ0o7QUFDSixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
