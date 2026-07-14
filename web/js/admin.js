(function () {
  'use strict';

  var DURATION_LABELS = {
    just_noticed: 'Just noticed it',
    few_days: 'A few days',
    few_weeks: 'A few weeks',
    over_month: 'Over a month',
  };

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function formatTimestamp(date) {
    return date.toLocaleString('en-US', {
      month: 'numeric',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  }

  function statusBadgeHtml(report) {
    if (report.resolved) {
      return '<span class="status-badge resolved">Resolved</span>';
    }
    if (report.pending) {
      return '<span class="status-badge pending-review">Pending Review</span>';
    }
    if (report.teamDispatched) {
      return '<span class="status-badge dispatched">Team Dispatched</span>';
    }
    return '<span class="status-badge inspection">Under Inspection</span>';
  }

  var currentTab = 'accepted';
  var currentView = 'map';
  var chartInstance = null;

  function renderDashboard() {
    var state = getState();
    var activeReports = state.reports.filter(function (r) { return !r.resolved; });

    // Stat cards
    document.getElementById('stat-total').textContent = state.counts.total;
    document.getElementById('stat-accepted').textContent = state.counts.approved;
    document.getElementById('stat-pending').textContent = state.counts.pending;
    var severeCount = activeReports.filter(function (r) { return r.severity === 'severe'; }).length;
    document.getElementById('stat-severe').textContent = severeCount;

    // Map -- unaffected by tabs/filters, always shows every active report
    document.getElementById('admin-pin-count').textContent =
      activeReports.length + ' pin' + (activeReports.length === 1 ? '' : 's');
    refreshMapMarkers(activeReports);

    // Tab counts
    var acceptedAll = activeReports.filter(function (r) { return !r.pending; });
    var pendingAll = activeReports.filter(function (r) { return r.pending; });
    document.getElementById('tab-accepted-count').textContent = '(' + acceptedAll.length + ')';
    document.getElementById('tab-pending-count').textContent = '(' + pendingAll.length + ')';

    renderFilteredList();
    updateAnalyticsChart(activeReports);
  }

  function renderFilteredList() {
    var state = getState();
    var activeReports = state.reports.filter(function (r) { return !r.resolved; });
    var base = currentTab === 'accepted'
      ? activeReports.filter(function (r) { return !r.pending; })
      : activeReports.filter(function (r) { return r.pending; });

    var category = document.getElementById('filter-category').value;
    var severity = document.getElementById('filter-severity').value;
    var dateFilter = document.getElementById('filter-date').value;
    var sort = document.getElementById('filter-sort').value;

    var filtered = base.filter(function (r) {
      if (category && r.type !== category) return false;
      if (severity && r.severity !== severity) return false;
      if (dateFilter) {
        var created = new Date(r.createdAt);
        var now = new Date();
        if (dateFilter === 'today') {
          if (created.toDateString() !== now.toDateString()) return false;
        } else if (dateFilter === 'week') {
          if (created < new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)) return false;
        } else if (dateFilter === 'month') {
          if (created < new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)) return false;
        }
      }
      return true;
    });

    filtered.sort(function (a, b) {
      var da = new Date(a.createdAt).getTime();
      var db = new Date(b.createdAt).getTime();
      return sort === 'oldest' ? da - db : db - da;
    });

    renderReportsList(filtered);
  }

  function updateAnalyticsChart(reports) {
    var canvas = document.getElementById('damage-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    var typeKeys = ['pothole', 'alligator_crack', 'longitudinal_crack', 'transverse_crack', 'intact_road'];
    var labels = ['Pothole', 'Alligator Crack', 'Longitudinal Crack', 'Transverse Crack', 'Intact Road'];
    var colors = ['#ef4444', '#a855f7', '#f97316', '#eab308', '#14b8a6'];
    var counts = typeKeys.map(function (key) {
      return reports.filter(function (r) { return r.type === key; }).length;
    });

    if (chartInstance) {
      chartInstance.data.datasets[0].data = counts;
      chartInstance.update();
      return;
    }

    chartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels: labels, datasets: [{ data: counts, backgroundColor: colors, borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { color: '#94a3b8', precision: 0 }, grid: { color: 'rgba(148,163,184,0.1)' } },
          x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
        },
      },
    });
  }

  function switchTab(tab) {
    currentTab = tab;
    document.getElementById('tab-accepted').classList.toggle('active', tab === 'accepted');
    document.getElementById('tab-pending').classList.toggle('active', tab === 'pending');
    renderFilteredList();
  }

  function switchView(view) {
    currentView = view;
    document.getElementById('view-map-btn').classList.toggle('active', view === 'map');
    document.getElementById('view-analytics-btn').classList.toggle('active', view === 'analytics');
    document.getElementById('admin-map').classList.toggle('hidden', view !== 'map');
    document.getElementById('admin-analytics').classList.toggle('hidden', view !== 'analytics');
    if (view === 'map' && typeof mainMap !== 'undefined' && mainMap) {
      mainMap.invalidateSize();
    }
  }

  function bindDashboardControls() {
    document.getElementById('tab-accepted').addEventListener('click', function () { switchTab('accepted'); });
    document.getElementById('tab-pending').addEventListener('click', function () { switchTab('pending'); });
    document.getElementById('view-map-btn').addEventListener('click', function () { switchView('map'); });
    document.getElementById('view-analytics-btn').addEventListener('click', function () { switchView('analytics'); });

    ['filter-category', 'filter-severity', 'filter-date', 'filter-sort'].forEach(function (id) {
      document.getElementById(id).addEventListener('change', renderFilteredList);
    });
  }

  function renderReportsList(allReports) {
    var list = document.getElementById('admin-reports-list');
    var empty = document.getElementById('admin-empty-state');
    list.innerHTML = '';

    if (allReports.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');

    allReports.forEach(function (report) {
      var row = document.createElement('div');
      row.className = 'report-row';
      row.dataset.reportId = report.id;

      var actionsHtml =
        '<div class="report-row-actions">' +
          '<button class="btn-delete" data-id="' + report.id + '" type="button">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg> Delete report' +
          '</button>' +
        '</div>';

      var reporterHtml =
        '<div class="report-row-reporter-box">' +
          '<div class="reporter-row"><span class="reporter-row-label">Reporter\'s Name</span>' +
            (report.reporterName
              ? '<span class="reporter-row-value">' + escapeHtml(report.reporterName) + '</span>'
              : '<span class="reporter-row-value reporter-row-empty">Not provided</span>') +
          '</div>' +
          '<div class="reporter-row"><span class="reporter-row-label">Reporter\'s Email</span>' +
            (report.reporterEmail
              ? '<span class="reporter-row-value">' + escapeHtml(report.reporterEmail) + '</span>'
              : '<span class="reporter-row-value reporter-row-empty">Not provided</span>') +
          '</div>' +
          '<div class="reporter-row"><span class="reporter-row-label">Reported duration</span>' +
            '<span class="reporter-row-value' + (DURATION_LABELS[report.duration] ? '' : ' reporter-row-empty') + '">' +
              (DURATION_LABELS[report.duration] || 'Not specified') +
            '</span>' +
          '</div>' +
          '<div class="reporter-row severity-row">' +
            '<span class="reporter-row-label">Severity</span>' +
            '<select class="severity-select" data-id="' + report.id + '">' +
              '<option value=""' + (!report.severity ? ' selected' : '') + '>Not set</option>' +
              '<option value="low"' + (report.severity === 'low' ? ' selected' : '') + '>Low</option>' +
              '<option value="moderate"' + (report.severity === 'moderate' ? ' selected' : '') + '>Moderate</option>' +
              '<option value="severe"' + (report.severity === 'severe' ? ' selected' : '') + '>Severe</option>' +
            '</select>' +
          '</div>' +
          '<div class="reporter-row severity-row">' +
            '<span class="reporter-row-label">Repair status</span>' +
            '<div class="repair-status-buttons">' +
              (report.pending
                ? '<button class="btn-approve-pending" data-id="' + report.id + '" type="button">' +
                    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Approve' +
                  '</button>'
                : '<button class="btn-dispatch' + (report.teamDispatched ? ' btn-dispatch-active' : '') + '" data-id="' + report.id + '" type="button"' + (report.resolved ? ' disabled' : '') + '>' +
                    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg> ' +
                    (report.teamDispatched ? 'Team Dispatched' : 'Send Team') +
                  '</button>' +
                  '<button class="btn-resolve' + (report.resolved ? ' btn-resolve-active' : '') + '" data-id="' + report.id + '" type="button">' +
                    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> ' +
                    (report.resolved ? 'Resolved' : 'Mark Resolved') +
                  '</button>') +
            '</div>' +
          '</div>' +
        '</div>';

      var alsoConsideredHtml = '';
      if (report.alsoConsidered && report.alsoConsidered.length > 0) {
        alsoConsideredHtml =
          '<div class="also-considered-box">' +
            '<span class="also-considered-label">Also considered</span>' +
            report.alsoConsidered.map(function (item) {
              return '<div class="also-considered-row">' +
                '<span>' + escapeHtml(item.label) + '</span>' +
                '<span class="also-considered-conf">' + item.confidence + '%</span>' +
              '</div>';
            }).join('') +
          '</div>';
      }

      row.innerHTML =
        '<img src="' + report.imageDataUrl + '" alt="' + report.label + '" class="report-row-img" data-id="' + report.id + '" />' +
        '<div class="report-row-info">' +
          '<h5>' + report.label + ' &middot; ' + report.confidence + '%</h5>' +
          alsoConsideredHtml +
          reporterHtml +
          '<div class="report-row-meta">' +
            statusBadgeHtml(report) + ' &nbsp; ' +
            report.lat.toFixed(4) + ', ' + report.lng.toFixed(4) + '<br>' +
            formatTimestamp(new Date(report.createdAt)) +
          '</div>' +
          actionsHtml +
        '</div>';

      // Clicking the row (but not its thumbnail/buttons/select, which have
      // their own handlers) flies the map to this report and opens its popup.
      row.addEventListener('click', function (e) {
        if (e.target.closest('img, button, select')) return;
        if (currentView !== 'map') switchView('map');
        highlightReportRow(report.id);
        flyToReport(report.lat, report.lng, function () {
          openReportPopup(report.id);
        });
      });

      list.appendChild(row);
    });

    // Click a report's thumbnail to view it full-size in an inline lightbox.
    list.querySelectorAll('.report-row-img').forEach(function (img) {
      img.addEventListener('click', function () {
        openLightbox(img.src);
      });
    });

    list.querySelectorAll('.btn-delete').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var confirmed = window.confirm('Delete this report permanently? This cannot be undone.');
        if (confirmed) {
          deleteReport(btn.dataset.id);
        }
      });
    });

    // Admin can override the reporter's (or model-suggested) severity
    // at any time, independent of dispatch/delete.
    list.querySelectorAll('.severity-select').forEach(function (select) {
      select.addEventListener('change', function () {
        updateReport(select.dataset.id, { severity: select.value });
      });
    });

    // Toggle whether a repair team has been dispatched -- this is what
    // swaps the public map marker from a colored dot to a wrench icon.
    list.querySelectorAll('.btn-dispatch').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var report = allReports.find(function (r) { return r.id === btn.dataset.id; });
        var nextValue = !(report && report.teamDispatched);
        updateReport(btn.dataset.id, { teamDispatched: nextValue });
      });
    });

    // Marking a report resolved removes its dot from both maps (public
    // and admin) while keeping it listed here for record-keeping.
    list.querySelectorAll('.btn-resolve').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var report = allReports.find(function (r) { return r.id === btn.dataset.id; });
        var nextValue = !(report && report.resolved);
        updateReport(btn.dataset.id, { resolved: nextValue });
      });
    });

    // Approving a pending report makes it count toward "approved reports
    // nationwide" and shows its real damage-type color on the map instead
    // of the grey pending pin.
    list.querySelectorAll('.btn-approve-pending').forEach(function (btn) {
      btn.addEventListener('click', function () {
        updateReport(btn.dataset.id, { pending: false });
      });
    });
  }

  var zoomState = { scale: 1, panX: 0, panY: 0 };
  var MIN_ZOOM_SCALE = 1;
  var MAX_ZOOM_SCALE = 5;
  var isDragging = false;
  var dragStart = { x: 0, y: 0, panX: 0, panY: 0 };

  function applyZoomTransform() {
    var img = document.getElementById('lightbox-image');
    img.style.transform = 'translate(' + zoomState.panX + 'px, ' + zoomState.panY + 'px) scale(' + zoomState.scale + ')';
    img.style.cursor = zoomState.scale > 1 ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in';
    document.getElementById('zoom-reset').textContent = Math.round(zoomState.scale * 100) + '%';
  }

  function setZoom(nextScale) {
    nextScale = Math.min(MAX_ZOOM_SCALE, Math.max(MIN_ZOOM_SCALE, nextScale));
    if (nextScale === MIN_ZOOM_SCALE) {
      zoomState.panX = 0;
      zoomState.panY = 0;
    }
    zoomState.scale = nextScale;
    applyZoomTransform();
  }

  function resetZoom() {
    zoomState = { scale: 1, panX: 0, panY: 0 };
    applyZoomTransform();
  }

  function openLightbox(src) {
    document.getElementById('lightbox-image').src = src;
    document.getElementById('lightbox-overlay').classList.remove('hidden');
    resetZoom();
  }

  function closeLightbox() {
    document.getElementById('lightbox-overlay').classList.add('hidden');
    document.getElementById('lightbox-image').src = '';
    resetZoom();
  }

  function highlightReportRow(id) {
    var previous = document.querySelector('.report-row.highlighted');
    if (previous) previous.classList.remove('highlighted');

    var target = document.querySelector('[data-report-id="' + id + '"]');
    if (target) {
      target.classList.add('highlighted');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function bindLightboxEvents() {
    var img = document.getElementById('lightbox-image');
    var wrap = document.getElementById('lightbox-image-wrap');

    document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
    document.getElementById('lightbox-overlay').addEventListener('click', function (e) {
      if (e.target.id === 'lightbox-overlay') closeLightbox();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeLightbox();
    });

    document.getElementById('zoom-in').addEventListener('click', function () {
      setZoom(zoomState.scale + 0.5);
    });
    document.getElementById('zoom-out').addEventListener('click', function () {
      setZoom(zoomState.scale - 0.5);
    });
    document.getElementById('zoom-reset').addEventListener('click', resetZoom);

    // Scroll wheel to zoom in/out.
    wrap.addEventListener('wheel', function (e) {
      e.preventDefault();
      setZoom(zoomState.scale + (e.deltaY < 0 ? 0.3 : -0.3));
    }, { passive: false });

    // Double-click to toggle between 1x and 2.5x.
    img.addEventListener('dblclick', function () {
      setZoom(zoomState.scale > 1 ? 1 : 2.5);
    });

    // Drag to pan once zoomed in.
    img.addEventListener('mousedown', function (e) {
      if (zoomState.scale <= 1) return;
      isDragging = true;
      dragStart = { x: e.clientX, y: e.clientY, panX: zoomState.panX, panY: zoomState.panY };
      e.preventDefault();
    });
    window.addEventListener('mousemove', function (e) {
      if (!isDragging) return;
      zoomState.panX = dragStart.panX + (e.clientX - dragStart.x);
      zoomState.panY = dragStart.panY + (e.clientY - dragStart.y);
      applyZoomTransform();
    });
    window.addEventListener('mouseup', function () {
      if (isDragging) {
        isDragging = false;
        applyZoomTransform();
      }
    });
  }

  // ---- Auth ------------------------------------------------------
  var mapInitialized = false;

  function showView(view) {
    document.getElementById('admin-login-view').classList.toggle('hidden', view !== 'login');
    document.getElementById('admin-reset-view').classList.toggle('hidden', view !== 'reset');
    document.getElementById('admin-dashboard-view').classList.toggle('hidden', view !== 'dashboard');
    document.getElementById('admin-body').classList.toggle('admin-dashboard-body', view === 'dashboard');
  }

  function showDashboard() {
    showView('dashboard');
    if (!mapInitialized) {
      initMainMap('admin-map');
      mapInitialized = true;
    }
    renderDashboard();
  }

  function bindAuthEvents() {
    document.getElementById('login-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var email = document.getElementById('login-email').value.trim();
      var password = document.getElementById('login-pass').value;
      var errorEl = document.getElementById('login-error');
      errorEl.classList.add('hidden');

      sb.auth.signInWithPassword({ email: email, password: password }).then(function (res) {
        if (res.error) {
          errorEl.textContent = res.error.message || 'Invalid email or password.';
          errorEl.classList.remove('hidden');
          return;
        }
        showDashboard();
      });
    });

    document.getElementById('forgot-password-link').addEventListener('click', function () {
      var email = document.getElementById('login-email').value.trim();
      if (!email) {
        alert('Enter your email above first, then click "Forgot password?"');
        return;
      }
      sb.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin + window.location.pathname,
      }).then(function (res) {
        if (res.error) {
          alert('Could not send reset email: ' + res.error.message);
        } else {
          alert('Password reset link sent to ' + email + '. Check your inbox.');
        }
      });
    });

    document.getElementById('reset-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var newPassword = document.getElementById('reset-new-pass').value;
      var errorEl = document.getElementById('reset-error');
      var successEl = document.getElementById('reset-success');
      errorEl.classList.add('hidden');

      sb.auth.updateUser({ password: newPassword }).then(function (res) {
        if (res.error) {
          errorEl.textContent = res.error.message || 'Something went wrong.';
          errorEl.classList.remove('hidden');
          return;
        }
        successEl.classList.remove('hidden');
        setTimeout(showDashboard, 1200);
      });
    });

    document.getElementById('sign-out').addEventListener('click', function () {
      sb.auth.signOut().then(function () {
        showView('login');
      });
    });

    document.getElementById('open-change-password').addEventListener('click', function () {
      document.getElementById('change-password-modal').classList.remove('hidden');
    });
    document.getElementById('close-change-password').addEventListener('click', closeChangePasswordModal);
    document.getElementById('change-password-modal').addEventListener('click', function (e) {
      if (e.target.id === 'change-password-modal') closeChangePasswordModal();
    });

    document.getElementById('change-password-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var currentEmail = document.getElementById('current-email').value.trim();
      var currentPassword = document.getElementById('current-password').value;
      var newPassword = document.getElementById('new-password').value;
      var confirmPassword = document.getElementById('confirm-password').value;
      var errorEl = document.getElementById('change-password-error');
      var successEl = document.getElementById('change-password-success');
      errorEl.classList.add('hidden');
      successEl.classList.add('hidden');

      if (newPassword !== confirmPassword) {
        errorEl.textContent = "New passwords don't match.";
        errorEl.classList.remove('hidden');
        return;
      }

      sb.auth.getUser().then(function (userRes) {
        var loggedInEmail = userRes.data && userRes.data.user && userRes.data.user.email;
        if (!loggedInEmail || currentEmail.toLowerCase() !== loggedInEmail.toLowerCase()) {
          errorEl.textContent = "That email doesn't match your logged-in account.";
          errorEl.classList.remove('hidden');
          return;
        }

        // Re-verify the current password before allowing the change --
        // protects against someone using an already-unlocked, signed-in
        // session to silently take over the account.
        sb.auth.signInWithPassword({ email: currentEmail, password: currentPassword }).then(function (reauthRes) {
          if (reauthRes.error) {
            errorEl.textContent = 'Current password is incorrect.';
            errorEl.classList.remove('hidden');
            return;
          }

          sb.auth.updateUser({ password: newPassword }).then(function (res) {
            if (res.error) {
              errorEl.textContent = res.error.message || 'Something went wrong.';
              errorEl.classList.remove('hidden');
              return;
            }
            successEl.classList.remove('hidden');
            document.getElementById('change-password-form').reset();
            setTimeout(closeChangePasswordModal, 1500);
          });
        });
      });
    });
  }

  function closeChangePasswordModal() {
    document.getElementById('change-password-modal').classList.add('hidden');
    document.getElementById('change-password-error').classList.add('hidden');
    document.getElementById('change-password-success').classList.add('hidden');
    document.getElementById('change-password-form').reset();
  }

  function initAuth() {
    bindAuthEvents();

    // Arriving via a "reset password" email link fires this event --
    // show the reset-password screen instead of the normal login/dashboard.
    sb.auth.onAuthStateChange(function (event) {
      if (event === 'PASSWORD_RECOVERY') {
        showView('reset');
      }
    });

    sb.auth.getSession().then(function (res) {
      var session = res.data && res.data.session;
      if (session) {
        showDashboard();
      } else {
        showView('login');
      }
    });
  }

  function init() {
    initAuth();
    subscribe(function () {
      // Only re-render the dashboard if it's actually visible -- avoids
      // touching map/list DOM before login or while on the reset screen.
      if (!document.getElementById('admin-dashboard-view').classList.contains('hidden')) {
        renderDashboard();
      }
    });
    window.onMapMarkerClick = highlightReportRow;

    bindLightboxEvents();
    bindDashboardControls();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
