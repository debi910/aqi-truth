// Where the live API runs. Empty = same origin (docker compose / hosted server serves this page itself).
// The GitHub Pages copy sets this to the hosted Db2 + Granite server so the static page uses the live engine.
window.AQT_API = window.AQT_API || "";
