// Where the live API lives when this page is served from GitHub Pages; served by the app itself, it uses its own origin.
window.AQT_API = window.AQT_API ||
  (location.hostname.endsWith("github.io") ? "https://super-invention-g475pv4x6vjw26wq-8000.app.github.dev" : "");
