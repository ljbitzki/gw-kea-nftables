const state = {
  summary: null,
  leases: [],
  reservations: [],
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

function resetReservationForm() {
  state.editingId = null;
  el("reservationForm").reset();
  el("reservationSubnet").value = "1";
  el("reservationFormTitle").textContent = "Nova reservation";
  el("saveReservation").textContent = "Salvar reservation";
}

function buildReservationPayload() {
  const payload = {
    subnet_id: Number(el("reservationSubnet").value || 1),
    ip_address: normalizeBlank(el("reservationIp").value),
    hw_address: normalizeBlank(el("reservationMac").value),
  };

  const hostname = normalizeBlank(el("reservationHostname").value);
  if (hostname) payload.hostname = hostname;
  return payload;
}

function fillReservationForm(reservation) {
  state.editingId = reservation.id;
  el("reservationSubnet").value = reservation.subnet_id || 1;
  el("reservationIp").value = reservation.ip_address || "";
  el("reservationMac").value = reservation.hw_address || "";
  el("reservationHostname").value = reservation.hostname || "";
  el("reservationFormTitle").textContent = "Editar reservation";
  el("saveReservation").textContent = "Atualizar reservation";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function renderSummary() {
  const summary = state.summary || {};
  const config = summary.config || {};
  const subnets = config.subnets || [];

  el("dhcpSummary").textContent = `${summary.leases_count || 0} leases · ${summary.reservations_count || 0} reservations`;

  const body = el("subnetsBody");
  if (!subnets.length) {
    body.innerHTML = '<div class="muted">Nenhuma subnet encontrada.</div>';
    return;
  }

  body.innerHTML = subnets.map((subnet) => `
    <article class="summary-box">
      <strong>Subnet ${escapeHtml(subnet.id)} · ${escapeHtml(subnet.subnet)}</strong>
      <dl>
        <dt>Pool</dt>
        <dd>${escapeHtml((subnet.pools || []).join(", ") || "-")}</dd>
        <dt>DNS</dt>
        <dd>${escapeHtml((subnet.options || {})["domain-name-servers"] || "-")}</dd>
        <dt>Domínio</dt>
        <dd>${escapeHtml((subnet.options || {})["domain-name"] || "-")}</dd>
        <dt>Router</dt>
        <dd>${escapeHtml((subnet.options || {}).routers || "-")}</dd>
        <dt>Reservations</dt>
        <dd>${escapeHtml(subnet.reservations_count || 0)}</dd>
      </dl>
    </article>
  `).join("");
}

function renderReservations() {
  const tbody = el("reservationsBody");
  if (!state.reservations.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">Nenhuma reservation cadastrada.</td></tr>';
    return;
  }

  tbody.innerHTML = state.reservations.map((reservation) => `
    <tr>
      <td>${escapeHtml(reservation.subnet_id)}</td>
      <td><strong>${escapeHtml(reservation.ip_address)}</strong></td>
      <td><code>${escapeHtml(reservation.hw_address)}</code></td>
      <td>${escapeHtml(reservation.hostname || "-")}</td>
      <td>
        <div class="table-actions">
          <button class="ghost" type="button" data-action="edit-reservation" data-id="${escapeHtml(reservation.id)}">Editar</button>
          <button class="danger" type="button" data-action="delete-reservation" data-id="${escapeHtml(reservation.id)}">Remover</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function hasReservationForLease(lease) {
  return state.reservations.some((reservation) => (
    reservation.ip_address === lease.address || reservation.hw_address === String(lease.hw_address || "").toLowerCase()
  ));
}

function renderLeases() {
  const tbody = el("leasesBody");
  if (!state.leases.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">Nenhum lease encontrado.</td></tr>';
    return;
  }

  tbody.innerHTML = state.leases.map((lease) => `
    <tr>
      <td><strong>${escapeHtml(lease.address)}</strong></td>
      <td><code>${escapeHtml(lease.hw_address || "-")}</code></td>
      <td>${escapeHtml(lease.hostname || "-")}</td>
      <td>${escapeHtml(lease.subnet_id || "-")}</td>
      <td>${escapeHtml(formatDate(lease.expire_at))}</td>
      <td><span class="tag proto">${escapeHtml(lease.state_label || "-")}</span></td>
      <td>
        ${hasReservationForLease(lease)
          ? '<span class="muted">reservado</span>'
          : `<button class="ghost" type="button" data-action="reserve-lease" data-address="${escapeHtml(lease.address)}" data-mac="${escapeHtml(lease.hw_address || "")}" data-hostname="${escapeHtml(lease.hostname || "")}" data-subnet="${escapeHtml(lease.subnet_id || 1)}">Reservar</button>`}
      </td>
    </tr>
  `).join("");
}

async function loadDhcp() {
  const [health, summary, leases, reservations] = await Promise.all([
    api("/health"),
    api("/dhcp/summary"),
    api("/dhcp/leases"),
    api("/dhcp/reservations"),
  ]);

  el("lanIf").textContent = `LAN: ${health.lan_if}`;
  el("wanIf").textContent = `WAN: ${health.wan_if}`;
  el("lanCidr").textContent = `CIDR: ${health.lan_cidr}`;
  state.summary = summary;
  state.leases = leases;
  state.reservations = reservations;
  renderSummary();
  renderReservations();
  renderLeases();
  setStatus("DHCP carregado", "ok");
}

el("refreshDhcp").addEventListener("click", () => {
  setStatus("Atualizando DHCP...");
  loadDhcp().catch((error) => setStatus(error.message, "error"));
});

el("applyReservations").addEventListener("click", async () => {
  try {
    setStatus("Aplicando reservations...");
    await api("/dhcp/apply", { method: "POST" });
    await loadDhcp();
    setStatus("Reservations aplicadas", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("newReservation").addEventListener("click", resetReservationForm);
el("cancelReservationEdit").addEventListener("click", resetReservationForm);

el("reservationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const editing = Boolean(state.editingId);
    const payload = buildReservationPayload();
    setStatus(editing ? "Atualizando reservation..." : "Criando reservation...");

    if (editing) {
      await api(`/dhcp/reservations/${encodeURIComponent(state.editingId)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/dhcp/reservations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }

    resetReservationForm();
    await loadDhcp();
    setStatus(editing ? "Reservation atualizada" : "Reservation criada", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el("reservationsBody").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const reservation = state.reservations.find((item) => item.id === button.dataset.id);
  if (button.dataset.action === "edit-reservation" && reservation) {
    fillReservationForm(reservation);
    return;
  }

  if (button.dataset.action === "delete-reservation") {
    const confirmed = window.confirm("Remover esta reservation?");
    if (!confirmed) return;
    try {
      setStatus("Removendo reservation...");
      await api(`/dhcp/reservations/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" });
      if (state.editingId === button.dataset.id) resetReservationForm();
      await loadDhcp();
      setStatus("Reservation removida", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }
});

el("leasesBody").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='reserve-lease']");
  if (!button) return;

  state.editingId = null;
  el("reservationSubnet").value = button.dataset.subnet || 1;
  el("reservationIp").value = button.dataset.address || "";
  el("reservationMac").value = button.dataset.mac || "";
  el("reservationHostname").value = button.dataset.hostname || "";
  el("reservationFormTitle").textContent = "Nova reservation";
  el("saveReservation").textContent = "Salvar reservation";
  window.scrollTo({ top: 0, behavior: "smooth" });
});

resetReservationForm();
loadDhcp().catch((error) => setStatus(error.message, "error"));
