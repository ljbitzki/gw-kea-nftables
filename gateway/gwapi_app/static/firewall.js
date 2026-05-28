const state = {
  rules: [],
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
  const dport = normalizeBlank(el("dport").value);

  if (id) payload.id = id;
  if (description) payload.description = description;
  if (src) payload.src = src;
  if (dst) payload.dst = dst;
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
}

function fillForm(rule) {
  state.editingId = rule.id;
  el("ruleId").value = rule.id || "";
  el("description").value = rule.description || "";
  el("action").value = rule.action || "allow";
  el("proto").value = rule.proto || "all";
  el("src").value = rule.src || "";
  el("dst").value = rule.dst || "";
  el("dport").value = rule.dport || "";
  el("formTitle").textContent = "Editar regra";
  el("saveRule").textContent = "Atualizar regra";
  el("positionField").style.display = "none";
  updateDportState();
  window.scrollTo({ top: 0, behavior: "smooth" });
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
      <td>${escapeHtml(rule.src || "qualquer")}</td>
      <td>${escapeHtml(rule.dst || "qualquer")}</td>
      <td>${escapeHtml(rule.dport || "-")}</td>
      <td>${escapeHtml(rule.description || "-")}</td>
      <td>
        <div class="table-actions">
          <button class="ghost" type="button" data-action="edit" data-id="${escapeHtml(rule.id)}">Editar</button>
          <button class="danger" type="button" data-action="delete" data-id="${escapeHtml(rule.id)}">Remover</button>
        </div>
      </td>
    </tr>
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
  state.rules = firewall.rules || [];
  renderRules();
  setStatus("Estado carregado", "ok");
}

el("proto").addEventListener("change", updateDportState);
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
