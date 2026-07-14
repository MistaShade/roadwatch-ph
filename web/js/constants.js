/** Damage type definitions matching the map legend */
var DAMAGE_TYPES = {
  pothole: { label: 'Pothole', color: '#ef4444' },
  alligator_crack: { label: 'Alligator Crack', color: '#a855f7' },
  longitudinal_crack: { label: 'Longitudinal Crack', color: '#f97316' },
  transverse_crack: { label: 'Transverse Crack', color: '#eab308' },
  intact_road: { label: 'Intact Road', color: '#14b8a6' },
};

var TYPE_KEYS = Object.keys(DAMAGE_TYPES);
var API_BASE = 'http://127.0.0.1:5000';

/** Severity levels a reporter can (optionally) select. */
var SEVERITY_LEVELS = {
  low: { label: 'Low', color: '#22c55e' },
  moderate: { label: 'Moderate', color: '#eab308' },
  severe: { label: 'Severe', color: '#ef4444' },
};

/** Starting suggestion only -- the reporter can change it, and the admin
 * can override it later. Not a substitute for real severity detection,
 * which the model doesn't currently do. */
var SEVERITY_SUGGESTION = {
  pothole: 'severe',
  alligator_crack: 'severe',
  longitudinal_crack: 'moderate',
  transverse_crack: 'moderate',
  intact_road: 'low',
};

function dataUrlToBlob(dataUrl) {
  var parts = dataUrl.split(',');
  var mimeMatch = parts[0].match(/:(.*?);/);
  var mime = mimeMatch ? mimeMatch[1] : 'image/jpeg';
  var binary = atob(parts[1]);
  var array = new Uint8Array(binary.length);
  for (var i = 0; i < binary.length; i++) {
    array[i] = binary.charCodeAt(i);
  }
  return new Blob([array], { type: mime });
}

/** Call the trained VGG16 + RBF-SVM model via the local API */
function classifyImage(imageDataUrl) {
  var formData = new FormData();
  formData.append('image', dataUrlToBlob(imageDataUrl), 'report.jpg');

  return fetch(API_BASE + '/api/classify', {
    method: 'POST',
    body: formData,
  }).then(function (response) {
    if (!response.ok) {
      return response.json().catch(function () {
        return { error: 'Classification failed' };
      }).then(function (body) {
        throw new Error(body.error || 'Classification failed');
      });
    }
    return response.json();
  });
}

/** Fallback only if the API server is not running */
function mockClassify(_imageDataUrl) {
  var weights = [0.45, 0.15, 0.15, 0.15, 0.10];
  var roll = Math.random();
  var typeKey = TYPE_KEYS[0];
  for (var i = 0; i < TYPE_KEYS.length; i++) {
    roll -= weights[i];
    if (roll <= 0) {
      typeKey = TYPE_KEYS[i];
      break;
    }
  }
  var confidence = 65 + Math.random() * 30;
  return {
    type: typeKey,
    label: DAMAGE_TYPES[typeKey].label,
    confidence: Math.round(confidence * 10) / 10,
    color: DAMAGE_TYPES[typeKey].color,
  };
}

function formatCoords(lat, lng) {
  return 'Pin: ' + lat.toFixed(5) + ', ' + lng.toFixed(5);
}

function formatTimestamp(date) {
  return date.toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}
