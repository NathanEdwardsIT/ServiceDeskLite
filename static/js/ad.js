(function () {
  const cfg = window.AD_CONFIG || {};
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

  document.getElementById("user-filter")?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll("#user-list .ad-list-item").forEach((el) => {
      const name = el.getAttribute("data-name") || "";
      el.parentElement.style.display = name.includes(q) ? "" : "none";
    });
  });

  function roleOptions(selected) {
    return cfg.roles
      .map((r) => `<option value="${r}" ${r === selected ? "selected" : ""}>${esc(cfg.roleLabels[r] || r)}</option>`)
      .join("");
  }

  function managerOptions(selectedId) {
    let html = '<option value="">— None —</option>';
    (cfg.managers || []).forEach((m) => {
      html += `<option value="${m.id}" ${m.id === selectedId ? "selected" : ""}>${esc(m.name)}</option>`;
    });
    return html;
  }

  function groupCheckboxes(userGroupIds) {
    const ids = new Set(userGroupIds || []);
    return (cfg.groups || [])
      .map(
        (g) =>
          `<label class="chip"><input type="checkbox" disabled ${ids.has(g.id) ? "checked" : ""}> ${esc(g.name)}</label>`
      )
      .join(" ");
  }

  async function loadUserDetail(id) {
    const el = document.getElementById("user-detail");
    if (!el) return;
    try {
      const u = await fetch(`/ad/users/${id}`).then((r) => r.json());
      const canManage = cfg.canManage;
      const groupsHtml = (u.groups || [])
        .map(
          (g) =>
            `<span class="chip">${esc(g.name)}${
              canManage
                ? `<form method="post" action="/ad/users/${u.id}/groups/remove" class="inline-form"><input type="hidden" name="group_id" value="${g.id}"><button type="submit" class="chip-x">×</button></form>`
                : ""
            }</span>`
        )
        .join(" ");

      let addGroupForm = "";
      if (canManage) {
        const opts = (cfg.groups || [])
          .filter((g) => !(u.groups || []).some((ug) => ug.id === g.id))
          .map((g) => `<option value="${g.id}">${esc(g.name)}</option>`)
          .join("");
        addGroupForm = `<form method="post" action="/ad/users/${u.id}/groups/add" class="inline-form">
          <select name="group_id">${opts}</select><button type="submit" class="btn btn-sm">Add to group</button></form>`;
      }

      el.innerHTML = `
        <div class="detail-header">
          <h2>${esc(u.display_name)} ${u.is_active ? "" : '<span class="badge status-cancelled">Disabled</span>'}</h2>
          <p class="muted">${esc(u.upn)} · SAM: ${esc(u.sam)}</p>
        </div>
        ${canManage ? `
        <form method="post" action="/ad/users/${u.id}/update" class="ad-form grid-form">
          <div><label>Display name</label><input name="display_name" value="${esc(u.display_name)}" required></div>
          <div><label>Email</label><input name="email" type="email" value="${esc(u.email)}" required></div>
          <div><label>Department</label><input name="department" value="${esc(u.department || "")}"></div>
          <div><label>Job title</label><input name="job_title" value="${esc(u.job_title || "")}"></div>
          <div><label>App role</label><select name="role">${roleOptions(u.role)}</select></div>
          <div><label>Manager</label><select name="manager_id">${managerOptions(u.manager_id)}</select></div>
          <div class="checkbox-row"><label><input type="checkbox" name="role_sync_from_groups" value="true" ${u.role_sync_from_groups ? "checked" : ""}> Sync role from AD groups</label></div>
          <div class="checkbox-row"><label><input type="checkbox" name="is_active" value="true" ${u.is_active ? "checked" : ""}> Account enabled</label></div>
          <div class="full-width"><button type="submit" class="btn btn-primary">Save Changes</button></div>
        </form>
        <form method="post" action="/ad/users/${u.id}/reset-password" class="ad-form inline-row">
          <input name="new_password" placeholder="New password" required>
          <button type="submit" class="btn btn-sm">Reset Password</button>
        </form>` : `
        <dl class="detail-dl">
          <dt>Email</dt><dd>${esc(u.email)}</dd>
          <dt>Department</dt><dd>${esc(u.department || "—")}</dd>
          <dt>Role</dt><dd>${esc(cfg.roleLabels[u.role] || u.role)}</dd>
          <dt>Manager</dt><dd>${esc(u.manager || "—")}</dd>
        </dl>`}
        <h3>Group Membership</h3>
        <div class="chip-row">${groupsHtml || "<span class='muted'>No groups</span>"}</div>
        ${addGroupForm}
        <h3>Effective Permissions</h3>
        <div class="perm-tags">${(u.effective_permissions || []).map((p) => `<span class="perm-tag">${esc(cfg.permissionLabels[p] || p)}</span>`).join("")}</div>
      `;
    } catch (e) {
      el.innerHTML = `<p class="alert alert-error">Failed to load user.</p>`;
    }
  }

  async function loadGroupDetail(id) {
    const el = document.getElementById("group-detail");
    if (!el) return;
    try {
      const g = await fetch(`/ad/groups/${id}`).then((r) => r.json());
      const canManage = cfg.canManage;
      const members = (g.members || [])
        .map(
          (m) =>
            `<li>${esc(m.display_name)} <small>${esc(m.email)}</small>${
              canManage
                ? `<form method="post" action="/ad/groups/${g.id}/members/remove" class="inline-form"><input type="hidden" name="user_id" value="${m.id}"><button type="submit" class="btn btn-sm">Remove</button></form>`
                : ""
            }</li>`
        )
        .join("");

      el.innerHTML = `
        <div class="detail-header">
          <h2>${esc(g.name)}</h2>
          <p class="muted"><code>${esc(g.dn)}</code></p>
        </div>
        ${canManage ? `
        <form method="post" action="/ad/groups/${g.id}/update" class="ad-form grid-form">
          <div><label>Name</label><input name="name" value="${esc(g.name)}" required></div>
          <div><label>Type</label><select name="group_type"><option value="security" ${g.group_type === "security" ? "selected" : ""}>Security</option><option value="distribution" ${g.group_type === "distribution" ? "selected" : ""}>Distribution</option></select></div>
          <div><label>Mapped role</label><select name="mapped_role"><option value="">— None —</option>${roleOptions(g.mapped_role || "")}</select></div>
          <div><label>Role priority</label><input name="role_priority" type="number" value="${g.role_priority || 0}"></div>
          <div class="full-width"><label>Description</label><textarea name="description" rows="2">${esc(g.description || "")}</textarea></div>
          <div class="checkbox-row"><label><input type="checkbox" name="clear_mapped_role" value="true"> Clear mapped role</label></div>
          <div class="full-width">
            <button type="submit" class="btn btn-primary">Save Group</button>
            <button type="submit" formaction="/ad/groups/${g.id}/delete" formmethod="post" class="btn btn-danger" onclick="return confirm('Delete this group?')">Delete</button>
          </div>
        </form>` : `<p>${esc(g.description || "")}</p><p>Mapped role: <strong>${esc(g.mapped_role || "—")}</strong></p>`}
        <h3>Members (${g.member_count})</h3>
        <ul class="member-list">${members}</ul>
        ${canManage ? `<p><a href="/ad?tab=users" class="btn btn-sm">Add members via Users tab</a></p>` : ""}
      `;
    } catch (e) {
      el.innerHTML = `<p class="alert alert-error">Failed to load group.</p>`;
    }
  }

  async function loadPermissionsEditor(id) {
    const el = document.getElementById("permissions-panel");
    if (!el || !cfg.canManage) return;
    try {
      const g = await fetch(`/ad/groups/${id}`).then((r) => r.json());
      const granted = new Set(g.permissions || []);
      const rows = cfg.allPermissions
        .map(
          (p) => `
        <label class="perm-row">
          <input type="checkbox" name="perm_${p}" ${granted.has(p) ? "checked" : ""}>
          <span><strong>${esc(cfg.permissionLabels[p] || p)}</strong><small>${esc(p)}</small></span>
        </label>`
        )
        .join("");

      el.innerHTML = `
        <h2>Permissions: ${esc(g.name)}</h2>
        <p class="muted">These permissions are <em>added</em> to whatever the group's mapped role (${esc(g.mapped_role || "none")}) already provides.</p>
        <form method="post" action="/ad/groups/${g.id}/permissions" class="perm-editor">
          ${rows}
          <button type="submit" class="btn btn-primary">Save Permissions</button>
        </form>
      `;
    } catch (e) {
      el.innerHTML = `<p class="alert alert-error">Failed to load permissions.</p>`;
    }
  }

  window.confirmDeleteOu = function (e) {
    e.preventDefault();
    const sel = document.getElementById("delete-ou-select");
    if (!sel || !confirm("Delete OU " + sel.options[sel.selectedIndex].text + "?")) return false;
    e.target.form.action = "/ad/ous/" + sel.value + "/delete";
    e.target.form.submit();
    return false;
  };

  if (cfg.selectedId) {
    if (cfg.tab === "users") loadUserDetail(cfg.selectedId);
    if (cfg.tab === "groups") loadGroupDetail(cfg.selectedId);
    if (cfg.tab === "permissions") loadPermissionsEditor(cfg.selectedId);
  }
})();
