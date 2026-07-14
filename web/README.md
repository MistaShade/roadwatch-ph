# RoadWatch PH — Web UI

Crowdsourced road damage reporting interface for the Philippines. **UI-only prototype** — classification uses a mock predictor until the model is trained.

## Screens

| Screen | Description |
|--------|-------------|
| **Live Map** | Dark Leaflet map centered on the Philippines with approved report markers and legend |
| **Report Damage** | 4-step flow: upload photo → confirm location → AI classification (mock) → success |
| **Settings** | Admin portal link and report statistics |
| **Admin sign-in** | Demo credentials: `admin` / `admin123` |
| **Admin Dashboard** | Review pending reports — inspect, approve, or reject |

## Run locally

**Important:** Don't double-click `index.html` — browsers block the app from loading properly that way. Use a local server instead:

### Easiest way (Windows)
Double-click **`start.bat`** inside the `web` folder. It starts a server and opens http://localhost:8080 automatically.

### Python
```bash
cd web
python -m http.server 8080
```
Open http://localhost:8080

### VS Code / Cursor
Use the **Live Server** extension and open `web/index.html`.

You need an internet connection for the map tiles (OpenStreetMap via Leaflet).

## Project structure

```
web/
├── index.html          # Main HTML shell
├── css/styles.css      # All styles (matches reference design)
└── js/
    ├── app.js          # UI logic & event handlers
    ├── map.js          # Leaflet map setup
    ├── store.js        # Report state (localStorage)
    └── constants.js    # Damage types & mock classifier
```

## Damage types (map legend)

- 🔴 Pothole
- 🟣 Alligator Crack
- 🟠 Longitudinal Crack
- 🟡 Transverse Crack
- 🟢 Intact Road

## Next steps (when ready)

1. Replace `mockClassify()` in `js/constants.js` with a real API call to your trained model
2. Add a backend (e.g. Flask/FastAPI) for persistent storage and image upload
3. Optionally migrate to React/Vite when Node.js is available
