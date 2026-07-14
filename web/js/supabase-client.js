/**
 * Shared Supabase client. Loaded on both index.html and admin.html,
 * before store.js (which depends on window.sb existing).
 *
 * The URL and publishable key below are meant to be public -- they're
 * safe to ship in client-side JS. Actual data protection comes from the
 * Row Level Security policies set up in Supabase (see supabase_schema.sql),
 * not from keeping this key secret.
 */
var SUPABASE_URL = 'https://ngfdbsmvyonquczvcgha.supabase.co';
var SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_kdjPKEP_fr1FUzPJ3cW_rw_mKU5fdYE';

var sb = supabase.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
