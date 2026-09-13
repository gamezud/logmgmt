import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite's default dev port (5173) is what backend/config.py's
// FRONTEND_ORIGIN default and CORSMiddleware expect out of the box — see
// docs/DECISIONS.md.
export default defineConfig({
  plugins: [react()],
});
