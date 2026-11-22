(function () {
  "use strict";

  var PALETTES = {
    tips: { nombre: "Tips técnicos DJI / Configuración", clave: "tips", accent: "#00E5FF", accent_2: "#F4FBFF", ground: "#0B111A", surface: "#101A27", ink: "#F4FBFF", font_display: "Outfit" },
    fpv: { nombre: "Vuelo FPV / Acción / Velocidad", clave: "fpv", accent: "#FF6B00", accent_2: "#FFD166", ground: "#0D0D0F", surface: "#171216", ink: "#FFF7ED", font_display: "Outfit" },
    cine: { nombre: "Tomas cinematográficas / Edición / Color", clave: "cine", accent: "#10B981", accent_2: "#FBBF24", ground: "#0F172A", surface: "#111C32", ink: "#ECFDF5", font_display: "Space Grotesk" },
    tech: { nombre: "Novedades Tech / Gadgets / Comparativas", clave: "tech", accent: "#8B5CF6", accent_2: "#EC4899", ground: "#090D16", surface: "#12142A", ink: "#F5F3FF", font_display: "Outfit" }
  };

  var RULES = [
    ["tips", /tip|configuraci[oó]n|configuracion|ajuste|sensor|checklist|bater[ií]a|bateria|dji/i],
    ["fpv", /fpv|acci[oó]n|accion|velocidad|racing|freestyle|veloz|r[aá]pido|rapido/i],
    ["cine", /cinematogr[aá]fic|cinematograf|edici[oó]n|edicion|color|toma|plano|grade|a[eé]reo|aereo/i],
    ["tech", /tech|tecnolog|gadget|comparativa|novedad|review|lanzamiento/i]
  ];

  function normalize(text) {
    return String(text || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function resolvePalette() {
    var root = document.documentElement;
    var explicit = normalize(root.getAttribute("data-palette") || "");
    if (explicit && PALETTES[explicit]) return PALETTES[explicit];
    var category = normalize(root.getAttribute("data-category") || "");
    var title = normalize(root.getAttribute("data-title") || document.title || "");
    var haystack = category + " " + title;
    for (var i = 0; i < RULES.length; i += 1) {
      if (RULES[i][1].test(haystack)) return PALETTES[RULES[i][0]];
    }
    return PALETTES.tips;
  }

  var palette = resolvePalette();
  var root = document.documentElement;
  root.style.setProperty("--accent", palette.accent);
  root.style.setProperty("--accent-2", palette.accent_2);
  root.style.setProperty("--ground", palette.ground);
  root.style.setProperty("--surface", palette.surface);
  root.style.setProperty("--ink", palette.ink);
  root.style.setProperty("--font-display", '"' + palette.font_display + '", sans-serif');
  root.style.setProperty("--muted", "rgba(244, 251, 255, 0.62)");
  root.style.setProperty("--hairline", "rgba(244, 251, 255, 0.12)");
  root.style.setProperty("--caption-bg", "rgba(0, 0, 0, 0.75)");
  root.style.setProperty("--caption-radius", "16px");
  root.style.setProperty("--accent-soft", palette.accent + "33");
  root.setAttribute("data-palette-resolved", palette.clave);
  root.setAttribute("data-category", root.getAttribute("data-category") || palette.clave);
  window.__AURA_PALETTE__ = palette;
})();
