const money = (value) => `$${value.toLocaleString('es-CO')}`;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

async function refreshDashboardCounts() {
  const response = await fetch('/api/dashboard/resumen', { cache: 'no-store' });
  if (!response.ok) return;
  const data = await response.json();
  const available = document.querySelector('#count-available');
  const inUse = document.querySelector('#count-in-use');
  if (available) available.textContent = data.disponibles;
  if (inUse) inUse.textContent = data.en_uso;
}

const inventoryModal = document.querySelector('#inventory-detail-modal');
if (inventoryModal) {
  const detailModal = document.querySelector('#inventory-detail-modal');
  const inUseRows = document.querySelector('#in-use-rows');
  const inUseStatus = document.querySelector('#in-use-status');
  const listView = document.querySelector('#inventory-list-view');
  const transferDetail = document.querySelector('#transfer-detail');
  const timeline = document.querySelector('#transfer-timeline');
  const warning = document.querySelector('#transfer-history-warning');
  const trackingStatus = document.querySelector('#location-tracking-status');
  const patientSummary = document.querySelector('#tracking-patient-summary');
  const patientName = document.querySelector('#tracking-patient-name');
  const patientDocument = document.querySelector('#tracking-patient-document');
  const searchInput = document.querySelector('#inventory-search');
  let inventoryCloseTimer = null;
  let inventory = [];
  let currentFilter = 'EN_USO';
  let inventoryPage = 1;
  let timelinePage = 1;
  let selectedHistory = [];
  const DEFAULT_INVENTORY_PAGE_SIZE = 4;
  const TIMELINE_PAGE_SIZE = 2;

  function closeInventoryModal() {
    if (!detailModal.open || detailModal.classList.contains('is-closing')) return;
    detailModal.classList.add('is-closing');
    inventoryCloseTimer = window.setTimeout(() => {
      if (detailModal.open) detailModal.close();
      detailModal.classList.remove('is-closing');
      inventoryCloseTimer = null;
    }, 160);
  }

  const controlStatusLabels = {
    DISPONIBLE: 'Disponible', PRESTADO: 'En uso', PENDIENTE_DEVOLUCION: 'Pendiente de devolución',
    EN_REVISION: 'En revisión', REPARACION: 'En revisión'
  };

  function inventoryPageSize() {
    return currentFilter === 'DISPONIBLE' ? 15 : DEFAULT_INVENTORY_PAGE_SIZE;
  }

  function renderInventoryPage() {
    const query = (searchInput?.value || '').trim().toLocaleLowerCase('es-CO');
    const visible = inventory.filter((item) => {
      const matchesState = currentFilter === 'DISPONIBLE'
        ? item.estado === 'DISPONIBLE'
        : item.estado !== 'DISPONIBLE';
      if (!matchesState) return false;
      if (!query) return true;
      return String(item.habitacion_actual || item.ubicacion_asignada || '')
        .toLocaleLowerCase('es-CO').includes(query);
    });
    let pageSize = inventoryPageSize();
    let pageItems = visible.slice((inventoryPage - 1) * pageSize, inventoryPage * pageSize);
    const renderRows = (items) => { inUseRows.innerHTML = items.map((item) => {
      const active = item.prestamo_id != null;
      const patient = active ? `${escapeHtml(item.nombre)}<small>${escapeHtml(item.documento)}</small>` : '—';
      const location = item.habitacion_actual || item.ubicacion_asignada || '—';
      const date = item.fecha_entrega ? new Date(item.fecha_entrega).toLocaleString('es-CO') : '—';
      const startTime = item.fecha_entrega ? new Date(item.fecha_entrega).getTime() : NaN;
      const daysInUse = Number.isFinite(startTime)
        ? Math.max(1, Math.ceil(Math.max(0, Date.now() - startTime) / 86400000))
        : null;
      const loan = active && daysInUse !== null
        ? `${date}<small>${daysInUse} ${daysInUse === 1 ? 'día' : 'días'} en uso</small>`
        : date;
      const status = controlStatusLabels[item.estado] || item.estado;
      const actions = active
        ? `<div class="inventory-actions"><button class="secondary-action" data-inventory-history="${item.prestamo_id}" data-tracking-location="${escapeHtml(location)}" type="button">Ver detalle</button></div>`
        : '—';
      return `<tr><td data-label="Usuario / documento">${patient}</td><td data-label="Habitación / cama">${escapeHtml(location)}</td><td data-label="Préstamo / días en uso">${loan}</td><td data-label="Control"><strong>${escapeHtml(item.codigo)}</strong><small>${escapeHtml(item.marca || '')}</small></td><td data-label="Estado"><span class="table-status ${item.estado === 'PRESTADO' ? 'status-active' : ''}">${escapeHtml(status)}</span></td><td data-label="Detalle">${actions}</td></tr>`;
    }).join(''); };
    const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
    inventoryPage = Math.min(inventoryPage, pageCount);
    pageItems = visible.slice((inventoryPage - 1) * pageSize, inventoryPage * pageSize);
    renderRows(pageItems);
    inUseStatus.hidden = pageItems.length > 0;
    inUseStatus.textContent = pageItems.length ? '' : (query ? 'No hay controles en esa habitación.' : 'No hay controles en este estado.');
    inUseStatus.className = 'workflow-status';
    document.querySelector('#inventory-page-label').textContent = `Página ${inventoryPage} de ${pageCount}`;
    document.querySelector('#inventory-page-previous').disabled = inventoryPage <= 1;
    document.querySelector('#inventory-page-next').disabled = inventoryPage >= pageCount;
  }

  async function refreshInventory() {
    try {
      const response = await fetch('/api/inventario/controles', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo consultar el inventario.');
      inventory = data.controles || [];
      renderInventoryPage();
    } catch (error) {
      inUseStatus.textContent = error.message;
      inUseStatus.className = 'workflow-status workflow-status-error';
      inUseStatus.hidden = false;
    }
  }

  async function loadLoanTracking(loanId) {
    trackingStatus.hidden = false;
    trackingStatus.textContent = 'Consultando movimientos del control...';
    trackingStatus.className = 'workflow-status';
    try {
      const response = await fetch(`/api/prestamos/${encodeURIComponent(loanId)}/historial-traslados`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo consultar el historial del control.');

      let loan = data.prestamo || null;
      let movements = Array.isArray(data.traslados) ? data.traslados : null;
      let verifyLocation = Boolean(data.verificar_ubicacion);
      if (!loan) {
        // Compatibilidad con respuestas de servidores que todavía no incluyen el préstamo en este endpoint.
        const loansResponse = await fetch('/api/prestamos', { cache: 'no-store' });
        const loansData = await loansResponse.json();
        if (!loansResponse.ok) throw new Error(loansData.mensaje || 'No fue posible consultar el préstamo activo.');
        loan = (loansData.prestamos || []).find((item) => String(item.id) === String(loanId)) || null;
      }
      if (!loan) throw new Error('No se encontró un préstamo asociado al control seleccionado. Actualiza el inventario y vuelve a abrir el detalle.');
      loan.habitacion_inicial = loan.habitacion_inicial || loan.habitacion || loan.ubicacion_actual || loan.habitacion_actual;
      loan.ubicacion_actual = loan.ubicacion_actual || loan.habitacion_actual || loan.habitacion_inicial;
      loan.responsable_entrega = loan.responsable_entrega || loan.responsable;
      loan.control = loan.control || loan.control_codigo;

      if ((!movements || movements.length === 0) && loan.documento) {
        const trackingUrl = `/api/controles/seguimiento?tipo=documento&valor=${encodeURIComponent(loan.documento)}`;
        const trackingResponse = await fetch(trackingUrl, { cache: 'no-store' });
        const trackingData = await trackingResponse.json();
        if (trackingResponse.ok) {
          const currentTracking = (trackingData.seguimientos || []).find((item) => String(item.prestamo_id) === String(loanId));
          movements = currentTracking?.traslados || [];
          if (currentTracking) verifyLocation = Boolean(currentTracking.verificar_ubicacion);
        }
      }
      patientName.textContent = loan.nombre || 'No informado';
      patientDocument.textContent = loan.documento || 'No informado';
      patientSummary.hidden = false;
      selectedHistory = buildControlHistory(loan, data.historial_control, movements || []);
      timelinePage = 1;
      warning.hidden = !verifyLocation;
      trackingStatus.hidden = true;
      renderTimelinePage();
    } catch (error) {
      selectedHistory = [];
      patientSummary.hidden = true;
      patientName.textContent = '—';
      patientDocument.textContent = '—';
      warning.hidden = true;
      trackingStatus.textContent = error.message;
      trackingStatus.className = 'workflow-status workflow-status-error';
      timeline.innerHTML = '<li class="timeline-empty">No fue posible cargar los movimientos.</li>';
      document.querySelector('#timeline-page-label').textContent = 'Movimientos 0 de 0';
      document.querySelector('#timeline-page-previous').disabled = true;
      document.querySelector('#timeline-page-next').disabled = true;
    }
  }

  function buildControlHistory(selectedLoan, controlHistory, fallbackTransfers) {
    const loans = (controlHistory?.prestamos?.length ? controlHistory.prestamos : [selectedLoan])
      .slice().sort((a, b) => new Date(a.fecha_entrega) - new Date(b.fecha_entrega));
    const transfers = controlHistory?.traslados || fallbackTransfers || [];
    const now = Date.now();
    const loanInfo = new Map();
    const events = [];
    const toMillis = (value) => {
      const parsed = new Date(value).getTime();
      return Number.isFinite(parsed) ? parsed : 0;
    };
    for (const item of loans) {
      const start = toMillis(item.fecha_entrega);
      const end = item.fecha_devolucion ? toMillis(item.fecha_devolucion) : now;
      const days = Math.max(1, Math.ceil(Math.max(0, end - start) / 86400000));
      loanInfo.set(String(item.id), { item, start, end, days });
      const location = item.habitacion_inicial || item.ubicacion_actual || 'No informada';
      events.push({
        tipo_movimiento: loans.length > 1 ? 'Nuevo pr\u00e9stamo / entrega' : 'Entrega del control',
        fecha_movimiento: item.fecha_entrega,
        habitacion_origen: 'Oficina de pr\u00e9stamos', habitacion_destino: location,
        paciente: item.nombre || 'No informado', documento: item.documento || 'No informado',
        responsable: item.responsable_entrega || 'No informado', quien_recibio: item.recibe || 'No informado',
        dias_utilizados: days, control: item.control_codigo || selectedLoan.control,
        estado_prestamo: item.estado || 'No informado', confirmacion_fisica: Boolean(item.confirmacion_fisica),
        detalle: item.parentesco ? `Recibi\u00f3: ${item.recibe || 'No informado'} (${item.parentesco})` : ''
      });
      if (item.fecha_devolucion) {
        events.push({
          tipo_movimiento: 'Devoluci\u00f3n del control', fecha_movimiento: item.fecha_devolucion,
          habitacion_origen: item.ubicacion_actual || location, habitacion_destino: 'Inventario de controles',
          paciente: item.nombre || 'No informado', documento: item.documento || 'No informado',
          responsable: item.responsable_devolucion || 'No informado', quien_recibio: item.responsable_devolucion || 'No informado',
          dias_utilizados: days, control: item.control_codigo || selectedLoan.control,
          estado_prestamo: item.estado || 'DEVUELTO', confirmacion_fisica: true,
          detalle: `Devuelto por: ${item.recibe_devolucion || 'No informado'}${item.valor_total != null ? ` · Total registrado: ${money(Number(item.valor_total))} COP` : ''}`
        });
      }
    }
    for (const move of transfers) {
      const moveAt = toMillis(move.fecha_movimiento);
      const matching = loans.find((item) => {
        const info = loanInfo.get(String(item.id));
        const samePatient = String(item.documento || '') === String(move.documento || '');
        const sameControl = move.control_id == null || String(move.control_id) === String(item.control_id)
          || String(move.nuevo_control_id || '') === String(item.control_id);
        return info && samePatient && sameControl && moveAt >= info.start && moveAt <= info.end;
      });
      const info = matching ? loanInfo.get(String(matching.id)) : null;
      events.push({
        tipo_movimiento: 'Cambio de habitaci\u00f3n', fecha_movimiento: move.fecha_movimiento,
        habitacion_origen: move.habitacion_origen || 'No informada',
        habitacion_destino: move.habitacion_destino || 'No informada',
        paciente: matching?.nombre || (String(move.documento || '') === String(selectedLoan.documento || '') ? selectedLoan.nombre : 'No informado'),
        documento: move.documento || matching?.documento || 'No informado',
        responsable: move.responsable || 'No informado',
        quien_recibio: move.recibe_control_anterior || 'No informado',
        dias_utilizados: info?.days ?? 0,
        control: move.control_codigo || matching?.control_codigo || selectedLoan.control,
        estado_prestamo: move.estado || 'REGISTRADO',
        confirmacion_fisica: Boolean(move.confirmacion_fisica),
        detalle: move.observaciones || ''
      });
    }
    const priority = { 'Devoluci\u00f3n del control': 0, 'Entrega del control': 1, 'Nuevo pr\u00e9stamo / entrega': 1, 'Cambio de habitaci\u00f3n': 2 };
    return events.sort((a, b) => toMillis(a.fecha_movimiento) - toMillis(b.fecha_movimiento)
      || (priority[a.tipo_movimiento] ?? 1) - (priority[b.tipo_movimiento] ?? 1));
  }

  function renderTimelinePage() {
    const pageCount = Math.max(1, Math.ceil(selectedHistory.length / TIMELINE_PAGE_SIZE));
    timelinePage = Math.min(timelinePage, pageCount);
    const pageMoves = selectedHistory.slice((timelinePage - 1) * TIMELINE_PAGE_SIZE, timelinePage * TIMELINE_PAGE_SIZE);
    timeline.innerHTML = pageMoves.length ? pageMoves.map((move) => `<li class="timeline-item">
        <time>${new Date(move.fecha_movimiento).toLocaleString('es-CO')}</time>
        <strong>${escapeHtml(move.control || move.control_codigo || 'Control')} · ${escapeHtml(move.tipo_movimiento || 'Movimiento')}</strong>
        <strong>${escapeHtml(move.habitacion_origen)} <span aria-hidden="true">→</span> ${escapeHtml(move.habitacion_destino)}</strong>
        <span>Responsable: ${escapeHtml(move.responsable || 'No informado')}</span>
        <span>Paciente: ${escapeHtml(move.paciente || 'No informado')} &middot; Documento: ${escapeHtml(move.documento || 'No informado')}</span>
        <span>Recibi&oacute; el control: ${escapeHtml(move.quien_recibio || 'No informado')} &middot; D&iacute;as utilizados: ${escapeHtml(move.dias_utilizados ?? 0)}</span>
        ${move.detalle ? `<span>${escapeHtml(move.detalle)}</span>` : ''}
        <span>Control físico: ${move.confirmacion_fisica ? 'confirmado' : 'sin confirmar'}${move.control_codigo ? ` · ${escapeHtml(move.control_codigo)}` : ''}</span>
      </li>`).join('') : '<li class="timeline-empty">Este préstamo aún no tiene traslados registrados.</li>';
    const firstMove = selectedHistory.length ? (timelinePage - 1) * TIMELINE_PAGE_SIZE + 1 : 0;
    const lastMove = Math.min(timelinePage * TIMELINE_PAGE_SIZE, selectedHistory.length);
    document.querySelector('#timeline-page-label').textContent = `Movimientos ${firstMove}-${lastMove} de ${selectedHistory.length}`;
    document.querySelector('#timeline-page-previous').disabled = timelinePage <= 1;
    document.querySelector('#timeline-page-next').disabled = timelinePage >= pageCount;
  }

  document.querySelectorAll('[data-inventory-filter]').forEach((card) => {
    const activate = async () => {
      currentFilter = card.dataset.inventoryFilter;
      inventoryPage = 1;
      listView.hidden = false;
      transferDetail.hidden = true;
      searchInput.value = '';
      searchInput.closest('.inventory-search').hidden = currentFilter !== 'EN_USO';
      inUseStatus.hidden = true;
      selectedHistory = [];
      document.querySelector('#inventory-detail-title').textContent = {
        DISPONIBLE: 'Controles disponibles',
        EN_USO: 'Controles en uso'
      }[currentFilter] || 'Inventario de controles';
      detailModal.dataset.inventoryState = currentFilter;
      detailModal.classList.remove('is-closing');
      if (inventoryCloseTimer) window.clearTimeout(inventoryCloseTimer);
      document.querySelectorAll('[data-inventory-filter]').forEach((item) => {
        item.classList.toggle('is-selected', item === card);
        item.setAttribute('aria-pressed', String(item === card));
      });
      detailModal.showModal();
      await refreshInventory();
    };
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
    });
  });
  document.querySelector('#inventory-page-previous').addEventListener('click', () => {
    inventoryPage--;
    renderInventoryPage();
  });
  document.querySelector('#inventory-page-next').addEventListener('click', () => {
    inventoryPage++;
    renderInventoryPage();
  });
  searchInput?.addEventListener('input', () => { inventoryPage = 1; renderInventoryPage(); });
  window.addEventListener('resize', () => {
    if (detailModal.open && currentFilter === 'DISPONIBLE') renderInventoryPage();
  });
  document.querySelector('#timeline-page-previous').addEventListener('click', () => {
    timelinePage--;
    renderTimelinePage();
  });
  document.querySelector('#timeline-page-next').addEventListener('click', () => {
    timelinePage++;
    renderTimelinePage();
  });
  document.querySelector('#inventory-back-to-list').addEventListener('click', () => {
    transferDetail.hidden = true;
    listView.hidden = false;
    inUseStatus.hidden = true;
  });
  document.querySelector('[data-close-inventory-modal]').addEventListener('click', closeInventoryModal);
  detailModal.addEventListener('click', (event) => { if (event.target === detailModal) closeInventoryModal(); });
  detailModal.addEventListener('cancel', (event) => { event.preventDefault(); closeInventoryModal(); });
  detailModal.addEventListener('close', () => detailModal.classList.remove('is-closing'));
  document.querySelector('#export-transfer-pdf').addEventListener('click', () => {
    if (!selectedHistory.length) {
      window.alert('Primero abre el detalle del control para cargar su recorrido.');
      return;
    }
    const control = selectedHistory.find((move) => move.control)?.control || 'Control';
    const deliveries = selectedHistory.filter((move) => /entrega|prestamo/i.test(move.tipo_movimiento || ''));
    const totalDays = deliveries.reduce((sum, move) => sum + Number(move.dias_utilizados || 0), 0);
    const generatedAt = new Date().toLocaleString('es-CO');
    const content = selectedHistory.map((move) => {
      const date = new Date(move.fecha_movimiento);
      const dateLabel = Number.isNaN(date.getTime()) ? 'Fecha no informada' : date.toLocaleString('es-CO');
      return `<tr><td>${escapeHtml(dateLabel)}</td><td>${escapeHtml(move.tipo_movimiento || 'Movimiento')}</td><td>${escapeHtml(move.paciente || 'No informado')}<br>${escapeHtml(move.documento || 'No informado')}</td><td>${escapeHtml(move.habitacion_origen || 'No informada')} &rarr; ${escapeHtml(move.habitacion_destino || 'No informada')}</td><td>${escapeHtml(move.responsable || 'No informado')}</td><td>${escapeHtml(move.quien_recibio || 'No informado')}</td><td>${escapeHtml(move.dias_utilizados ?? 0)}</td><td>${escapeHtml(move.control || control)}</td></tr>`;
    }).join('');
    const printWindow = window.open('', '_blank');
    if (!printWindow) { window.alert('Permite ventanas emergentes para generar el PDF.'); return; }
    printWindow.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Recorrido del control ${escapeHtml(control)}</title><style>@page{size:A4 landscape;margin:12mm}body{font-family:Arial,sans-serif;color:#18324a;margin:1rem}h1{text-align:center;font-size:1.35rem;margin:.2rem 0 .7rem}.summary{display:flex;justify-content:space-between;gap:1rem;margin-bottom:.8rem;padding:.65rem;border:1px solid #dce7f0;background:#f8fbfe}table{width:100%;border-collapse:collapse;font-size:.72rem}th,td{padding:.45rem;border:1px solid #cbd8e3;text-align:left;vertical-align:top}th{background:#edf4fa}tfoot{font-weight:bold}.note{margin-top:.7rem;color:#587089;font-size:.7rem}@media print{body{margin:0}}</style></head><body><h1>Recorrido del control ${escapeHtml(control)}</h1><div class="summary"><span><strong>Movimientos:</strong> ${selectedHistory.length}</span><span><strong>Pr\u00e9stamos registrados:</strong> ${deliveries.length}</span><span><strong>Total de d\u00edas utilizados:</strong> ${totalDays}</span><span><strong>Generado:</strong> ${escapeHtml(generatedAt)}</span></div><table><thead><tr><th>Fecha y hora</th><th>Movimiento</th><th>Paciente / documento</th><th>Ubicaci&#243;n: origen &rarr; destino</th><th>Responsable que lo prest&#243; / gestion&#243;</th><th>Persona que lo recibi&#243;</th><th>D&#237;as utilizados en el pr&#233;stamo</th><th>Control</th></tr></thead><tbody>${content}</tbody></table><p class="note">El recorrido incluye cada entrega, cambio de habitaci&#243;n y devoluci&#243;n registrados para este control.</p></body></html>`);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  });

  inUseRows.addEventListener('click', async (event) => {
    const historyButton = event.target.closest('[data-inventory-history]');
    if (historyButton) {
      listView.hidden = true;
      transferDetail.hidden = false;
      inUseStatus.hidden = true;
      await loadLoanTracking(historyButton.dataset.inventoryHistory);
    }
  });
}

const inventoryReentryModal = document.querySelector('#inventory-reentry-modal');
if (inventoryReentryModal) {
  const reentryForm = document.querySelector('#inventory-reentry-form');
  const reentrySelect = document.querySelector('#inventory-reentry-loan');
  const reentryRecipient = document.querySelector('#inventory-reentry-recipient');
  const reentryStatus = document.querySelector('#inventory-reentry-status');
  const reentryBillingLink = document.querySelector('#inventory-reentry-generate-charge');
  const reentryLoans = new Map();

  async function loadReentryOptions() {
    reentryLoans.clear();
    reentrySelect.replaceChildren(new Option('Consultando controles en uso...', ''));
    reentrySelect.disabled = true;
    try {
      const response = await fetch('/api/inventario/controles', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No fue posible consultar los controles en uso.');
      const active = (data.controles || []).filter((item) => item.prestamo_id != null);
      reentrySelect.replaceChildren(new Option('Selecciona un control en uso', ''));
      active.forEach((item) => {
        const loanId = String(item.prestamo_id);
        reentryLoans.set(loanId, item);
        const location = item.habitacion_actual || item.ubicacion_asignada || 'Ubicación no informada';
        reentrySelect.add(new Option(`${item.codigo} · ${item.nombre || 'Paciente'} · Hab. ${location}`, loanId));
      });
      reentrySelect.disabled = active.length === 0;
      if (!active.length) {
        reentryStatus.textContent = 'No hay controles prestados pendientes de reingreso.';
        reentryStatus.className = 'workflow-status';
        reentryStatus.hidden = false;
      }
    } catch (error) {
      reentrySelect.replaceChildren(new Option('No se pudo cargar el inventario', ''));
      reentryStatus.textContent = error.message;
      reentryStatus.className = 'workflow-status workflow-status-error';
      reentryStatus.hidden = false;
    }
  }

  document.querySelector('#open-inventory-reentry').addEventListener('click', async () => {
    reentryRecipient.value = '';
    reentryBillingLink.hidden = true;
    reentryStatus.hidden = true;
    reentrySelect.replaceChildren(new Option('Selecciona un control en uso', ''));
    inventoryReentryModal.showModal();
    await loadReentryOptions();
  });
  document.querySelectorAll('[data-close-reentry-modal]').forEach((button) => button.addEventListener('click', () => inventoryReentryModal.close()));
  inventoryReentryModal.addEventListener('click', (event) => { if (event.target === inventoryReentryModal) inventoryReentryModal.close(); });
  reentrySelect.addEventListener('change', () => { reentryBillingLink.hidden = true; });
  reentryForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!reentryForm.reportValidity()) return;
    const loanId = reentrySelect.value;
    const selectedLoan = reentryLoans.get(loanId);
    if (!loanId || !selectedLoan) return;
    const submit = reentryForm.querySelector('[type="submit"]');
    submit.disabled = true;
    reentryStatus.hidden = true;
    reentryBillingLink.hidden = true;
    try {
      const response = await fetch(`/api/prestamos/${encodeURIComponent(loanId)}/devolucion`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recibe: reentryRecipient.value.trim() })
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 409 && selectedLoan.documento) {
          reentryBillingLink.href = `/generar-cobro?documento=${encodeURIComponent(selectedLoan.documento)}`;
          reentryBillingLink.hidden = false;
        }
        throw new Error(data.mensaje || 'No se pudo registrar el reingreso.');
      }
      reentryStatus.textContent = data.mensaje || 'Control reingresado al inventario.';
      reentryStatus.className = 'workflow-status workflow-status-success';
      reentryStatus.hidden = false;
      reentryRecipient.value = '';
      await refreshDashboardCounts();
      await loadReentryOptions();
      reentryStatus.textContent = data.mensaje || 'Control reingresado al inventario.';
      reentryStatus.className = 'workflow-status workflow-status-success';
      reentryStatus.hidden = false;
    } catch (error) {
      reentryStatus.textContent = error.message;
      reentryStatus.className = 'workflow-status workflow-status-error';
      reentryStatus.hidden = false;
    } finally { submit.disabled = false; }
  });
}

let historyLoans = [];
let historyPage = 1;
const HISTORY_PAGE_SIZE = 10;
let selectedReturnLoan = null;

function renderHistoryPage() {
  const rows = document.querySelector('#history-rows');
  if (!rows) return;
  const pageCount = Math.max(1, Math.ceil(historyLoans.length / HISTORY_PAGE_SIZE));
  historyPage = Math.min(historyPage, pageCount);
  const pageLoans = historyLoans.slice((historyPage - 1) * HISTORY_PAGE_SIZE, historyPage * HISTORY_PAGE_SIZE);
  rows.innerHTML = pageLoans.map((loan) => `<tr>
    <td>${escapeHtml(loan.nombre)}</td><td>${escapeHtml(loan.documento)}</td><td>${escapeHtml(loan.habitacion_actual)}</td>
    <td>${escapeHtml(loan.control)}</td><td>${new Date(loan.fecha_entrega).toLocaleString('es-CO')}</td>
    <td>${loan.fecha_devolucion ? new Date(loan.fecha_devolucion).toLocaleString('es-CO') : 'Pendiente'}</td>
    <td>${money(loan.valor)}</td><td>${escapeHtml(loan.estado === 'ACTIVO' ? 'En uso' : 'Devuelto')}</td>
    <td>${loan.estado === 'ACTIVO' ? `<button class="secondary-action" data-return-loan="${loan.id}">Registrar devolución</button>` : '—'}</td></tr>`).join('');
  const pages = Math.max(1, Math.ceil(historyLoans.length / HISTORY_PAGE_SIZE));
  document.querySelector('#history-page-label').textContent = `Página ${historyPage} de ${pages}`;
  document.querySelector('#history-previous').disabled = historyPage <= 1;
  document.querySelector('#history-next').disabled = historyPage >= pages;
}

async function refreshHistory() {
  const rows = document.querySelector('#history-rows');
  if (!rows) return;
  const status = document.querySelector('#history-status');
  status.hidden = false;
  status.textContent = 'Consultando historial...';
  try {
    const response = await fetch('/api/prestamos', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || 'No fue posible consultar el historial.');
    // Solo se muestran controles actualmente prestados; las devoluciones antiguas siguen guardadas.
    historyLoans = data.prestamos.filter((loan) => loan.estado === 'ACTIVO');
    renderHistoryPage();
    status.textContent = historyLoans.length ? `${historyLoans.length} control(es) prestado(s). Se muestran hasta 10 por página.` : '';
    status.hidden = historyLoans.length === 0;
    status.className = 'workflow-status workflow-status-success';
  } catch (error) { status.hidden = false; status.textContent = error.message; status.className = 'workflow-status workflow-status-error'; }
}

document.querySelector('#refresh-history')?.addEventListener('click', async () => { await refreshHistory(); await refreshDashboardCounts(); });
document.querySelector('#history-previous')?.addEventListener('click', () => { historyPage--; renderHistoryPage(); });
document.querySelector('#history-next')?.addEventListener('click', () => { historyPage++; renderHistoryPage(); });
document.querySelector('#history-return-back')?.addEventListener('click', () => document.querySelector('#history-return-modal')?.close());
document.querySelector('#history-rows')?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-return-loan]');
  if (!button) return;
  selectedReturnLoan = button.dataset.returnLoan;
  document.querySelector('#history-return-recipient').value = '';
  document.querySelector('#history-return-modal')?.showModal();
});
document.querySelector('#history-return-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!selectedReturnLoan) return;
  const submit = event.currentTarget.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    const recibe = document.querySelector('#history-return-recipient').value.trim();
    const response = await fetch(`/api/prestamos/${selectedReturnLoan}/devolucion`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ recibe }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || 'No se pudo guardar la devolución.');
    document.querySelector('#history-return-modal').close();
    selectedReturnLoan = null;
    await refreshHistory();
    await refreshDashboardCounts();
    document.querySelector('#history-status').textContent = data.mensaje;
  } catch (error) { window.alert(error.message); }
  finally { submit.disabled = false; }
});
refreshDashboardCounts();
refreshHistory();


const patientWorkflow = document.querySelector('#room-patient-modal');
if (patientWorkflow) {
  const status = document.querySelector('#patient-search-status');
  const details = document.querySelector('#patient-details');
  const list = document.querySelector('#room-patients');
  const form = patientWorkflow.querySelector('#home-loan-form');
  const code = document.querySelector('#loan-physical-control');
  const bed = document.querySelector('#loan-bed-display');
  const confirmBed = document.querySelector('#loan-confirm-bed');
  const confirmControl = document.querySelector('#loan-confirm-control');
  const loanAccordion = document.querySelector('#loan-service-accordion');
  const exemptionAccordion = document.querySelector('#tv-exemption-accordion');
  const exemptionNote = document.querySelector('#tv-exemption-note');
  const documentField = document.querySelector('#loan-document');
  const relationship = document.querySelector('#loan-relationship');
  const exemptionOptions = [...document.querySelectorAll('input[name="exoneracion_categoria"]')];
  const resetExemption = () => {
    if (exemptionAccordion) {
      exemptionAccordion.hidden = false;
      exemptionAccordion.open = false;
    }
    exemptionOptions.forEach((option) => { option.checked = false; });
    if (exemptionNote) {
      exemptionNote.textContent = 'Si no seleccionas una categoría, el préstamo se registrará con la tarifa habitual.';
      exemptionNote.classList.remove('is-exempt-selected');
    }
  };
  exemptionOptions.forEach((option) => option.addEventListener('change', () => {
    if (exemptionNote) {
      exemptionNote.textContent = option.checked
        ? `Categoría seleccionada: ${option.value}. El servicio se registrará exento a $0.`
        : 'Si no seleccionas una categoría, el préstamo se registrará con la tarifa habitual.';
      exemptionNote.classList.toggle('is-exempt-selected', option.checked);
    }
  }));
  document.querySelector('.tv-exemption-options')?.addEventListener('dblclick', (event) => {
    const option = event.target.closest('label')?.querySelector('input[name="exoneracion_categoria"]');
    if (!option?.checked) return;
    option.checked = false;
    option.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const save = document.querySelector('#save-loan') || form?.querySelector('button[type="submit"]');
  const searchButtons = [...document.querySelectorAll('.home-patient-search button[type="submit"]')];
  const title = document.querySelector('#room-patient-modal-title');
  let selected = null;
  let loanSaved = false;
  let documentLookupTimer = null;

  const setDisabled = (element, disabled) => {
    if (element) element.disabled = Boolean(disabled);
  };

  const say = (message, error = false) => {
    if (!status) return;
    status.hidden = false;
    status.textContent = message;
    status.className = 'workflow-status' + (error ? ' workflow-status-error' : '');
  };
  const hasBedNumber = (value) => /^[A-Z0-9]+-[0-9]+$/i.test(String(value || '').trim());

  function updateLoanAvailability() {
    const exactLocation = selected && form.dataset.locationCode &&
      String(selected.cama || '').trim().toUpperCase() === form.dataset.locationCode;
    setDisabled(save, !(exactLocation && !loanSaved && bed?.value && code?.value &&
      documentField.value.trim() === String(selected?.identificacion || '') &&
      document.querySelector('#loan-recipient')?.value.trim() && relationship.value));
  }

  async function loadLoanOptions(patient) {
    let locationCode = String(patient.cama || '').trim().toUpperCase();
    const notice = document.querySelector('#loan-persistence-notice');
    notice.hidden = true;
    bed.replaceChildren(new Option(locationCode, locationCode));
    bed.value = locationCode;
    form.dataset.locationCode = '';
    code.replaceChildren(new Option('Consultando inventario...', ''));
    setDisabled(code, true);
    if (!locationCode) throw new Error('El censo no devolvió una cama válida para asociar el control.');
    const response = await fetch('/api/catalogo/ubicaciones/' + encodeURIComponent(locationCode) + '/controles');
    const result = await response.json();
    if (!response.ok || !Array.isArray(result.controles)) throw new Error(result.mensaje || 'No fue posible consultar el inventario.');
    const catalogCode = String(result.ubicacion?.ubicacion_codigo || '').trim().toUpperCase();
    const concatenatedCode = catalogCode.match(/^([0-9]{3})-([0-9])$/);
    const isCensusAlias = concatenatedCode && locationCode === concatenatedCode[1] + concatenatedCode[2];
    if (!catalogCode || (catalogCode !== locationCode && !isCensusAlias)) {
      throw new Error('El catálogo no confirmó una correspondencia exacta para la cama del paciente.');
    }
    // El censo puede enviar 3081 mientras el catálogo conserva 308-1.
    locationCode = catalogCode;
    patient.cama = catalogCode;
    bed.replaceChildren(new Option(locationCode, locationCode));
    bed.value = locationCode;
    document.querySelector('#result-patient-bed').textContent = locationCode;
    if (result.controles.length) {
      const firstAvailable = result.controles[0];
      code.replaceChildren(new Option(result.marca_requerida || firstAvailable.marca, firstAvailable.id));
      code.value = String(firstAvailable.id);
    } else {
      code.replaceChildren(new Option('Sin controles disponibles', ''));
    }
    setDisabled(code, !result.controles.length);
    confirmBed.checked = Boolean(result.controles.length);
    confirmControl.checked = Boolean(result.controles.length);
    form.dataset.locationCode = locationCode;
    notice.textContent = result.controles.length
      ? ''
      : (result.mensaje || 'No hay control disponible para esta ubicaci\u00f3n.');
    notice.className = 'workflow-status modal-wide ' + (result.controles.length ? 'workflow-status-success' : 'workflow-status-warning');
    notice.hidden = Boolean(result.controles.length);
    updateLoanAvailability();
  }

  async function selectPatient(patient) {
    const response = await fetch('/api/paciente/identificacion/' + encodeURIComponent(patient.identificacion));
    const valid = await response.json();
    if (!response.ok) throw new Error(valid.mensaje || 'No se pudo validar el paciente.');
    selected = Object.assign({}, valid, {cama: patient.cama || valid.cama, control_tv: patient.control_tv || null});
    patientWorkflow.classList.remove('loan-saved-state');
    if (save) save.hidden = false;
    loanSaved = false;
    const fullName = selected.nombre_completo || 'No informado';
    const patientName = document.querySelector('#loan-patient-name');
    patientName.textContent = 'Paciente: ' + fullName;
    patientName.title = fullName;
    document.querySelector('#result-patient-identity').textContent = selected.identificacion || 'No informado';
    const location = String(selected.cama || '').trim().toUpperCase();
    const room = location.replace(/-[0-9]+$/, '');
    document.querySelector('#result-patient-bed').textContent = location || 'No informada';
    documentField.value = selected.identificacion || '';
    document.querySelector('#loan-relationship').value = '';
    document.querySelector('#loan-recipient').value = '';
    document.querySelector('#loan-delivered-at').value = localDateTimeValue();
    resetExemption();
    form.dataset.patientIdentification = selected.identificacion || '';
    details.hidden = false;
    list.hidden = true;
    loanAccordion.hidden = false;
    loanAccordion.open = false;
    status.hidden = true;
    setDisabled(save, true);
    try {
      await loadLoanOptions(selected);
    } catch (error) {
      // Se mantiene la ficha real del paciente sin exponer errores del catálogo;
      // el guardado permanece bloqueado si no hay correspondencia física válida.
      const notice = document.querySelector('#loan-persistence-notice');
      notice.hidden = false;
      notice.textContent = error.message || 'No hay una correspondencia física válida para esta ubicación.';
      notice.className = 'workflow-status modal-wide workflow-status-error';
      setDisabled(save, true);
    }
  }

  function makePatientCard(patient) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'room-patient-card';
    const location = String(patient.cama || '').trim().toUpperCase();
    const room = location.replace(/-[0-9]+$/, '');
    button.title = patient.nombre_completo || 'Nombre no informado';
    button.innerHTML = '<span><b>Paciente:</b> ' + escapeHtml(patient.nombre_completo || 'Nombre no informado') + '</span>' +
      '<span><b>CC:</b> ' + escapeHtml(patient.identificacion || 'No informado') + '</span>' +
      '<span><b>Cama:</b> ' + escapeHtml(location || room || 'No informada') + '</span>';
    button.addEventListener('click', async () => {
      list.querySelectorAll('button').forEach((item) => { item.disabled = true; });
      try { await selectPatient(patient); }
      catch (error) { reportWorkflowError(error, 'No se pudo cargar el formulario.'); }
    });
    return button;
  }

  function resetSelection() {
    selected = null;
    patientWorkflow.classList.remove('loan-saved-state');
    if (save) save.hidden = false;
    loanSaved = false;
    details.hidden = true;
    loanAccordion.hidden = true;
    loanAccordion.open = false;
    resetExemption();
    documentField.value = '';
    relationship.value = '';
    list.hidden = true;
    list.replaceChildren();
    status.hidden = true;
    form.dataset.locationCode = '';
    if (patientWorkflow.open) patientWorkflow.close();
  }

  function reportWorkflowError(error, fallback) {
    const technicalNullError = error instanceof TypeError && /properties of null|configurar|disabled/i.test(error.message || '');
    if (technicalNullError) {
      console.error('Flujo de préstamo incompleto: falta un elemento esperado en la plantilla.', error);
      if (status) status.hidden = true;
      return;
    }
    say(error?.message || fallback, true);
  }

  document.querySelector('#close-patient-workflow')?.addEventListener('click', resetSelection);
  document.querySelector('#cancel-loan-form')?.addEventListener('click', () => {
    if (loanSaved) {
      resetSelection();
      return;
    }
    loanAccordion.open = false;
    document.querySelector('#loan-persistence-notice').hidden = true;
  });

  document.querySelectorAll('.home-patient-search').forEach((searchForm) => searchForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = searchForm.elements.q.value.trim();
    if (!query) { searchForm.elements.q.focus(); return; }
    selected = null;
    patientWorkflow.classList.remove('loan-saved-state');
    if (save) save.hidden = false;
    loanSaved = false;
    details.hidden = true;
    loanAccordion.hidden = true;
    loanAccordion.open = false;
    resetExemption();
    list.hidden = true;
    list.replaceChildren();
    title.textContent = 'Paciente encontrado';
    if (!patientWorkflow.open) patientWorkflow.showModal();
    searchButtons.forEach((button) => { button.disabled = true; });
    say('Consultando el sistema institucional...');
    try {
      const roomSearch = searchForm.dataset.searchType === 'habitacion';
      const endpoint = roomSearch ? '/api/paciente/habitacion/' : '/api/paciente/identificacion/';
      const response = await fetch(endpoint + encodeURIComponent(query));
      const result = await response.json();
      if (!response.ok) throw new Error(result?.mensaje || 'No se encontraron pacientes para la búsqueda.');
      if (roomSearch) {
        if (!Array.isArray(result.pacientes) || !result.pacientes.length) throw new Error('No se encontraron pacientes en esa habitación.');
        title.textContent = 'Paciente encontrado';
        if (result.pacientes.length === 1) {
          await selectPatient(result.pacientes[0]);
        } else {
          list.replaceChildren(...result.pacientes.map(makePatientCard));
          list.hidden = false;
          status.hidden = true;
        }
      } else {
        if (!result.identificacion || !result.cama) throw new Error('La respuesta del paciente está incompleta.');
        await selectPatient(result);
      }
    } catch (error) {
      title.textContent = 'No fue posible consultar';
      reportWorkflowError(error, 'No fue posible consultar los pacientes.');
    } finally { searchButtons.forEach((button) => { button.disabled = false; }); }
  }));

  code.addEventListener('change', updateLoanAvailability);
  document.querySelector('#loan-recipient').addEventListener('input', updateLoanAvailability);
  relationship.addEventListener('change', updateLoanAvailability);
  documentField.addEventListener('input', () => {
    const value = documentField.value.trim();
    if (selected && value === String(selected.identificacion || '')) return;
    selected = null;
    setDisabled(save, true);
    details.hidden = true;
    loanAccordion.hidden = true;
    clearTimeout(documentLookupTimer);
    if (value.length < 5) return;
    documentLookupTimer = setTimeout(async () => {
      say('Validando documento y consultando los datos del paciente...');
      try {
        const response = await fetch('/api/paciente/identificacion/' + encodeURIComponent(value));
        const patient = await response.json();
        if (!response.ok || !patient.identificacion) throw new Error(patient.mensaje || 'No se encontro un paciente con ese documento.');
        await selectPatient(patient);
      } catch (error) {
        say(error.message || 'No fue posible validar el documento.', true);
      }
    }, 450);
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity() || !code.value || !bed.value) return;
    setDisabled(save, true);
    const notice = document.querySelector('#loan-persistence-notice');
    notice.hidden = true;
    try {
      const response = await fetch('/api/prestamos', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({documento: form.dataset.patientIdentification, nombre: selected.nombre_completo,
          recibe: document.querySelector('#loan-recipient').value, habitacion: form.dataset.locationCode,
          parentesco: relationship.value, exoneracion_categoria: exemptionOptions.find((option) => option.checked)?.value || '',
          control: code.value, confirmar_cama: true, confirmar_control_fisico: true})});
      const result = await response.json();
      notice.hidden = false;
      notice.className = 'workflow-status modal-wide ' + (response.ok ? 'workflow-status-success loan-save-success' : 'workflow-status-error');
      if (response.ok) {
        notice.replaceChildren();
        const artwork = document.createElement('div');
        artwork.className = 'loan-save-success-art';
        const image = document.createElement('img');
        image.className = 'loan-save-success-image';
        image.src = '/img/pingui_exito.jpg';
        image.alt = 'Mascota de Clínica CES celebrando el préstamo exitoso';
        const artworkTitle = document.createElement('span');
        artworkTitle.className = 'loan-save-success-art-title';
        artworkTitle.textContent = 'PRÉSTAMO EXITOSO';
        artwork.append(image, artworkTitle);
        const confirmation = document.createElement('p');
        confirmation.textContent = result.exoneracion_categoria
          ? `Préstamo exitoso. El control de TV ha sido asignado correctamente al paciente. Servicio exento ($0): ${result.exoneracion_categoria}.`
          : 'Préstamo exitoso. El control de TV ha sido asignado correctamente al paciente.';
        notice.append(artwork, confirmation);
        loanSaved = true;
        patientWorkflow.classList.add('loan-saved-state');
        details.hidden = true;
        loanAccordion.open = true;
        exemptionAccordion.hidden = true;
        if (save) save.hidden = true;
        setDisabled(save, true);
        refreshDashboardCounts();
        refreshHistory();
      } else {
        const errorMessage = result.mensaje || 'No se pudo registrar la entrega.';
        if (response.status === 409 && /pr[eé]stamo activo|control ya no est[aá] disponible/i.test(errorMessage)) {
          notice.replaceChildren();
          const artwork = document.createElement('div');
          artwork.className = 'loan-save-error-art';
          const image = document.createElement('img');
          image.className = 'loan-save-success-image';
          image.src = '/img/pingui_error.jpg';
          image.alt = 'Pingüi triste porque el control ya está prestado';
          const artworkTitle = document.createElement('span');
          artworkTitle.className = 'loan-save-error-art-title';
          artworkTitle.textContent = 'YA ESTÁ PRESTADO';
          artwork.append(image, artworkTitle);
          const confirmation = document.createElement('p');
          confirmation.textContent = /pr[eé]stamo activo/i.test(errorMessage)
            ? 'Este paciente ya tiene un préstamo activo.'
            : 'Este control ya está prestado. Actualiza la lista de controles disponibles.';
          notice.className = 'workflow-status modal-wide loan-save-error';
          notice.append(artwork, confirmation);
        } else {
          notice.textContent = errorMessage;
        }
      }
    } catch (error) {
      notice.hidden = false;
      notice.textContent = 'No se confirmó la entrega por un error de conexión. Verifica el historial antes de reintentar.';
      notice.className = 'workflow-status modal-wide workflow-status-error';
    } finally { updateLoanAvailability(); }
  });
}
function localDateTimeValue() {
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

const searchForm = document.querySelector('#search-form');
if (searchForm) {
  const searchModes = [...document.querySelectorAll('[data-search-mode]')];
  let selectedSearchMode = 'identificacion';
  const searchInput = document.querySelector('#search-query');
  const searchLabel = document.querySelector('#search-label');
  searchModes.forEach((button) => button.addEventListener('click', () => {
    selectedSearchMode = button.dataset.searchMode;
    searchModes.forEach((modeButton) => {
      const selected = modeButton === button;
      modeButton.classList.toggle('is-selected', selected);
      modeButton.setAttribute('aria-pressed', String(selected));
    });
    const byBed = selectedSearchMode === 'cama';
    searchLabel.textContent = byBed ? 'Número de cama' : 'Número de identificación';
    searchInput.placeholder = byBed ? 'Escribe el número de cama (ej. 502)' : 'Escribe el número de identificación';
    searchInput.inputMode = byBed ? 'text' : 'numeric';
    searchInput.value = '';
    document.querySelector('#patient-result').hidden = true;
    searchInput.focus();
  }));

  searchForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = searchInput.value.trim();
    const resultBox = document.querySelector('#patient-result');
    if (searchModes.length) {
      if (!query) return;
      resultBox.innerHTML = '<small>Consultando el sistema institucional...</small>';
      resultBox.hidden = false;
      const endpoint = selectedSearchMode === 'cama' ? 'cama' : 'identificacion';
      try {
        const response = await fetch(`/api/paciente/${endpoint}/${encodeURIComponent(query)}`);
        const data = await response.json();
        if (!response.ok) {
          resultBox.innerHTML = `<small class="patient-search-error">${escapeHtml(data.mensaje || 'No encontramos resultados para ese dato.')}</small>`;
          return;
        }
        resultBox.innerHTML = `<div class="patient-summary"><h2>Paciente encontrado</h2><dl><div><dt>Tipo de identificación</dt><dd>${escapeHtml(data.tipo_identificacion)}</dd></div><div><dt>Identificación</dt><dd>${escapeHtml(data.identificacion)}</dd></div><div><dt>Nombre completo</dt><dd>${escapeHtml(data.nombre_completo)}</dd></div><div><dt>Cama</dt><dd>${escapeHtml(data.cama)}</dd></div></dl></div>`;
      } catch (error) {
        resultBox.innerHTML = '<small class="patient-search-error">No fue posible conectar con el servidor.</small>';
      }
      return;
    }

    resultBox.innerHTML = '<small>Consultando la habitación...</small>';
    resultBox.hidden = false;
    try {
      const response = await fetch(`/api/buscar-usuario?q=${encodeURIComponent(query)}&tipo=room`);
      const data = await response.json();
      if (!response.ok || !data.encontrado) {
        resultBox.innerHTML = `<small class="patient-search-error">${escapeHtml(data.mensaje || 'No encontramos resultados para ese dato.')}</small>`;
        return;
      }
      const patient = data.paciente;
      const statusClass = patient.estado === 'Activo' ? 'status-active' : patient.estado === 'Devuelto' ? 'status-returned' : 'status-overdue';
      resultBox.innerHTML = `<div class="patient-summary"><h2>Resultado de la búsqueda</h2><dl><div><dt>Nombre y apellido</dt><dd>${escapeHtml(patient.nombre)}</dd></div><div><dt>Número de documento (C.C. / T.I.)</dt><dd>${escapeHtml(patient.cedula)}</dd></div><div><dt>Control asignado</dt><dd>${escapeHtml(patient.control)}</dd></div><div><dt>Estado del préstamo</dt><dd><span class="table-status ${statusClass}">${escapeHtml(patient.estado)}</span></dd></div><div><dt>Días con el control</dt><dd>${escapeHtml(patient.dias_con_control)}</dd></div><div><dt>Valor por día</dt><dd>${money(patient.valor_diario)}</dd></div><div><dt>Valor total a pagar</dt><dd>${money(patient.valor_total)}</dd></div></dl></div>`;
    } catch (error) {
      resultBox.innerHTML = '<small class="patient-search-error">No fue posible conectar con el servidor Python.</small>';
    }
  });
  document.querySelector('#clear-search')?.addEventListener('click', () => {
    searchInput.value = '';
    document.querySelector('#patient-result').hidden = true;
    document.querySelector('#search-query').focus();
  });
}

const loanForm = document.querySelector('#loan-form');
if (loanForm) {
  const controlSelect = document.querySelector('#loan-control');
  const confirmPhysical = document.querySelector('#loan-confirm-control');
  const confirmBed = document.querySelector('#loan-confirm-bed');
  const roomSuggestions = document.querySelector('#room-suggestions');
  const roomInput = document.querySelector('#loan-room-number');
  const requiredBrand = document.querySelector('#loan-required-brand');
  const startDate = document.querySelector('#loan-start-date');
  let roomCatalog = new Map();
  let lookupSequence = 0;
  fetch('/api/inventario').then((response) => response.json()).then((inventoryData) => {
    if (!Array.isArray(inventoryData.habitaciones)) throw new Error(inventoryData.mensaje || 'Catálogo no disponible');
    roomCatalog = new Map(inventoryData.habitaciones.map((room) => [room.codigo.toUpperCase(), room]));
    roomSuggestions.innerHTML = inventoryData.habitaciones.map((room) => `<option value="${escapeHtml(room.codigo)}">${escapeHtml(room.torre)} · Piso ${escapeHtml(room.piso)} · ${escapeHtml(room.marca)}</option>`).join('');
    updateControlForRoom();
  }).catch(() => {
    requiredBrand.textContent = 'No se pudo cargar el catálogo de habitaciones.';
    controlSelect.replaceChildren(new Option('Catálogo no disponible', ''));
    controlSelect.disabled = true;
  });

  async function updateControlForRoom() {
    const sequence = ++lookupSequence;
    const roomCode = roomInput.value.trim().toUpperCase();
    const room = roomCatalog.get(roomCode);
    controlSelect.replaceChildren(new Option('Consultando controles de esta ubicación...', ''));
    controlSelect.disabled = true;
    if (!room) {
      controlSelect.replaceChildren(new Option('Selecciona una ubicación válida', ''));
      requiredBrand.textContent = roomCode ? 'Habitación no encontrada en el catálogo.' : 'Selecciona una habitación para consultar la marca requerida.';
      return;
    }

    requiredBrand.textContent = `Marca requerida: ${room.marca}`;
    try {
      const response = await fetch('/api/inventario/controles-disponibles');
      const data = await response.json();
      if (sequence !== lookupSequence) return;
      const controls = response.ok && Array.isArray(data.controles) ? data.controles : [];
      controlSelect.replaceChildren(new Option(
        controls.length ? 'Selecciona un control físico disponible' : 'No hay controles disponibles para asignar. Verifique el inventario',
        '',
      ));
      controls.forEach((control) => {
        controlSelect.add(new Option(
          [control.codigo, control.serial, control.marca].filter(Boolean).join(' · '),
          control.id,
        ));
      });
      controlSelect.disabled = controls.length === 0;
      if (!controls.length) requiredBrand.textContent = data.mensaje || 'No hay controles disponibles en el inventario.';
      else requiredBrand.textContent = `Marca registrada para la ubicación: ${room.marca}. Identifica el control físico antes de entregarlo.`;
    } catch (error) {
      if (sequence !== lookupSequence) return;
      controlSelect.replaceChildren(new Option('Inventario no disponible', ''));
      requiredBrand.textContent = 'No fue posible consultar el inventario físico de esta ubicación.';
    }
  }

  roomInput.addEventListener('input', () => {
    lookupSequence += 1;
    controlSelect.replaceChildren(new Option('Confirma una ubicación del catálogo', ''));
    controlSelect.disabled = true;
  });
  roomInput.addEventListener('change', updateControlForRoom);
  const today = new Date().toISOString().slice(0, 10);
  startDate.value = today;
  startDate.readOnly = true;
  loanForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!confirmBed.checked || !confirmPhysical.checked) { (!confirmBed.checked ? confirmBed : confirmPhysical).reportValidity(); return; }
    const response = await fetch('/api/prestamos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ documento: document.querySelector('#loan-document').value, nombre: document.querySelector('#loan-patient').value, recibe: document.querySelector('#loan-recipient').value, habitacion: document.querySelector('#loan-room-number').value, control: controlSelect.value, confirmar_cama: confirmBed.checked, confirmar_control_fisico: confirmPhysical.checked }) });
    const data = await response.json();
    window.alert(data.mensaje);
    if (response.ok) {
      loanForm.reset();
      startDate.value = today;
    }
  });
  loanForm.addEventListener('reset', () => {
    window.setTimeout(() => {
      startDate.value = today;
      updateControlForRoom();
    }, 0);
  });
}


const transferForm = document.querySelector('#transfer-form');
if (transferForm) {
  const lookupButton = document.querySelector('#transfer-lookup');
  const documentInput = document.querySelector('#transfer-patient-document');
  const status = document.querySelector('#transfer-status');
  const patientResult = document.querySelector('#transfer-patient-result');
  const originInput = document.querySelector('#transfer-origin');
  const destinationInput = document.querySelector('#transfer-destination');
  const destinationBed = document.querySelector('#transfer-destination-bed');
  const destinationBrand = document.querySelector('#transfer-destination-brand-display');
  const destinationBrandValue = document.querySelector('#transfer-destination-brand');
  const newControl = document.querySelector('#transfer-new-control');
  const newRecipient = document.querySelector('#transfer-new-recipient');
  const newRelationship = document.querySelector('#transfer-new-relationship');
  const submitButton = document.querySelector('#transfer-submit');
  const disposition = document.querySelector('#transfer-disposition');
  const oldRecipient = document.querySelector('#transfer-old-recipient');
  const oldRelationship = document.querySelector('#transfer-old-relationship');
  let validPatient = null;
  let activeLoan = null;
  let completed = false;

  function updateTransferReady() {
    const dispositionValid = activeLoan
      ? ['returned', 'pending'].includes(disposition.value)
      : disposition.value === 'pending';
    const newControlValid = !newControl.value || (newRecipient.value.trim() && newRelationship.value);
    const oldRecipientValid = !activeLoan || disposition.value !== 'returned' || (oldRecipient.value.trim() && oldRelationship.value);
    submitButton.disabled = completed || !validPatient || !destinationBed.value || !dispositionValid || !newControlValid || !oldRecipientValid;
  }

  async function chooseDestination(code) {
    newControl.replaceChildren(new Option('Consultando inventario...', ''));
    newControl.disabled = true;
    destinationBrand.value = '';
    destinationBrandValue.value = '';
    newRecipient.value = document.querySelector('#transfer-responsible').value;
    newRelationship.value = '';
    try {
      const inventoryResponse = await fetch('/api/catalogo/ubicaciones/' + encodeURIComponent(code) + '/controles');
      const inventory = await inventoryResponse.json();
      if (!inventoryResponse.ok || !Array.isArray(inventory.controles)) throw new Error(inventory.mensaje || 'No fue posible consultar el inventario.');
      destinationBed.value = inventory.ubicacion.ubicacion_codigo;
      destinationBrand.value = inventory.marca_requerida || inventory.ubicacion.marca_control_requerida || '';
      destinationBrandValue.value = destinationBrand.value;
      newControl.replaceChildren(new Option('', ''));
      inventory.controles.forEach((control) => newControl.add(new Option(control.id, control.id)));
      newControl.disabled = false;
      newControl.value = inventory.controles.length ? String(inventory.controles[0].id) : '';
      newRecipient.required = Boolean(newControl.value);
      newRelationship.required = Boolean(newControl.value);
      document.querySelector('#transfer-destination-status').textContent = inventory.controles.length
        ? `Marca asignada a la habitaci\u00f3n de destino: ${destinationBrand.value}. Se asign\u00f3 autom\u00e1ticamente un control disponible.`
        : (inventory.mensaje || `Marca requerida para el destino: ${destinationBrand.value}. No hay unidades disponibles.`);
      updateTransferReady();
    } catch (error) {
      destinationBed.value = '';
      destinationBrand.value = '';
      destinationBrandValue.value = '';
      newControl.replaceChildren(new Option('Inventario no disponible', ''));
      newControl.disabled = true;
      document.querySelector('#transfer-destination-status').textContent = error.message;
      updateTransferReady();
    }
  }

  async function loadDestinationRoom() {
    const typed = destinationInput.value.trim().toUpperCase();
    destinationBed.replaceChildren(new Option(typed ? 'Consultando camas reales...' : 'Primero ingresa una habitaci\u00f3n', ''));
    destinationBed.disabled = true;
    newControl.replaceChildren(new Option('Selecciona una cama de destino', ''));
    newControl.disabled = true;
    destinationBrand.value = '';
    destinationBrandValue.value = '';
    if (!typed) { updateTransferReady(); return; }
    try {
      const response = await fetch('/api/catalogo/ubicaciones');
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.ubicaciones)) throw new Error(data.mensaje || 'No fue posible consultar las camas.');
      const matches = data.ubicaciones.filter((item) => {
        const code = String(item.codigo || item.ubicacion_codigo || '').trim().toUpperCase();
        return String(item.habitacion || '').trim().toUpperCase() === typed || code === typed || code.startsWith(typed + '-');
      });
      destinationBed.replaceChildren(new Option(matches.length ? 'Selecciona una cama real' : 'No hay camas catalogadas para esta habitaci\u00f3n', ''));
      matches.forEach((item) => {
        const code = item.codigo || item.ubicacion_codigo;
        destinationBed.add(new Option(code, code));
      });
      destinationBed.disabled = matches.length === 0;
      if (matches.length) { destinationBed.value = destinationBed.options[1].value; await chooseDestination(destinationBed.value); }
      if (!matches.length) document.querySelector('#transfer-destination-status').textContent = data.mensaje || 'La habitaci\u00f3n no tiene camas registradas en el catalogo.';
    } catch (error) {
      destinationBed.replaceChildren(new Option('No se pudieron consultar las camas', ''));
      document.querySelector('#transfer-destination-status').textContent = error.message;
    }
    updateTransferReady();
  }

  async function validateTransferPatient(candidate) {
    const response = await fetch('/api/paciente/identificacion/' + encodeURIComponent(candidate.identificacion));
    const patient = await response.json();
    if (!response.ok) throw new Error(patient.mensaje || 'No se encontró un paciente válido.');
    validPatient = Object.assign({}, patient, {cama: candidate.cama || patient.cama});
    document.querySelector('#transfer-patient-name').textContent = validPatient.nombre_completo || 'Sin nombre';
    document.querySelector('#transfer-patient-identity').textContent = validPatient.identificacion || '';
    patientResult.hidden = false;
    document.querySelector('#transfer-room-choices').hidden = true;
    const loansResponse = await fetch('/api/prestamos');
    const loansData = await loansResponse.json();
    if (!loansResponse.ok) throw new Error(loansData.mensaje || 'No se pudo consultar el historial de préstamos.');
    activeLoan = loansData.prestamos.find((item) => item.documento === validPatient.identificacion && item.estado === 'ACTIVO') || null;
    const canonicalTransferLocation = (value) => {
      const code = String(value || '').trim().toUpperCase();
      const compactBed = code.match(/^([0-9]{3})([0-9])$/);
      return compactBed ? `${compactBed[1]}-${compactBed[2]}` : code;
    };
    const patientLocation = canonicalTransferLocation(validPatient.cama);
    const activeLoanLocation = canonicalTransferLocation(activeLoan?.habitacion_actual || activeLoan?.habitacion);
    const location = activeLoanLocation || patientLocation;
    originInput.dataset.locationCode = location;
    originInput.value = String(location);
    document.querySelector('#transfer-current-status').value = activeLoan
      ? (activeLoan.marca || activeLoan.control_marca || '')
      : 'Sin préstamo activo';
    disposition.required = true;
    disposition.value = activeLoan ? '' : 'pending';
    disposition.querySelector('option[value="returned"]').disabled = !activeLoan;
    oldRecipient.required = false;
    oldRelationship.required = false;
    destinationInput.disabled = false;
    destinationInput.focus();
    status.textContent = 'Paciente validado';
    status.hidden = false;
    status.className = 'workflow-status workflow-status-success';
    updateTransferReady();
  }

  lookupButton.addEventListener('click', async () => {
    const query = documentInput.value.trim();
    const mode = document.querySelector('#transfer-search-type').value;
    const choices = document.querySelector('#transfer-room-choices');
    if (!query) { documentInput.focus(); documentInput.reportValidity(); return; }
    lookupButton.disabled = true;
    completed = false;
    status.hidden = false;
    status.textContent = 'Consultando paciente y préstamo activo...';
    status.className = 'workflow-status';
    validPatient = null;
    activeLoan = null;
    submitButton.disabled = true;
    patientResult.hidden = true;
    choices.hidden = true;
    choices.replaceChildren();
    destinationInput.value = '';
    destinationInput.disabled = true;
    destinationBed.replaceChildren(new Option('Primero valida el paciente', ''));
    destinationBed.disabled = true;
    newControl.replaceChildren(new Option('Selecciona una cama de destino', ''));
    newControl.disabled = true;
    document.querySelector('#transfer-current-status').value = 'Sin préstamo activo';
    disposition.value = '';
    disposition.querySelector('option[value="returned"]').disabled = false;
    oldRecipient.value = '';
    oldRecipient.required = false;
    oldRelationship.value = '';
    oldRelationship.required = false;
    newRecipient.value = document.querySelector('#transfer-responsible').value;
    newRelationship.value = '';
    destinationBrand.value = '';
    destinationBrandValue.value = '';
    try {
      const endpoint = mode === 'habitacion' ? '/api/paciente/habitacion/' : '/api/paciente/identificacion/';
      const response = await fetch(endpoint + encodeURIComponent(query));
      const result = await response.json();
      if (!response.ok) throw new Error(result.mensaje || 'No se encontró el paciente.');
      if (mode === 'habitacion') {
        if (!Array.isArray(result.pacientes) || !result.pacientes.length) throw new Error('No hay pacientes hospitalizados en esa habitación.');
        if (result.pacientes.length === 1) await validateTransferPatient(result.pacientes[0]);
        else {
          status.textContent = 'Selecciona el paciente y la cama para continuar.';
          choices.replaceChildren(...result.pacientes.map((candidate) => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'room-patient-card';
            option.innerHTML = `<strong>${escapeHtml(candidate.nombre_completo || 'Nombre no informado')}</strong><span>CC: ${escapeHtml(candidate.identificacion)}</span><span>Habitación y cama: ${escapeHtml(candidate.cama)}</span><b>Seleccionar</b>`;
            option.addEventListener('click', async () => {
              choices.querySelectorAll('button').forEach((button) => { button.disabled = true; });
              try { await validateTransferPatient(candidate); }
              catch (error) { status.textContent = error.message; status.className = 'workflow-status workflow-status-error'; }
            });
            return option;
          }));
          choices.hidden = false;
        }
      } else await validateTransferPatient(result);
    } catch (error) {
      validPatient = null;
      status.textContent = error.message;
      status.className = 'workflow-status workflow-status-error';
    } finally { lookupButton.disabled = false; }
  });

  document.querySelector('#transfer-search-type').addEventListener('change', (event) => {
    const byRoom = event.target.value === 'habitacion';
    document.querySelector('#transfer-query-label').textContent = byRoom ? 'Número de Habitación' : 'Número de Identificación';
    documentInput.placeholder = byRoom ? 'Ej. 307' : 'Ingresa el documento';
    documentInput.value = '';
  });
  documentInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); lookupButton.click(); } });
  destinationInput.addEventListener('change', loadDestinationRoom);
  destinationInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); loadDestinationRoom(); } });
  destinationBed.addEventListener('change', () => { if (destinationBed.value) chooseDestination(destinationBed.value); });
  disposition.addEventListener('change', () => {
    oldRecipient.required = Boolean(activeLoan && disposition.value === 'returned');
    oldRelationship.required = Boolean(activeLoan && disposition.value === 'returned');
    updateTransferReady();
  });
  oldRecipient.addEventListener('input', updateTransferReady);
  oldRelationship.addEventListener('change', updateTransferReady);
  newControl.addEventListener('change', () => {
    newRecipient.required = Boolean(newControl.value);
    newRelationship.required = Boolean(newControl.value);
    updateTransferReady();
  });
  newRecipient.addEventListener('input', updateTransferReady);
  newRelationship.addEventListener('change', updateTransferReady);

  transferForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!validPatient) {
      status.hidden = false;
      status.textContent = 'Busca y valida al paciente antes de registrar el traslado.';
      status.className = 'workflow-status workflow-status-error';
      return;
    }
    newRecipient.required = Boolean(newControl.value);
    newRelationship.required = Boolean(newControl.value);
    oldRecipient.required = Boolean(activeLoan && disposition.value === 'returned');
    oldRelationship.required = Boolean(activeLoan && disposition.value === 'returned');
    if (!transferForm.reportValidity()) return;
    submitButton.disabled = true;
    document.querySelector('#transfer-new-date').value = localDateTimeValue();
    try {
      const observation = [
        oldRecipient.value.trim() ? `Persona que entrega el control anterior: ${oldRecipient.value.trim()}` : '',
        oldRelationship.value ? `Parentesco: ${oldRelationship.value}` : '',
      ].filter(Boolean).join('. ');
      const response = await fetch('/api/traslados', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documento: validPatient.identificacion, origen: originInput.dataset.locationCode || originInput.value,
          destino: destinationBed.value, novedad_control: activeLoan ? disposition.value : 'no_control',
          devolucion_confirmada: Boolean(activeLoan && disposition.value === 'returned'), responsable: document.querySelector('#transfer-responsible').value,
          recibe_control_anterior: oldRecipient.value, parentesco_control_anterior: oldRelationship.value, observacion: observation,
          nuevo_control: newControl.value || null, recibe_nuevo_control: newRecipient.value,
          parentesco_nuevo_control: newRelationship.value, confirmar_control_fisico: Boolean(newControl.value) }) });
      const result = await response.json();
      status.hidden = false;
      status.textContent = response.ok
        ? (newControl.value ? '\u00a1Cambio exitoso! Nuevo pr\u00e9stamo registrado correctamente.' : '\u00a1Cambio exitoso! Traslado registrado correctamente.')
        : (result.mensaje || 'No se pudo registrar el traslado.');
      status.className = 'workflow-status ' + (response.ok ? 'workflow-status-success' : 'workflow-status-error');
      if (response.ok) { completed = true; validPatient = null; await refreshDashboardCounts(); await refreshHistory(); }
    } catch (error) {
      status.hidden = false;
      status.textContent = 'No se pudo conectar con el servidor. No se confirm\u00f3 el traslado.';
      status.className = 'workflow-status workflow-status-error';
    } finally { submitButton.disabled = completed || !validPatient; }
  });
}
const historyFilter = document.querySelector('#history-filter');
if (historyFilter) {
  const historyRows = [...document.querySelectorAll('.table-panel tbody tr')];
  historyFilter.addEventListener('input', () => {
    const query = historyFilter.value.trim().toLocaleLowerCase();
    historyRows.forEach((row) => {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
    });
  });
  document.querySelector('#clear-history')?.addEventListener('click', () => {
    historyFilter.value = '';
    historyFilter.dispatchEvent(new Event('input'));
    historyFilter.focus();
  });
  document.querySelector('#refresh-history')?.addEventListener('click', () => window.location.reload());
}

const metricCards = document.querySelectorAll('.metric-card');
const metricDetail = document.querySelector('#metric-detail');
const metricDetailTitle = document.querySelector('#metric-detail-title');
const metricDetailCopy = document.querySelector('#metric-detail-copy');
const metricDetailRows = document.querySelector('#metric-detail-rows');
const metricBack = document.querySelector('.metric-back');

const metricDetails = {
  'in-use': {title:'Controles en uso actualmente', copy:'Movimientos activos consultados desde la base de datos.', rows:[]},
  available: {title:'Controles disponibles', copy:'Inventario disponible consultado desde la base de datos.', rows:[]},
  overdue: {title:'Seguimiento de pr?stamos', copy:'Pr?stamos activos que requieren seguimiento.', rows:[]}
};

const showMetricDetail = async (metric) => {
  const detail = metricDetails[metric];
  if (!detail || !metricDetail) return;
  metricDetailTitle.textContent = detail.title;
  metricDetailCopy.textContent = detail.copy;
  metricDetailRows.innerHTML = '<tr><td colspan="4">Consultando registros...</td></tr>';
  metricDetail.hidden = false;
  try {
    let rows = [];
    if (metric === 'available') {
      const response = await fetch('/api/controles-disponibles'); const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo consultar el inventario.');
      rows = (data.controles || []).map(item => [item.codigo, item.ubicacion_asignada || 'Oficina de pr?stamos', '?', 'Disponible']);
    } else {
      const response = await fetch('/api/prestamos'); const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo consultar el historial.');
      rows = (data.prestamos || []).filter(item => item.estado === 'ACTIVO').map(item => [item.control, item.habitacion_actual, new Date(item.fecha_entrega).toLocaleString('es-CO'), item.estado_control === 'PENDIENTE_DEVOLUCION' ? 'Pendiente de devoluci?n' : 'En uso']);
    }
    metricDetailRows.innerHTML = rows.length ? rows.map(row => '<tr><td>' + escapeHtml(row[0]) + '</td><td>' + escapeHtml(row[1]) + '</td><td>' + escapeHtml(row[2]) + '</td><td>' + escapeHtml(row[3]) + '</td></tr>').join('') : '<tr><td colspan="4">No hay registros para mostrar.</td></tr>';
  } catch (error) { metricDetailRows.innerHTML = '<tr><td colspan="4">' + escapeHtml(error.message) + '</td></tr>'; }
  metricDetail.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

metricCards.forEach((card) => {
  const openDetail = () => showMetricDetail(card.dataset.metric);
  card.addEventListener('click', openDetail);
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openDetail();
    }
  });
});

if (metricBack) {
  metricBack.addEventListener('click', () => {
    metricDetail.hidden = true;
    document.querySelector('.home-stat-grid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

const historySearchForm = document.querySelector('#history-search-form');
if (historySearchForm) {
  const searchType = document.querySelector('#history-search-type');
  const queryInput = document.querySelector('#history-query');
  const queryLabel = document.querySelector('#history-query-label');
  const searchButton = document.querySelector('#history-search-button');
  const searchStatus = document.querySelector('#history-search-status');
  const patientChoices = document.querySelector('#history-patient-choices');
  const detailModal = document.querySelector('#history-patient-modal');
  let currentBillingContext = null;

  function setHistorySearchStatus(message, isError = false) {
    searchStatus.hidden = !message;
    searchStatus.textContent = message;
    searchStatus.className = 'workflow-status' + (isError ? ' workflow-status-error' : '');
  }

  async function readHistoryJson(response, fallbackMessage) {
    if (!response.headers.get('content-type')?.includes('application/json')) {
      if (response.redirected) {
        throw new Error('La sesión expiró. Inicia sesión nuevamente y vuelve a autorizar la salida.');
      }
      if (response.status === 404) {
        throw new Error('La ruta de autorización no está cargada en Flask (HTTP 404). Reinicia el servidor y vuelve a intentarlo.');
      }
      if (response.status === 405) {
        const allowedMethods = response.headers.get('allow');
        throw new Error(`La ruta ${response.url} no acepta la solicitud enviada (HTTP 405${allowedMethods ? `; métodos permitidos: ${allowedMethods}` : ''}). Reinicia la instancia Flask que está atendiendo esta página.`);
      }
      throw new Error(`El servidor respondió HTTP ${response.status} sin JSON. ${fallbackMessage}`);
    }
    return response.json();
  }

  function calendarDaysSince(startValue) {
    const [year, month, day] = String(startValue).slice(0, 10).split('-').map(Number);
    const start = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.max(1, Math.floor((today - start) / 86400000));
  }

  function updateBillingPreanalysis() {
    const service = document.querySelector('input[name="history-service-used"]:checked')?.value || '';
    document.querySelector('#history-generate-invoice').disabled = !service;
  }

  async function loadCurrentLoanDetail(patient) {
    let response;
    try {
      response = await fetch('/api/historial/prestamo-actual?documento=' + encodeURIComponent(patient.identificacion), { cache: 'no-store' });
      if (response.status !== 404 && response.headers.get('content-type')?.includes('application/json')) {
        const detail = await response.json();
        if (!response.ok) throw new Error(detail.mensaje || 'No se pudo consultar el préstamo actual.');
        if (String(detail.paciente?.documento || '') !== String(patient.identificacion || '')) throw new Error('El documento del prestamo consultado no coincide con el paciente seleccionado. Vuelve a buscarlo.');
        return detail;
      }
    } catch (error) {
      if (error.message !== 'Failed to fetch') throw error;
    }

    const loansResponse = await fetch('/api/prestamos', { cache: 'no-store' });
    const loansData = await readHistoryJson(loansResponse, 'El servidor no respondió en formato JSON. Reinicia Flask e inténtalo de nuevo.');
    if (!loansResponse.ok) throw new Error(loansData.mensaje || 'No se pudo consultar el historial de préstamos.');
    const activeLoan = (loansData.prestamos || []).find((loan) =>
      loan.documento === patient.identificacion && loan.estado === 'ACTIVO');
    if (!activeLoan) {
      return {
        paciente: {
          nombre: patient.nombre_completo || 'Paciente NN',
          documento: patient.identificacion,
          ubicacion: patient.cama || 'No informada',
        },
        prestamo: null,
      };
    }
    const days = calendarDaysSince(activeLoan.fecha_entrega);
    return {
      paciente: {
        nombre: activeLoan.nombre || document.querySelector('#history-patient-name').textContent,
        documento: activeLoan.documento,
        ubicacion: activeLoan.habitacion_actual || activeLoan.habitacion,
      },
      prestamo: {
        id: activeLoan.id,
        marca: activeLoan.marca || 'No informada',
        estado: 'ACTIVO',
        fecha_entrega: activeLoan.fecha_entrega,
        dias_servicio: days,
        total: activeLoan.exoneracion_categoria ? 0 : days * 3000,
        exoneracion_categoria: activeLoan.exoneracion_categoria,
      },
    };
  }

  async function showPatientLoan(candidate) {
    setHistorySearchStatus('Validando paciente y consultando el préstamo actual...');
    patientChoices.hidden = true;
    let patient;
    if (candidate.origen_datos === 'prestamo_local') {
      patient = candidate;
    } else {
      const patientResponse = await fetch('/api/paciente/identificacion/' + encodeURIComponent(candidate.identificacion));
      patient = await readHistoryJson(patientResponse, 'No fue posible validar el paciente.');
      if (!patientResponse.ok) throw new Error(patient.mensaje || 'No se pudo validar el paciente.');
      if (String(patient.identificacion) !== String(candidate.identificacion)) throw new Error('El documento no coincide con el paciente de la habitacion.');
    }

    const patientDocument = document.querySelector('#history-patient-document');
    const validatedPatient = Object.assign({}, patient, { cama: candidate.cama || patient.cama });
    const data = await loadCurrentLoanDetail(validatedPatient);

    document.querySelector('#history-patient-name').textContent = data.paciente.nombre || 'Paciente NN';
    patientDocument.textContent = `${patient.tipo_identificacion || 'Documento'}: ${data.paciente.documento}`;
    document.querySelector('#history-location').textContent = data.paciente.ubicacion || patient.cama || 'No informada';
    const loan = data.prestamo;
    currentBillingContext = { patient: data.paciente, loan, authorization: data.autorizacion_salida || null };
    const loanStatus = document.querySelector('#history-loan-status');
    const returnForm = document.querySelector('#history-loan-return-form');
    const returnStatus = document.querySelector('#history-return-status');
    const authorizationStatus = document.querySelector('#history-authorization-status');
    returnStatus.hidden = true;
    returnStatus.textContent = '';
    authorizationStatus.hidden = true;
    authorizationStatus.textContent = '';
    authorizationStatus.classList.remove('is-success', 'is-error');
    document.querySelector('#history-return-dashboard').hidden = true;
    document.querySelector('#history-end-date').textContent = new Date().toLocaleString('es-CO');
    document.querySelectorAll('input[name="history-service-used"]').forEach((input) => { input.checked = false; });
    if (data.autorizacion_salida) {
      const approval = data.autorizacion_salida;
      const serviceOption = document.querySelector(`input[name="history-service-used"][value="${approval.uso_servicio ? 'si' : 'no'}"]`);
      if (serviceOption) serviceOption.checked = true;
      const actionLabel = approval.tipo_autorizacion === 'pago' ? 'Pago autorizado' : 'Salida exenta autorizada';
      authorizationStatus.textContent = `Última acción: ${actionLabel} · ${new Date(approval.autorizado_at).toLocaleString('es-CO')} · ${approval.autorizado_por}.`;
      authorizationStatus.className = 'history-return-status is-success';
      authorizationStatus.hidden = false;
    }
    if (loan) {
      loanStatus.textContent = 'En uso';
      loanStatus.className = 'history-loan-status is-active';
      document.querySelector('#history-brand').textContent = loan.marca || 'No informada';
      document.querySelector('#history-start-date').textContent = new Date(loan.fecha_entrega).toLocaleString('es-CO');
      document.querySelector('#history-service-days').textContent = `${loan.dias_servicio} ${loan.dias_servicio === 1 ? 'día' : 'días'}`;
      document.querySelector('#history-total').textContent = money(loan.total) + ' COP';
      returnForm.dataset.loanId = loan.id;
      const currentAuthorization = data.autorizacion_salida;
      const paymentAuthorized = currentAuthorization?.tipo_autorizacion === 'pago'
        && String(currentAuthorization.prestamo_id) === String(loan.id)
        && Boolean(currentAuthorization.uso_servicio);
      returnForm.hidden = loan.exoneracion_categoria
        ? !loan.salida_autorizada_at
        : !paymentAuthorized;
      document.querySelector('#history-return-recipient').value = '';
    } else {
      loanStatus.textContent = 'Sin préstamo activo';
      loanStatus.className = 'history-loan-status is-inactive';
      document.querySelector('#history-brand').textContent = '—';
      document.querySelector('#history-start-date').textContent = '—';
      document.querySelector('#history-service-days').textContent = '0 días';
      document.querySelector('#history-total').textContent = money(0) + ' COP';
      returnForm.hidden = true;
      delete returnForm.dataset.loanId;
    }
    updateBillingPreanalysis();
    setHistorySearchStatus('');
    detailModal.showModal();
  }

  searchType.addEventListener('change', () => {
    const byRoom = searchType.value === 'habitacion';
    queryLabel.textContent = byRoom ? 'Número de Habitación / Cama' : 'Número de Identificación';
    queryInput.placeholder = byRoom ? 'Ingresa la habitación/cama' : 'Ingresa el documento';
    queryInput.inputMode = byRoom ? 'text' : 'numeric';
    queryInput.value = '';
    patientChoices.replaceChildren();
    patientChoices.hidden = true;
    setHistorySearchStatus('');
  });

  searchButton.addEventListener('click', () => {
    if (!queryInput.value.trim()) queryInput.reportValidity();
  });

  historySearchForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (!query) { queryInput.reportValidity(); return; }
    searchButton.disabled = true;
    patientChoices.replaceChildren();
    patientChoices.hidden = true;
    setHistorySearchStatus('Buscando paciente...');
    try {
      const byRoom = searchType.value === 'habitacion';
      const endpoint = byRoom ? '/api/paciente/habitacion/' : '/api/paciente/identificacion/';
      const response = await fetch(endpoint + encodeURIComponent(query) + (byRoom ? '?contexto=cobro' : ''), { cache: 'no-store' });
      const result = await readHistoryJson(response, 'El servidor no respondió en formato JSON. Reinicia Flask e inténtalo de nuevo.');
      if (!response.ok) throw new Error(result.mensaje || 'No se encontró el paciente.');
      if (!byRoom) {
        await showPatientLoan(result);
      } else if (result.pacientes.length === 1) {
        await showPatientLoan(result.pacientes[0]);
      } else {
        patientChoices.replaceChildren(...result.pacientes.map((candidate) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'history-patient-choice';
          const name = document.createElement('strong');
          name.textContent = candidate.nombre_completo || 'Paciente NN';
          const detail = document.createElement('span');
          detail.textContent = `${candidate.tipo_identificacion || 'Documento'}: ${candidate.identificacion} · Habitación/cama: ${candidate.cama || 'No informada'}`;
          button.append(name, detail);
          button.addEventListener('click', async () => {
            patientChoices.querySelectorAll('button').forEach((choice) => { choice.disabled = true; });
            try { await showPatientLoan(candidate); }
            catch (error) { setHistorySearchStatus(error.message, true); }
            finally { patientChoices.querySelectorAll('button').forEach((choice) => { choice.disabled = false; }); }
          });
          return button;
        }));
        patientChoices.hidden = false;
        setHistorySearchStatus('La habitación tiene varios pacientes. Selecciona uno para ver el detalle.');
      }
    } catch (error) {
      setHistorySearchStatus(error.message || 'No fue posible consultar el paciente.', true);
    } finally { searchButton.disabled = false; }
  });

  document.querySelector('#history-modal-close').addEventListener('click', () => detailModal.close());
  detailModal.addEventListener('click', (event) => { if (event.target === detailModal) detailModal.close(); });
  document.querySelectorAll('input[name="history-service-used"]').forEach((input) => input.addEventListener('change', updateBillingPreanalysis));

  document.querySelector('#history-generate-invoice').addEventListener('click', () => {
    const serviceUsed = document.querySelector('input[name="history-service-used"]:checked')?.value;
    if (!currentBillingContext || !serviceUsed) {
      const status = document.querySelector('#history-authorization-status');
      status.className = 'history-return-status is-error';
      status.hidden = false;
      status.textContent = 'Confirma si el paciente utilizó el servicio antes de generar el comprobante.';
      document.querySelector('.history-service-used').focus();
      return;
    }
    const patient = currentBillingContext.patient;
    const loan = currentBillingContext.loan;
    const generatedAt = new Date();
    document.querySelector('#history-end-date').textContent = generatedAt.toLocaleString('es-CO');
    const startDate = loan?.fecha_entrega ? new Date(loan.fecha_entrega).toLocaleString('es-CO') : 'Sin préstamo activo';
    const amount = serviceUsed === 'no' ? 0 : Number(loan?.total || 0);
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      window.alert('Permite ventanas emergentes para generar e imprimir el comprobante.');
      return;
    }
    const rows = [
      ['Paciente', patient.nombre || 'Paciente NN'],
      ['Documento', patient.documento || 'No informado'],
      ['Ubicación actual', patient.ubicacion || 'No informada'],
      ['Control TV', loan?.control || loan?.marca || 'No informado'],
      ['Marca', loan?.marca || 'No informada'],
      ['Préstamo desde', startDate],
      ['Corte de cobro', generatedAt.toLocaleString('es-CO')],
      ['Días de servicio', loan?.dias_servicio || 0],
      ['¿Utilizó el servicio?', serviceUsed === 'si' ? 'Sí' : 'No'],
      ['Total', `${money(amount)} COP`],
    ];
    const invoiceRows = rows.map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`).join('');
    printWindow.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Comprobante de cobro</title><style>body{font-family:Arial,sans-serif;color:#18324a;margin:2rem auto;max-width:760px;padding:0 1rem}h1{text-align:center;font-size:1.5rem}p{line-height:1.5}table{width:100%;border-collapse:collapse;margin:1.5rem 0}th,td{padding:.65rem;border-bottom:1px solid #dce7f0;text-align:left}th{width:38%;color:#587089}.total{font-size:1.15rem;font-weight:bold}.signature{margin-top:3rem;display:flex;justify-content:space-between;gap:2rem}.signature span{width:45%;border-top:1px solid #71859a;padding-top:.4rem;text-align:center}@media print{button{display:none}}</style></head><body><h1>Comprobante de cobro</h1><table>${invoiceRows}</table><p class="total">Total: ${escapeHtml(money(amount))} COP</p><div class="signature"><span>Paciente / responsable</span><span>Ejecutivo de cuenta</span></div><p>Generado el ${escapeHtml(generatedAt.toLocaleString('es-CO'))}</p></body></html>`);
    printWindow.document.close();
    printWindow.focus();
    document.querySelector('#history-return-dashboard').hidden = false;
    window.setTimeout(() => printWindow.print(), 250);
  });
  document.querySelector('#history-loan-return-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const returnForm = event.currentTarget;
    const loanId = returnForm.dataset.loanId;
    const recipient = document.querySelector('#history-return-recipient').value.trim();
    const returnButton = document.querySelector('#history-return-button');
    const returnStatus = document.querySelector('#history-return-status');
    if (!loanId || !recipient) { returnForm.reportValidity(); return; }
    returnButton.disabled = true;
    returnStatus.hidden = true;
    try {
      const response = await fetch(`/api/prestamos/${encodeURIComponent(loanId)}/devolucion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recibe: recipient }),
      });
      const result = await readHistoryJson(response, 'El servidor no respondió en formato JSON. Reinicia Flask e inténtalo de nuevo.');
      if (!response.ok) throw new Error(result.mensaje || 'No se pudo registrar la devolución.');
      document.querySelector('#history-loan-status').textContent = 'Devuelto';
      document.querySelector('#history-loan-status').className = 'history-loan-status is-inactive';
      returnForm.hidden = true;
      returnStatus.textContent = result.mensaje || 'Devolución registrada correctamente.';
      returnStatus.className = 'history-return-status is-success';
      returnStatus.hidden = false;
      document.querySelector('#history-return-dashboard').hidden = false;
      document.querySelector('#history-loan-status').textContent = 'Salida autorizada · control devuelto';
      document.querySelector('#history-loan-status').className = 'history-loan-status is-inactive';
      document.querySelector('#history-brand').textContent = '—';
      document.querySelector('#history-start-date').textContent = '—';
      document.querySelector('#history-service-days').textContent = '0 días';
      document.querySelector('#history-total').textContent = money(result.valor_total || 0) + ' COP';
      await refreshDashboardCounts();
      await refreshHistory();
    } catch (error) {
      returnStatus.textContent = error.message || 'No se pudo registrar la devolución.';
      returnStatus.className = 'history-return-status is-error';
      returnStatus.hidden = false;
    } finally { returnButton.disabled = false; }
  });
  const requestedDocument = new URLSearchParams(window.location.search).get('documento');
  if (requestedDocument) {
    queryInput.value = requestedDocument;
    historySearchForm.requestSubmit();
  }
}
