const state = {
  rules: [],
  groups: {},
  editingId: null,
};

const el = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setStatus(message, kind = "") {
  const line = el("statusLine");
  line.textContent = message;
  line.className = `status-line ${kind}`;
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({ error: "Resposta invalida" }));
  if (response.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Autenticação requerida");
  }
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function normalizeBlank(value) {
  const trimmed = String(value || "").trim();
  return trimmed.length ? trimmed : undefined;
}

function buildPayload(includePosition) {
  const proto = el("proto").value;
  const payload = {
    action: el("action").value,
    proto,
  };

  const id = normalizeBlank(el("ruleId").value);
  const description = normalizeBlank(el("description").value);
  const src = normalizeBlank(el("src").value);
  const dst = normalizeBlank(el("dst").value);
  const srcGroup = normalizeBlank(el("srcGroup").value);
  const dstGroup = normalizeBlank(el("dstGroup").value);
  const dport = normalizeBlank(el("dport").value);

  if (id) payload.id = id;
  if (description) payload.description = description;
  if (srcGroup) payload.src_group = srcGroup;
  else if (src) payload.src = src;
  if (dstGroup) payload.dst_group = dstGroup;
  else if (dst) payload.dst = dst;
  if (dport) payload.dport = Number(dport);
  if (includePosition) payload.position = el("position").value;

  return payload;
}

function updateDportState() {
  const proto = el("proto").value;
  const enabled = proto === "tcp" || proto === "udp";
  el("dport").disabled = !enabled;
  if (!enabled) {
    el("dport").value = "";
  }
}

function updateAddressState() {
  const srcGrouped = Boolean(el("srcGroup").value);
  const dstGrouped = Boolean(el("dstGroup").value);
  el("src").disabled = srcGrouped;
  el("dst").disabled = dstGrouped;
  if (srcGrouped) el("src").value = "";
  if (dstGrouped) el("dst").value = "";
}

function resetForm() {
  state.editingId = null;
  el("ruleForm").reset();
  el("action").value = "allow";
  el("proto").value = "tcp";
  el("position").value = "last";
  el("formTitle").textContent = "Nova regra";
  el("saveRule").textContent = "Salvar regra";
  el("positionField").style.display = "";
  updateDportState();
  updateAddressState();
}

function fillForm(rule) {
  state.editingId = rule.id;
  el("ruleId").value = rule.id || "";
  el("description").value = rule.description || "";
  el("action").value = rule.action || "allow";
  el("proto").value = rule.proto || "all";
  el("src").value = rule.src || "";
  el("srcGroup").value = rule.src_group || "";
  el("dst").value = rule.dst || "";
  el("dstGroup").value = rule.dst_group || "";
  el("dport").value = rule.dport || "";
  el("formTitle").textContent = "Editar regra";
  el("saveRule").textContent = "Atualizar regra";
  el("positionField").style.display = "none";
  updateDportState();
  updateAddressState();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderGroupOptions() {
  const options = ['<option value="">nenhum</option>']
    .concat(Object.entries(state.groups).map(([groupId, group]) => (
      `<option value="${escapeHtml(groupId)}">${escapeHtml(group.description || groupId)}</option>`
    )))
    .join("");

  const currentSrc = el("srcGroup").value;
  const currentDst = el("dstGroup").value;
  el("srcGroup").innerHTML = options;
  el("dstGroup").innerHTML = options;
  el("srcGroup").value = currentSrc;
  el("dstGroup").value = currentDst;
}

function formatAddress(rule, field) {
  const groupField = `${field}_group`;
  if (rule[groupField]) {
    const group = state.groups[rule[groupField]];
    return `@${group ? group.description : rule[groupField]}`;
  }
  return rule[field] || "qualquer";
}

function renderRules() {
  const tbody = el("rulesBody");
  el("ruleCount").textContent = `${state.rules.length} regra${state.rules.length === 1 ? "" : "s"}`;

  if (!state.rules.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">Nenhuma regra cadastrada.</td></tr>';
    return;
  }

  tbody.innerHTML = state.rules.map((rule) => `
    <tr>
      <td><strong>${escapeHtml(rule.id)}</strong></td>
      <td><span class="tag ${escapeHtml(rule.action)}">${escapeHtml(rule.action)}</span></td>
      <td><span class="tag proto">${escapeHtml(rule.proto || "all")}</span></td>
      <td>${escapeHtml(formatAddress(rule, "src"))}</td>
      <td>${escapeHtml(formatAddress(rule, "dst"))}</td>
      <td>${escapeHtml(rule.dport || "-")}</td>
      <td>${escapeHtml(rule.description || "-")}</td>
      <td>
        <div class="table-actions">
          ${rule.system ? '<span class="muted">sistema</span>' : `
            <button class="ghost" type="button" data-action="edit" data-id="${escapeHtml(rule.id)}">Editar</button>
            <button class="danger" type="button" data-action="delete" data-id="${escapeHtml(rule.id)}">Remover</button>
          `}
        </div>
      </td>
    </tr>
  `).join("");
}

function renderGroups() {
  const body = el("groupsBody");
  const entries = Object.entries(state.groups);
  if (!entries.length) {
    body.innerHTML = '<div class="muted">Nenhum grupo cadastrado.</div>';
    return;
  }

  body.innerHTML = entries.map(([groupId, group]) => `
    <article class="group-box">
      <div class="group-head">
        <div class="group-title">
          <strong>${escapeHtml(group.description || groupId)}</strong>
          <span class="muted">${escapeHtml(groupId)} · ${(group.members || []).length} membro${(group.members || []).length === 1 ? "" : "s"}</span>
        </div>
        ${group.system ? '<span class="tag proto">sistema</span>' : `<button class="danger" type="button" data-action="delete-group" data-group="${escapeHtml(groupId)}">Remover</button>`}
      </div>
      <form class="member-form" data-group="${escapeHtml(groupId)}">
        <input name="member" autocomplete="off" placeholder="10.88.0.100/32">
        <button class="ghost" type="submit">Adicionar</button>
      </form>
      <div class="member-list">
        ${(group.members || []).length ? group.members.map((member) => `
          <div class="member-row">
            <code>${escapeHtml(member)}</code>
            <button class="danger" type="button" data-action="delete-member" data-group="${escapeHtml(groupId)}" data-member="${escapeHtml(member)}">Remover</button>
          </div>
        `).join("") : '<span class="muted">Sem membros.</span>'}
      </div>
    </article>
  `).join("");
}

async function loadFirewall() {
  const [health, firewall] = await Promise.all([
    api("/health"),
    api("/firewall"),
  ]);

  el("lanIf").textContent = `LAN: ${health.lan_if}`;
  el("wanIf").textContent = `WAN: ${health.wan_if}`;
  el("lanCidr").textContent = `CIDR: ${health.lan_cidr}`;
  el("defaultPolicy").value = firewall.default_policy || "drop";
  state.groups = firewall.groups || {};
  state.rules = firewall.rules || [];
  renderGroupOptions();
  renderGroups();
  renderRules();
  setStatus("Estado carregado", "ok");
}

el("proto").addEventListener("change", updateDportState);
el("srcGroup").addEventListener("change", updateAddressState);
el("dstGroup").addEventListener("change", updateAddressState);
el("newRule").addEventListener("click", resetForm);
el("cancelEdit").addEventListener("click", resetForm);
el("refreshRules").addEventListener("click", () => {
  setStatus("Atualizando...");
  loadFirewall().catch((error) => setStatus(error.message, "error"));
});

el("applyRules").addEventListener("click", async () => {
  try {
    setStatus("Reaplicando ruleset...");
    await api("/firewall/apply", { method: "POST" });
    await loadFirewall();
    setStatus("Ruleset reaplicado", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("savePolicy").addEventListener("click", async () => {
  try {
    setStatus("Aplicando politica...");
    await api("/firewall/default", {
      method: "PUT",
      body: JSON.stringify({ policy: el("defaultPolicy").value }),
    });
    await loadFirewall();
    setStatus("Politica atualizada", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("groupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      id: normalizeBlank(el("groupId").value),
      description: normalizeBlank(el("groupDescription").value),
      members: [],
    };
    setStatus("Criando grupo...");
    await api("/firewall/groups", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    el("groupForm").reset();
    await loadFirewall();
    setStatus("Grupo criado", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("groupsBody").addEventListener("submit", async (event) => {
  const form = event.target.closest(".member-form");
  if (!form) return;
  event.preventDefault();

  const input = form.querySelector("input[name='member']");
  const member = normalizeBlank(input.value);
  if (!member) return;

  try {
    setStatus("Adicionando membro...");
    await api(`/firewall/groups/${encodeURIComponent(form.dataset.group)}/members`, {
      method: "POST",
      body: JSON.stringify({ member }),
    });
    input.value = "";
    await loadFirewall();
    setStatus("Membro adicionado", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("groupsBody").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const action = button.dataset.action;
  const groupId = button.dataset.group;

  try {
    if (action === "delete-member") {
      setStatus("Removendo membro...");
      await api(`/firewall/groups/${encodeURIComponent(groupId)}/members`, {
        method: "DELETE",
        body: JSON.stringify({ member: button.dataset.member }),
      });
      await loadFirewall();
      setStatus("Membro removido", "ok");
    }

    if (action === "delete-group") {
      const confirmed = window.confirm(`Remover o grupo ${groupId}?`);
      if (!confirmed) return;
      setStatus("Removendo grupo...");
      await api(`/firewall/groups/${encodeURIComponent(groupId)}`, { method: "DELETE" });
      await loadFirewall();
      setStatus("Grupo removido", "ok");
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("ruleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const editing = Boolean(state.editingId);
    const payload = buildPayload(!editing);
    setStatus(editing ? "Atualizando regra..." : "Criando regra...");

    if (editing) {
      await api(`/firewall/rules/${encodeURIComponent(state.editingId)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/firewall/rules", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }

    resetForm();
    await loadFirewall();
    setStatus(editing ? "Regra atualizada" : "Regra criada", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("rulesBody").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const id = button.dataset.id;
  const action = button.dataset.action;
  const rule = state.rules.find((item) => String(item.id) === id);

  if (action === "edit" && rule) {
    fillForm(rule);
    return;
  }

  if (action === "delete") {
    const confirmed = window.confirm(`Remover a regra ${id}?`);
    if (!confirmed) return;

    try {
      setStatus("Removendo regra...");
      await api(`/firewall/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.editingId === id) {
        resetForm();
      }
      await loadFirewall();
      setStatus("Regra removida", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }
});

resetForm();
loadFirewall().catch((error) => setStatus(error.message, "error"));
