import { defineConfig } from "vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { nitro } from "nitro/vite";

export default defineConfig({
  // Expose NEXT_PUBLIC_* in addition to Vite's default VITE_* prefix so the
  // deployed frontend can read NEXT_PUBLIC_API_URL (the Vercel project
  // variable) through import.meta.env. Vite inlines both at build time.
  envPrefix: ["VITE_", "NEXT_PUBLIC_"],
  plugins: [
    tailwindcss(),
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
    tanstackStart({
      // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
      // nitro/vite builds from this
      server: { entry: "server" },
    }),
    nitro(),
    viteReact(),
  ],
});
