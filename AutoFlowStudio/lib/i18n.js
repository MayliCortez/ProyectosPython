/*
 * i18n.js — Traducciones minimas del panel (es / en). UMD.
 * Se puede ampliar agregando idiomas al objeto STRINGS.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { i18n: mod });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const STRINGS = {
    es: {
      title: "AutoFlow Studio",
      mode: "Modo",
      text_to_video: "Texto a Video",
      frame_to_video: "Frame a Video",
      ingredients_to_video: "Ingredientes a Video",
      text_to_image: "Texto a Imagen",
      image_to_image: "Imagen a Imagen",
      prompts_placeholder: "Pega tus prompts aqui.\nSepara cada uno con una LINEA EN BLANCO.",
      import_file: "Importar archivo",
      add_to_queue: "Agregar a la cola",
      start: "Iniciar",
      pause: "Pausar",
      resume: "Reanudar",
      stop: "Detener",
      clear: "Limpiar",
      settings: "Ajustes",
      queue: "Cola",
      empty_queue: "La cola esta vacia.",
      status_queued: "En espera",
      status_generating: "Generando",
      status_downloading: "Descargando",
      status_completed: "Completado",
      status_failed: "Fallido",
      status_skipped: "Omitido",
      aspect_ratio: "Relacion de aspecto",
      duration: "Duracion",
      outputs: "Salidas por prompt",
      concurrency: "Concurrencia",
      video_model: "Modelo de video",
      image_model: "Modelo de imagen",
      delay: "Delay (ms)",
      retries: "Reintentos",
      auto_download: "Auto-descarga",
      resolution: "Resolucion",
      theme: "Tema",
      language: "Idioma",
      not_on_flow: "Abre un proyecto de Google Flow para usar la extension.",
    },
    en: {
      title: "AutoFlow Studio",
      mode: "Mode",
      text_to_video: "Text to Video",
      frame_to_video: "Frame to Video",
      ingredients_to_video: "Ingredients to Video",
      text_to_image: "Text to Image",
      image_to_image: "Image to Image",
      prompts_placeholder: "Paste your prompts here.\nSeparate each one with a BLANK LINE.",
      import_file: "Import file",
      add_to_queue: "Add to queue",
      start: "Start",
      pause: "Pause",
      resume: "Resume",
      stop: "Stop",
      clear: "Clear",
      settings: "Settings",
      queue: "Queue",
      empty_queue: "The queue is empty.",
      status_queued: "Queued",
      status_generating: "Generating",
      status_downloading: "Downloading",
      status_completed: "Completed",
      status_failed: "Failed",
      status_skipped: "Skipped",
      aspect_ratio: "Aspect ratio",
      duration: "Duration",
      outputs: "Outputs per prompt",
      concurrency: "Concurrency",
      video_model: "Video model",
      image_model: "Image model",
      delay: "Delay (ms)",
      retries: "Retries",
      auto_download: "Auto-download",
      resolution: "Resolution",
      theme: "Theme",
      language: "Language",
      not_on_flow: "Open a Google Flow project to use the extension.",
    },
  };

  function createTranslator(lang) {
    const table = STRINGS[lang] || STRINGS.es;
    return function t(key) {
      return table[key] || STRINGS.es[key] || key;
    };
  }

  return { STRINGS, createTranslator, languages: Object.keys(STRINGS) };
});
