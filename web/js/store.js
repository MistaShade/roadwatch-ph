/**
 * Report state, now backed by a real shared Supabase database instead of
 * localStorage -- this is what lets your whole team see the same live
 * data. The public API here (subscribe, getState, addReport, updateReport,
 * deleteReport) is intentionally identical to the old localStorage
 * version, so app.js/admin.js/map.js don't need to change at all.
 *
 * How it stays "live": on load we fetch all reports once, then subscribe
 * to Supabase Realtime, which pushes every insert/update/delete from
 * ANY connected browser (yours, a teammate's, the public site) into this
 * tab's local cache automatically.
 */

var TABLE = 'reports';

// Local in-memory cache, kept in sync via Realtime. Existing code reads
// this synchronously through getState(), same as it did with localStorage.
var reports = [];
var storeListeners = [];
var isReady = false;
var readyListeners = [];

function subscribe(fn) {
  storeListeners.push(fn);
  return function () {
    storeListeners = storeListeners.filter(function (l) { return l !== fn; });
  };
}

function notifyStore() {
  storeListeners.forEach(function (fn) { fn(getState()); });
}

// Fires once the initial fetch from Supabase completes -- useful if a
// page wants to know "has real data loaded yet" vs "still empty because
// we haven't fetched."
function onStoreReady(fn) {
  if (isReady) {
    fn();
  } else {
    readyListeners.push(fn);
  }
}

function getReports() {
  return reports.slice();
}

function getState() {
  var active = reports.filter(function (r) { return !r.resolved; });
  var pending = active.filter(function (r) { return r.pending; });
  var approved = active.filter(function (r) { return !r.pending; });
  var dispatched = approved.filter(function (r) { return r.teamDispatched; });
  var resolved = reports.filter(function (r) { return r.resolved; });
  return {
    reports: getReports(),
    counts: {
      total: reports.length,
      active: active.length,
      pending: pending.length,
      // "Approved reports nationwide" -- pending reports are visible on
      // the map (as a grey pin) but deliberately excluded from this count
      // until an admin approves them.
      approved: approved.length,
      dispatched: dispatched.length,
      underInspection: approved.length - dispatched.length,
      resolved: resolved.length,
    },
  };
}

// ---- DB row <-> app object mapping -----------------------------------
// The database uses snake_case columns; the rest of the app (app.js,
// admin.js, map.js) expects the same camelCase shape it always has.
// Keeping the mapping here means nothing else needs to know or care.

function rowToReport(row) {
  return {
    id: row.id,
    createdAt: row.created_at,
    lat: row.lat,
    lng: row.lng,
    type: row.type,
    label: row.label,
    confidence: row.confidence,
    color: row.color,
    alsoConsidered: row.also_considered || [],
    reporterName: row.reporter_name || '',
    reporterEmail: row.reporter_email || '',
    duration: row.duration || '',
    severity: row.severity || '',
    teamDispatched: !!row.team_dispatched,
    pending: row.pending === undefined ? true : !!row.pending,
    resolved: !!row.resolved,
    imageDataUrl: row.image_data_url,
  };
}

function reportToInsertRow(report) {
  return {
    lat: report.lat,
    lng: report.lng,
    type: report.type,
    label: report.label,
    confidence: report.confidence,
    color: report.color,
    also_considered: report.alsoConsidered || [],
    reporter_name: report.reporterName || '',
    reporter_email: report.reporterEmail || '',
    duration: report.duration || '',
    severity: report.severity || '',
    image_data_url: report.imageDataUrl,
  };
}

function patchToRow(patch) {
  var row = {};
  if ('severity' in patch) row.severity = patch.severity;
  if ('teamDispatched' in patch) row.team_dispatched = patch.teamDispatched;
  if ('resolved' in patch) row.resolved = patch.resolved;
  if ('pending' in patch) row.pending = patch.pending;
  return row;
}

// ---- Write operations ---------------------------------------------
// These fire the network request and return, without waiting -- the UI
// updates when Realtime echoes the change back (see subscribeRealtime
// below), not from these return values. This mirrors how the old
// synchronous localStorage version behaved from the caller's perspective.

function addReport(report) {
  sb.from(TABLE).insert(reportToInsertRow(report)).then(function (res) {
    if (res.error) {
      console.error('Failed to save report:', res.error);
      alert('Could not save your report. Please check your connection and try again.');
    }
  });
}

function updateReport(id, patch) {
  sb.from(TABLE).update(patchToRow(patch)).eq('id', id).then(function (res) {
    if (res.error) {
      console.error('Failed to update report:', res.error);
      alert('Could not save that change. Please check your connection and try again.');
    }
  });
}

function deleteReport(id) {
  sb.from(TABLE).delete().eq('id', id).then(function (res) {
    if (res.error) {
      console.error('Failed to delete report:', res.error);
      alert('Could not delete that report. Please check your connection and try again.');
    }
  });
}

// ---- Initial load + Realtime sync ----------------------------------

function loadInitialReports() {
  sb.from(TABLE)
    .select('*')
    .order('created_at', { ascending: false })
    .then(function (res) {
      if (res.error) {
        console.error('Failed to load reports:', res.error);
        return;
      }
      reports = res.data.map(rowToReport);
      isReady = true;
      readyListeners.forEach(function (fn) { fn(); });
      readyListeners = [];
      notifyStore();
    });
}

function subscribeRealtime() {
  sb.channel('reports-changes')
    .on('postgres_changes', { event: 'INSERT', schema: 'public', table: TABLE }, function (payload) {
      var incoming = rowToReport(payload.new);
      if (reports.some(function (r) { return r.id === incoming.id; })) return;
      reports = [incoming].concat(reports);
      notifyStore();
    })
    .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: TABLE }, function (payload) {
      var updated = rowToReport(payload.new);
      var existing = reports.find(function (r) { return r.id === updated.id; });
      // Safety net: if a live update ever arrives without the image (see
      // supabase_fix_image_bug.sql for the real cause/fix), don't let it
      // blank out an image we already know this report has.
      if (!updated.imageDataUrl && existing && existing.imageDataUrl) {
        updated.imageDataUrl = existing.imageDataUrl;
      }
      reports = reports.map(function (r) { return r.id === updated.id ? updated : r; });
      notifyStore();
    })
    .on('postgres_changes', { event: 'DELETE', schema: 'public', table: TABLE }, function (payload) {
      reports = reports.filter(function (r) { return r.id !== payload.old.id; });
      notifyStore();
    })
    .subscribe();
}

loadInitialReports();
subscribeRealtime();
