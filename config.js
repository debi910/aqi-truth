// Where the live API runs. Locally (docker compose, Codespace) the page talks to its own server.
// Only the GitHub Pages copy points at the hosted Db2 + Granite demo server.
window.AQT_API = window.AQT_API ||
  (location.hostname.endsWith("github.io") ? "https://super-invention-g475pv4x6vjw26wq-8000.app.github.dev" : "");
