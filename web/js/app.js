(function () {
  'use strict';

  var reportModal = document.getElementById('report-modal');
  var settingsModal = document.getElementById('settings-modal');
  var reportStepLabel = document.getElementById('report-step-label');

  var reportSteps = [
    document.getElementById('report-step-1'),
    document.getElementById('report-step-2'),
    document.getElementById('report-step-3'),
    document.getElementById('report-step-4'),
  ];

  var currentStep = 0;
  var draft = {
    imageDataUrl: null,
    lat: 14.52914,
    lng: 121.07134,
    classification: null,
    reporterName: '',
    reporterEmail: '',
    duration: '',
    severity: '',
  };
  var locationMapInstance = null;

  function renderUI() {
    var state = getState();
    var counts = state.counts;

    // "Approved reports nationwide" -- excludes pending reports on purpose,
    // even though pending reports still show on the map as a grey pin.
    document.getElementById('approved-count').textContent = counts.approved;
    document.getElementById('info-total').textContent = counts.approved;
    document.getElementById('info-pending').textContent = counts.pending;
    document.getElementById('info-dispatched').textContent = counts.dispatched;
    document.getElementById('info-resolved').textContent = counts.resolved;

    var activeReports = state.reports.filter(function (r) { return !r.resolved; });
    refreshMapMarkers(activeReports);
  }

  function showReportStep(step) {
    currentStep = step;
    reportStepLabel.textContent = 'Step ' + (step + 1) + ' of 4';
    reportSteps.forEach(function (el, i) {
      el.classList.toggle('hidden', i !== step);
    });
  }

  function resetDraft() {
    draft = {
      imageDataUrl: null,
      lat: 14.52914,
      lng: 121.07134,
      classification: null,
      reporterName: '',
      reporterEmail: '',
    };
    locationMapInstance = null;
    document.getElementById('photo-input').value = '';
    document.getElementById('reporter-name').value = '';
    document.getElementById('reporter-email').value = '';
    document.getElementById('report-duration').value = '';
    document.getElementById('report-severity').value = '';
    document.getElementById('classifying-state').classList.remove('hidden');
    document.getElementById('classification-result').classList.add('hidden');
    document.getElementById('top-predictions').innerHTML = '';
  }

  function formatTypeLabel(typeKey) {
    if (!typeKey) {
      return 'Unknown';
    }
    return typeKey.replace(/_/g, ' ').replace(/\b\w/g, function (char) {
      return char.toUpperCase();
    });
  }

  function computeAlsoConsidered(result) {
    var predictions = [];
    if (result && result.top_predictions && result.top_predictions.length > 0) {
      predictions = result.top_predictions;
    } else if (result && result.probabilities) {
      predictions = Object.keys(result.probabilities)
        .map(function (typeKey) {
          return {
            type: typeKey,
            label: (DAMAGE_TYPES && DAMAGE_TYPES[typeKey] && DAMAGE_TYPES[typeKey].label) || formatTypeLabel(typeKey),
            confidence: result.probabilities[typeKey],
          };
        })
        .sort(function (a, b) { return b.confidence - a.confidence; })
        .slice(0, 3);
    }

    // The top prediction is shown as the headline elsewhere -- only
    // return the other candidates here to avoid showing it twice.
    var primaryType = result && result.type;
    return predictions.filter(function (item) { return item.type !== primaryType; });
  }

  function renderTopPredictions(result) {
    var container = document.getElementById('top-predictions');
    container.innerHTML = '';

    var predictions = computeAlsoConsidered(result);

    if (predictions.length === 0) {
      return;
    }

    predictions.forEach(function (item) {
      var row = document.createElement('div');
      row.className = 'prediction-row';
      row.innerHTML =
        '<span class="prediction-label">' + item.label + '</span>' +
        '<span class="prediction-confidence">' + item.confidence + '%</span>';
      container.appendChild(row);
    });
  }

  function openReport() {
    resetDraft();
    showReportStep(0);
    reportModal.classList.remove('hidden');
  }

  function closeReport() {
    reportModal.classList.add('hidden');
    if (locationMapInstance && locationMapInstance.map) {
      locationMapInstance.map.remove();
      locationMapInstance = null;
    }
  }

  function handleImageFile(file) {
    if (!file || !file.type.startsWith('image/')) return;
    if (file.size > 10 * 1024 * 1024) {
      alert('Image must be under 10MB.');
      return;
    }

    var reader = new FileReader();
    reader.onload = function (e) {
      draft.imageDataUrl = e.target.result;
      document.getElementById('preview-image').src = draft.imageDataUrl;
      document.getElementById('preview-image-2').src = draft.imageDataUrl;
      showReportStep(1);
      initLocationMap();
    };
    reader.readAsDataURL(file);
  }

  function initLocationMap() {
    if (locationMapInstance && locationMapInstance.map) {
      locationMapInstance.map.remove();
    }

    locationMapInstance = createLocationMap(
      'location-map',
      draft.lat,
      draft.lng,
      function (lat, lng) {
        draft.lat = lat;
        draft.lng = lng;
        document.getElementById('pin-coords').textContent = formatCoords(lat, lng);
      }
    );
    document.getElementById('pin-coords').textContent = formatCoords(draft.lat, draft.lng);
    invalidateLocationMap(locationMapInstance.map);
  }

  function requestGPS() {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        draft.lat = pos.coords.latitude;
        draft.lng = pos.coords.longitude;
        if (locationMapInstance) {
          updateLocationMarker(locationMapInstance.marker, draft.lat, draft.lng);
          locationMapInstance.map.setView([draft.lat, draft.lng], 16);
        }
        document.getElementById('pin-coords').textContent = formatCoords(draft.lat, draft.lng);
      },
      function () {
        alert('Could not get your location. Drag the pin or click the map to set it.');
      }
    );
  }

  function runClassification() {
    showReportStep(2);
    document.getElementById('classifying-state').classList.remove('hidden');
    document.getElementById('classification-result').classList.add('hidden');

    classifyImage(draft.imageDataUrl)
      .then(function (result) {
        draft.classification = result;
        document.getElementById('result-type').textContent = result.label;
        document.getElementById('result-confidence').textContent =
          result.confidence + '% confidence';
        renderTopPredictions(result);

        // Pre-fill a starting suggestion based on the detected damage type
        // -- the reporter can still change it before submitting.
        var suggested = (typeof SEVERITY_SUGGESTION !== 'undefined') ? SEVERITY_SUGGESTION[result.type] : null;
        if (suggested) {
          document.getElementById('report-severity').value = suggested;
        }

        document.getElementById('classifying-state').classList.add('hidden');
        document.getElementById('classification-result').classList.remove('hidden');
      })
      .catch(function (err) {
        document.getElementById('classifying-state').classList.add('hidden');
        alert(
          'Could not reach the prediction server.\n\n' +
          'Start it with: python api.py\n\n' +
          (err && err.message ? err.message : '')
        );
        showReportStep(1);
      });
  }

  function submitReport() {
    var classification = draft.classification;
    draft.reporterName = document.getElementById('reporter-name').value.trim();
    draft.reporterEmail = document.getElementById('reporter-email').value.trim();
    draft.duration = document.getElementById('report-duration').value;
    draft.severity = document.getElementById('report-severity').value;

    addReport({
      imageDataUrl: draft.imageDataUrl,
      lat: draft.lat,
      lng: draft.lng,
      type: classification.type,
      label: classification.label,
      confidence: classification.confidence,
      color: classification.color,
      alsoConsidered: computeAlsoConsidered(classification),
      reporterName: draft.reporterName,
      reporterEmail: draft.reporterEmail,
      duration: draft.duration,
      severity: draft.severity,
    });

    document.getElementById('final-type').textContent = classification.label;
    document.getElementById('final-confidence').textContent =
      classification.confidence + '% confidence';
    showReportStep(3);
  }

  function openSettings() {
    settingsModal.classList.remove('hidden');
  }

  function closeSettings() {
    settingsModal.classList.add('hidden');
  }

  function toggleStatsPanel() {
    var panel = document.getElementById('stats-panel');
    var btn = document.getElementById('toggle-stats-panel');
    var isCollapsed = panel.classList.toggle('collapsed');
    btn.setAttribute('aria-expanded', String(!isCollapsed));
    btn.setAttribute('aria-label', isCollapsed ? 'Expand map info' : 'Collapse map info');
  }

  function bindEvents() {
    document.getElementById('open-report').addEventListener('click', openReport);
    document.getElementById('close-report').addEventListener('click', closeReport);
    document.getElementById('open-settings').addEventListener('click', openSettings);
    document.getElementById('close-settings').addEventListener('click', closeSettings);
    document.getElementById('toggle-stats-panel').addEventListener('click', toggleStatsPanel);

    reportModal.addEventListener('click', function (e) {
      if (e.target === reportModal) closeReport();
    });
    settingsModal.addEventListener('click', function (e) {
      if (e.target === settingsModal) closeSettings();
    });

    var uploadZone = document.getElementById('upload-zone');
    var photoInput = document.getElementById('photo-input');

    uploadZone.addEventListener('click', function () { photoInput.click(); });
    photoInput.addEventListener('change', function (e) {
      handleImageFile(e.target.files[0]);
    });

    uploadZone.addEventListener('dragover', function (e) {
      e.preventDefault();
      uploadZone.classList.add('dragover');
    });
    uploadZone.addEventListener('dragleave', function () {
      uploadZone.classList.remove('dragover');
    });
    uploadZone.addEventListener('drop', function (e) {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
      handleImageFile(e.dataTransfer.files[0]);
    });

    document.getElementById('use-gps').addEventListener('click', requestGPS);
    document.getElementById('back-to-upload').addEventListener('click', function () {
      showReportStep(0);
    });
    document.getElementById('to-classification').addEventListener('click', runClassification);
    document.getElementById('back-to-location').addEventListener('click', function () {
      showReportStep(1);
    });
    document.getElementById('submit-report').addEventListener('click', submitReport);
    document.getElementById('done-report').addEventListener('click', closeReport);
  }

  function init() {
    bindEvents();
    initMainMap('main-map');
    subscribe(renderUI);
    renderUI();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
