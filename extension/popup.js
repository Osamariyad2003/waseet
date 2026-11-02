const API = "http://localhost:8000";
const FRONTEND = "http://localhost:3000";
const ADMIN = "http://localhost:3001";

const $ = (id) => document.getElementById(id);
const log = $("log");

function addLog(msg, cls = "") {
  const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
  const div = document.createElement("div");
  div.className = `log-line ${cls}`;
  div.textContent = `[${ts}] ${msg}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function clearLog() {
  log.innerHTML = "";
}

function setBadge(id, ok, label) {
  const el = $(id);
  el.textContent = label || (ok ? "OK" : "FAIL");
  el.className = `status-badge ${ok ? "badge-ok" : "badge-fail"}`;
}

async function checkHealth(url, label, badgeId) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (r.ok) {
      setBadge(badgeId, true, "online");
      addLog(`${label} is online`, "log-ok");
      return true;
    }
    setBadge(badgeId, false, `HTTP ${r.status}`);
    addLog(`${label} returned ${r.status}`, "log-err");
    return false;
  } catch (e) {
    setBadge(badgeId, false, "offline");
    addLog(`${label} unreachable: ${e.message}`, "log-err");
    return false;
  }
}

async function checkRedirect(app) {
  try {
    const r = await fetch(`${API}/auth/paypal/redirect?app=${app}`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await r.json();
    if (r.ok && data.authorize_url) {
      addLog(`PayPal redirect (${app}): OK`, "log-ok");
      return data.authorize_url;
    }
    const errMsg = data?.error?.message || data?.detail || JSON.stringify(data);
    addLog(`PayPal redirect (${app}) failed: ${errMsg}`, "log-err");
    return null;
  } catch (e) {
    addLog(`PayPal redirect (${app}) error: ${e.message}`, "log-err");
    return null;
  }
}

async function checkCallbackEndpoint() {
  try {
    const r = await fetch(`${API}/auth/paypal/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "test-invalid-code", app: "escrow" }),
      signal: AbortSignal.timeout(5000),
    });
    const data = await r.json();
    if (r.status === 401 || r.status === 400) {
      setBadge("s-callback", true, "reachable");
      addLog("Callback endpoint reachable (rejects bad code as expected)", "log-ok");
      return true;
    }
    setBadge("s-callback", false, `HTTP ${r.status}`);
    addLog(`Callback endpoint unexpected status: ${r.status}`, "log-err");
    return false;
  } catch (e) {
    setBadge("s-callback", false, "error");
    addLog(`Callback endpoint error: ${e.message}`, "log-err");
    return false;
  }
}

function parseAuthorizeUrl(url) {
  try {
    const u = new URL(url);
    return {
      clientId: u.searchParams.get("client_id") || "—",
      redirectUri: u.searchParams.get("redirect_uri") || "—",
      scope: u.searchParams.get("scope") || "—",
      responseType: u.searchParams.get("response_type") || "—",
    };
  } catch {
    return null;
  }
}

async function runFullCheck() {
  clearLog();
  addLog("Starting full check...", "log-info");
  $("btn-run").disabled = true;

  // 1. Service health
  addLog("--- Service Health ---", "log-dim");
  const backendOk = await checkHealth(`${API}/health`, "Backend :8000", "s-backend");
  await checkHealth(FRONTEND, "Frontend :3000", "s-frontend");
  await checkHealth(ADMIN, "Admin :3001", "s-admin");

  if (!backendOk) {
    addLog("Backend is down — cannot test OAuth endpoints.", "log-err");
    $("btn-run").disabled = false;
    return;
  }

  // 2. PayPal OAuth endpoints
  addLog("--- PayPal OAuth ---", "log-dim");
  const escrowUrl = await checkRedirect("escrow");
  const adminUrl = await checkRedirect("admin");

  if (escrowUrl || adminUrl) {
    setBadge("s-paypal", true, "configured");
    setBadge("s-redirect", true, "OK");

    const parsed = parseAuthorizeUrl(escrowUrl || adminUrl);
    if (parsed) {
      $("url-details").style.display = "block";
      $("d-client-id").textContent = parsed.clientId;
      $("d-redirect-uri").textContent = parsed.redirectUri;
      $("d-scope").textContent = parsed.scope;

      addLog(`client_id: ${parsed.clientId.substring(0, 20)}...`, "log-info");
      addLog(`redirect_uri: ${parsed.redirectUri}`, "log-info");
      addLog(`scope: ${parsed.scope}`, "log-info");
      addLog(`response_type: ${parsed.responseType}`, "log-info");

      // Validate redirect_uri
      if (parsed.redirectUri.includes("localhost:3000/en/login/paypal/callback")) {
        addLog("Escrow redirect_uri format is correct", "log-ok");
      } else {
        addLog("WARNING: redirect_uri may not match PayPal app config", "log-err");
      }
    }
  } else {
    setBadge("s-paypal", false, "not configured");
    setBadge("s-redirect", false, "FAIL");
  }

  // 3. Callback endpoint
  await checkCallbackEndpoint();

  // 4. Check callback pages exist
  addLog("--- Callback Pages ---", "log-dim");
  try {
    const escrowCb = await fetch(`${FRONTEND}/en/login/paypal/callback`, {
      signal: AbortSignal.timeout(8000),
    });
    if (escrowCb.ok) {
      addLog("Frontend callback page: exists", "log-ok");
    } else {
      addLog(`Frontend callback page: HTTP ${escrowCb.status}`, "log-err");
    }
  } catch (e) {
    addLog(`Frontend callback page: ${e.message}`, "log-err");
  }

  try {
    const adminCb = await fetch(`${ADMIN}/en/login/paypal/callback`, {
      signal: AbortSignal.timeout(8000),
    });
    if (adminCb.ok) {
      addLog("Admin callback page: exists", "log-ok");
    } else {
      addLog(`Admin callback page: HTTP ${adminCb.status}`, "log-err");
    }
  } catch (e) {
    addLog(`Admin callback page: ${e.message}`, "log-err");
  }

  addLog("--- Check complete ---", "log-info");
  $("btn-run").disabled = false;
}

async function testOAuthFlow(app) {
  clearLog();
  addLog(`Testing ${app} OAuth flow...`, "log-info");

  const url = await checkRedirect(app);
  if (!url) {
    addLog("Cannot get authorize URL. Is the backend running?", "log-err");
    return;
  }

  addLog(`Opening PayPal authorize page...`, "log-info");
  addLog(`URL: ${url}`, "log-dim");

  chrome.tabs.create({ url });
}

// Wire up buttons
$("btn-run").addEventListener("click", runFullCheck);
$("btn-escrow").addEventListener("click", () => testOAuthFlow("escrow"));
$("btn-admin-flow").addEventListener("click", () => testOAuthFlow("admin"));

// Auto-run health check on open
(async () => {
  const backendOk = await checkHealth(`${API}/health`, "Backend", "s-backend");
  await checkHealth(FRONTEND, "Frontend", "s-frontend");
  await checkHealth(ADMIN, "Admin", "s-admin");
  $("btn-run").disabled = false;
  if (backendOk) {
    addLog("Services checked. Click 'Run Full Check' for details.", "log-info");
  }
})();
