/* Shared frontend runtime: auth/session, API helper, nav rendering,
   and small UI utilities reused across every page (login, requester,
   queue, assessment, compliance). No framework, no build step -- a
   declared stand-in for the React SPA
   architecture/TASD-v1.0.md section 9.1 specifies. See
   IMPLEMENTATION-NOTES.md.

   Every action here calls the real backend API; nothing is mocked.
   Server-side RBAC is the actual enforcement -- this file only hides/
   shows controls for a cleaner UX and re-checks nothing it doesn't
   also send to the server. */

const APP = (() => {
  const TOKEN_KEY = "poc_workflow_token";
  const ROLE_KEY = "poc_workflow_role";
  const USERID_KEY = "poc_workflow_user_id";
  const USERNAME_KEY = "poc_workflow_username";

  function saveSession(token) {
    localStorage.setItem(TOKEN_KEY, token);
    const payload = decodeJwt(token);
    if (payload) {
      localStorage.setItem(ROLE_KEY, payload.role || "");
      localStorage.setItem(USERID_KEY, payload.sub || "");
    }
  }

  function decodeJwt(token) {
    try {
      const part = token.split(".")[1];
      return JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    } catch {
      return null;
    }
  }

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function getRole() { return localStorage.getItem(ROLE_KEY); }
  function getUserId() { return localStorage.getItem(USERID_KEY); }
  function getUsername() { return localStorage.getItem(USERNAME_KEY); }
  function setUsername(u) { localStorage.setItem(USERNAME_KEY, u); }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(USERID_KEY);
    window.location.href = "/login";
  }

  function requireAuth() {
    if (!getToken()) {
      window.location.href = "/login";
      return false;
    }
    return true;
  }

  // Landing dashboard per role after login.
  const HOME_BY_ROLE = {
    Requester: "/requester",
    SecurityReviewer: "/queue",
    EnvironmentOwner: "/queue",
    FinalApprover: "/queue",
    ComplianceAuditor: "/compliance",
    PlatformOwner: "/queue",
  };
  function homeForRole(role) { return HOME_BY_ROLE[role] || "/queue"; }

  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => null);
    if (!res.ok) {
      const err = new Error("API error " + res.status);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  function errorMessage(e) {
    if (e && e.body) {
      if (typeof e.body === "string") return e.body;
      if (e.body.detail) {
        return typeof e.body.detail === "string" ? e.body.detail : JSON.stringify(e.body.detail, null, 2);
      }
      return JSON.stringify(e.body, null, 2);
    }
    return (e && e.message) || String(e);
  }

  function showError(targetId, e) {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.textContent = errorMessage(e);
    el.classList.remove("hidden");
  }
  function clearError(targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.textContent = "";
    el.classList.add("hidden");
  }
  function showSuccess(targetId, msg) {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  const ALL_ROLES = [
    "Requester",
    "SecurityReviewer",
    "EnvironmentOwner",
    "FinalApprover",
    "ComplianceAuditor",
    "PlatformOwner",
  ];

  const NAV_LINKS = [
    { href: "/requester", label: "Requester Portal", roles: ["Requester"] },
    { href: "/queue", label: "Assessment Queue", roles: ["SecurityReviewer", "EnvironmentOwner", "FinalApprover", "PlatformOwner"] },
    { href: "/compliance", label: "Compliance", roles: ["ComplianceAuditor", "PlatformOwner"] },
    { href: "/od-registry", label: "Organizational Decisions", roles: ["PlatformOwner"] },
  ];

  function renderHeader(activePath) {
    const header = document.getElementById("app-header");
    if (!header) return;
    const role = getRole();
    const username = getUsername();

    if (!role) {
      header.innerHTML = `<div class="brand">POC Security Assessment &amp; Approval Workflow</div>`;
      return;
    }

    const links = NAV_LINKS.filter((l) => l.roles.includes(role))
      .map((l) => `<a href="${l.href}" class="${activePath === l.href ? "active" : ""}">${l.label}</a>`)
      .join("");

    header.innerHTML = `
      <div class="brand">POC Security Assessment &amp; Approval Workflow</div>
      <nav class="app-nav">
        ${links}
      </nav>
      <div class="app-user">
        ${username ? username : ""} <span class="role-badge">${role}</span>
        <button class="navlink secondary" onclick="APP.logout()">Logout</button>
      </div>
    `;
  }

  function pill(text, cls) {
    return `<span class="pill ${cls || (text || "").toLowerCase().replace(/[^a-z]/g, "")}">${text}</span>`;
  }

  function provenanceBadge(tag) {
    const human = tag !== "AI_ASSERTION" && tag !== "AI_ASSUMPTION" && tag !== "MISSING_EVIDENCE";
    return `<span class="provenance-badge ${human ? "human" : ""}">${tag}</span>`;
  }

  function outcomePillClass(outcome) {
    if (outcome === "GO") return "go";
    if (outcome === "NO-GO") return "nogo";
    return "insufficient";
  }

  return {
    saveSession,
    decodeJwt,
    getToken,
    getRole,
    getUserId,
    getUsername,
    setUsername,
    logout,
    requireAuth,
    homeForRole,
    api,
    errorMessage,
    showError,
    clearError,
    showSuccess,
    renderHeader,
    pill,
    provenanceBadge,
    outcomePillClass,
    ALL_ROLES,
  };
})();
