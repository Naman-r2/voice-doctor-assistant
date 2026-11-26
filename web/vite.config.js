import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser talks to /api on the same origin; Vite forwards it to the Python server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:7860" },
  },
});
