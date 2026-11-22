# HyperFrames Project Rules

All HyperFrames projects in this workspace MUST adhere to these mandatory rules to ensure reliability and performance.

## 1. Local Dependencies Only
- **NO EXTERNAL CDNs:** Never use external CDN links (e.g., `jsdelivr`, `unpkg`) for GSAP, Three.js, or any other libraries in `index.html` or sub-compositions.
- **Action:** Download the required scripts and store them locally in the project's `assets/scripts/` or a similar local directory. Update all `<script src="...">` tags to point to these local files.

## 2. Performance Optimization (Fast Capture)
- **NO CSS BLUR FILTERS:** Never use `filter:blur()` or `backdrop-filter` in CSS. These properties force HyperFrames into "screenshot capture" mode, which is significantly slower.
- **Goal:** Maintain "fast capture" compatibility for all renders. Use pre-rendered assets or alternative visual techniques that do not rely on real-time CSS blurs.

## 3. GPU & Process Management
- **CLEAN RENDERS:** Before starting a new render, ensure no previous `node` or render processes are hanging.
- **Action:** Stop any active `npx hyperframes render` or `npm run dev` processes that are no longer needed to avoid GPU saturation and resource contention.
