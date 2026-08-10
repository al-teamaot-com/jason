const sectionCopy = {
  capabilities: ["Capabilities", "Discover registered Jason capabilities, versions, modes, providers, and governance requirements."],
  connectors: ["Connectors", "Review provider registrations, health, readiness, scopes, and dependency status without exposing credentials."],
  governance: ["Governance", "Inspect governing policies, risk classifications, approval requirements, and policy versions."],
  approvals: ["Approvals", "Human review queue for actions that require explicit organizational authority."],
  audit: ["Audit", "Search executions, decisions, evidence references, approvals, and policy outcomes."],
  identity: ["Identity & Access", "Review principals, organizations, roles, capability grants, and authority boundaries."],
  configuration: ["Configuration", "Inspect governed configuration values and schemas. Write controls are intentionally deferred."],
  secrets: ["Secrets", "View secret metadata, ownership, expiration, and rotation state. Secret values are never displayed."],
  stewardship: ["Platform Stewardship", "Track dependent platforms, API changes, deprecations, reviews, and retirement opportunities."],
  system: ["System", "Kernel health, orchestrator status, versions, deployment state, and diagnostic information."]
};

const nav = document.getElementById("nav");
const dashboard = document.getElementById("dashboard");
const generic = document.getElementById("generic");
const pageTitle = document.getElementById("page-title");
const pageSubtitle = document.getElementById("page-subtitle");
const genericTitle = document.getElementById("generic-title");
const genericCopy = document.getElementById("generic-copy");

function show(view) {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.dataset.view === view);
  });

  if (view === "dashboard") {
    dashboard.classList.add("active");
    generic.classList.remove("active");
    pageTitle.textContent = "Dashboard";
    pageSubtitle.textContent = "Governed operational visibility for Jason.";
    return;
  }

  const [title, copy] = sectionCopy[view] || ["Section", "Governed management surface pending."];
  dashboard.classList.remove("active");
  generic.classList.add("active");
  pageTitle.textContent = title;
  pageSubtitle.textContent = copy;
  genericTitle.textContent = title;
  genericCopy.textContent = copy;
}

nav.addEventListener("click", event => {
  const button = event.target.closest("[data-view]");
  if (button) show(button.dataset.view);
});

document.addEventListener("click", event => {
  const button = event.target.closest("[data-view-target]");
  if (button) show(button.dataset.viewTarget);
});
