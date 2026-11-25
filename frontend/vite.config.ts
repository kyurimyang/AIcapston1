import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 시연: `ngrok http 5173` 하나로 화면과 API를 모두 HTTPS로 연다.
// 폰은 화면을 ngrok 주소로 열고, /api 요청은 이 서버가 노트북의 백엔드(8000)로 넘긴다.
// (카메라는 HTTPS 페이지에서만 켜지고, HTTPS 페이지는 http API를 부를 수 없다)
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true, // ngrok 주소로 들어오는 요청 허용
    fs: { allow: [".."] }, // 해설 폴백: ../backend/scripts/narrations.json을 함께 묶는다 (src/offline.ts)
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
