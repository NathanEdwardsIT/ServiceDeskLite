(function () {
  // Auto-refresh SLA timers on list/kanban views every 60s
  if (document.querySelector(".sla-timer") || document.getElementById("kanban-board")) {
    setInterval(() => {
      fetch("/api/v1/tickets/stats")
        .then((r) => r.json())
        .then((stats) => {
          document.querySelectorAll(".queue-stats .stat-value").forEach((el, i) => {
            const vals = [stats.total_open, stats.breached_sla, stats.escalated, stats.unassigned];
            if (vals[i] !== undefined) el.textContent = vals[i];
          });
        })
        .catch(() => {});
    }, 60000);
  }

  // Priority matrix live preview on new ticket form
  const impactEl = document.getElementById("impact-select");
  const urgencyEl = document.getElementById("urgency-select");
  const priorityPreview = document.getElementById("priority-preview");
  const matrix = window.PRIORITY_MATRIX || {};

  function updatePriorityPreview() {
    if (!impactEl || !urgencyEl || !priorityPreview) return;
    const key = impactEl.value + ":" + urgencyEl.value;
    const p = matrix[key] || "medium";
    priorityPreview.textContent = p;
    priorityPreview.className = "badge priority-" + p;
  }

  impactEl?.addEventListener("change", updatePriorityPreview);
  urgencyEl?.addEventListener("change", updatePriorityPreview);
  updatePriorityPreview();
})();
