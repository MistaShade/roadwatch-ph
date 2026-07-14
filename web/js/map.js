/** Leaflet map helpers */

var DARK_TILES = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
var TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
var PH_CENTER = [12.5, 122.0];
var DEFAULT_ZOOM = 6;
// Zooming out further than this shows neighboring countries, which aren't
// relevant for a PH-only reporting app -- this caps it at "whole country
// visible" and no further.
var MIN_ZOOM = 5;
// Soft bounds around the Philippines (with some padding) so panning can't
// drift off toward other countries either.
var PH_BOUNDS = [
  [3.0, 113.0],  // southwest
  [22.0, 129.0], // northeast
];

var mainMap = null;
var markersLayer = null;
var markersById = {};

function initMainMap(containerId) {
  if (typeof L === 'undefined') {
    console.error('Leaflet failed to load. Check your internet connection.');
    return null;
  }

  mainMap = L.map(containerId, {
    center: PH_CENTER,
    zoom: DEFAULT_ZOOM,
    minZoom: MIN_ZOOM,
    maxBounds: PH_BOUNDS,
    maxBoundsViscosity: 1.0,
    zoomControl: true,
    attributionControl: true,
  });

  L.tileLayer(DARK_TILES, {
    attribution: TILE_ATTR,
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(mainMap);

  markersLayer = L.layerGroup().addTo(mainMap);
  mainMap.zoomControl.setPosition('topleft');

  // Leaflet needs a size recalc after the page finishes layout
  setTimeout(function () {
    mainMap.invalidateSize();
  }, 100);

  window.addEventListener('resize', function () {
    mainMap.invalidateSize();
  });

  return mainMap;
}

function createDamageMarker(lat, lng, color, teamDispatched, pending) {
  var effectiveColor = pending ? '#94a3b8' : color;
  var html = teamDispatched
    ? '<div class="damage-marker damage-marker-dispatched">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="' + effectiveColor + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>' +
        '</svg>' +
      '</div>'
    : '<div class="damage-marker' + (pending ? ' damage-marker-pending' : '') + '" style="background:' + effectiveColor + '"></div>';

  var icon = L.divIcon({
    className: '',
    html: html,
    iconSize: [teamDispatched ? 22 : 14, teamDispatched ? 22 : 14],
    iconAnchor: [teamDispatched ? 11 : 7, teamDispatched ? 11 : 7],
  });
  return L.marker([lat, lng], { icon: icon });
}

function buildReportPopupHtml(r) {
  var imageHtml = r.imageDataUrl
    ? '<img src="' + r.imageDataUrl + '" alt="' + r.label + '" ' +
      'style="width:100%;max-width:220px;height:140px;object-fit:cover;' +
      'border-radius:8px;display:block;margin-bottom:8px;" />'
    : '';
  var statusHtml = r.pending
    ? '<br><span style="color:#94a3b8;font-weight:600;">&#9203; Pending review</span>'
    : r.teamDispatched
      ? '<br><span style="color:' + r.color + ';font-weight:600;">&#128295; Repair team dispatched</span>'
      : '<br><span style="color:#eab308;font-weight:600;">&#128269; Under inspection</span>';

  var alsoConsideredHtml = '';
  if (r.alsoConsidered && r.alsoConsidered.length > 0) {
    alsoConsideredHtml =
      '<div style="margin-top:8px;padding-top:6px;border-top:1px solid #eee;font-size:0.78em;">' +
        '<div style="color:#888;font-weight:600;margin-bottom:2px;">Also considered:</div>' +
        r.alsoConsidered.map(function (item) {
          return '<div style="display:flex;justify-content:space-between;">' +
            '<span>' + item.label + '</span><span style="color:#888;">' + item.confidence + '%</span>' +
          '</div>';
        }).join('') +
      '</div>';
  }

  return (
    '<div style="min-width:180px;">' +
      imageHtml +
      '<strong>' + r.label + '</strong><br>' +
      r.confidence + '% confidence<br>' +
      '<small>' + r.lat.toFixed(4) + ', ' + r.lng.toFixed(4) + '</small>' +
      statusHtml +
      alsoConsideredHtml +
    '</div>'
  );
}

function refreshMapMarkers(approvedReports) {
  if (!markersLayer) return;
  markersLayer.clearLayers();
  markersById = {};
  approvedReports.forEach(function (r) {
    var marker = createDamageMarker(r.lat, r.lng, r.color, r.teamDispatched, r.pending);
    marker.bindPopup(buildReportPopupHtml(r), { maxWidth: 240 });
    marker.on('click', function () {
      // Optional hook -- only defined on admin.html, so this is a no-op
      // (and harmless) on the public site.
      if (typeof window.onMapMarkerClick === 'function') {
        window.onMapMarkerClick(r.id);
      }
    });
    markersLayer.addLayer(marker);
    markersById[r.id] = marker;
  });
}

function openReportPopup(id) {
  var marker = markersById[id];
  if (marker) {
    marker.openPopup();
  }
}

function flyToReport(lat, lng, onArrive) {
  if (!mainMap) return;
  if (onArrive) {
    mainMap.once('moveend', onArrive);
  }
  mainMap.flyTo([lat, lng], 15, { duration: 1.2 });
}

function createLocationMap(containerId, lat, lng, onMove) {
  var container = document.getElementById(containerId);
  var map = L.map(containerId, {
    center: [lat, lng],
    zoom: 15,
    minZoom: MIN_ZOOM,
    maxBounds: PH_BOUNDS,
    maxBoundsViscosity: 1.0,
    zoomControl: true,
    attributionControl: true,
  });

  L.tileLayer(DARK_TILES, {
    attribution: TILE_ATTR,
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  var pinIcon = L.divIcon({
    className: '',
    html: '<svg width="32" height="40" viewBox="0 0 24 36" fill="#ef4444" xmlns="http://www.w3.org/2000/svg"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0zm0 16.5A4.5 4.5 0 1 1 12 7.5a4.5 4.5 0 0 1 0 9z"/></svg>',
    iconSize: [32, 40],
    iconAnchor: [16, 40],
  });

  var marker = L.marker([lat, lng], { icon: pinIcon, draggable: true }).addTo(map);

  marker.on('dragend', function () {
    var pos = marker.getLatLng();
    onMove(pos.lat, pos.lng);
  });

  map.on('click', function (e) {
    marker.setLatLng(e.latlng);
    onMove(e.latlng.lat, e.latlng.lng);
  });

  forceMapResize(map, container);

  return { map: map, marker: marker };
}

/**
 * A single fixed-delay invalidateSize() guess is unreliable inside modals --
 * if the container hasn't finished its layout/animation by the time the
 * timeout fires, Leaflet renders tiles and computes marker positions using
 * the WRONG (usually smaller) size, causing the "half-blank map, giant
 * misplaced pin, dragging feels broken" bug. This keeps correcting the size
 * across several animation frames (catches the modal's slide-up transition
 * finishing at various points) and, where supported, keeps watching for any
 * future container resize so it's never stale again.
 */
function forceMapResize(map, container) {
  var attempts = 0;
  function tick() {
    map.invalidateSize();
    attempts += 1;
    if (attempts < 10) {
      requestAnimationFrame(tick);
    }
  }
  requestAnimationFrame(tick);

  if (container && typeof ResizeObserver !== 'undefined') {
    var observer = new ResizeObserver(function () {
      map.invalidateSize();
    });
    observer.observe(container);
    map.on('remove', function () {
      observer.disconnect();
    });
  }
}

function updateLocationMarker(marker, lat, lng) {
  marker.setLatLng([lat, lng]);
}

function invalidateLocationMap(map) {
  map.invalidateSize();
}
