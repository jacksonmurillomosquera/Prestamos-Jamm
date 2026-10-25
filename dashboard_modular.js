const money = (value) => `$${value.toLocaleString('es-CO')}`;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

async function refreshDashboardCounts() {
  const response = await fetch('/api/dashboard/resumen');
  if (!response.ok) return;
  const data = await response.json();
  const available = document.querySelector('#count-available');
  const inUse = document.querySelector('#count-in-use');
  const pending = document.querySelector('#count-pending');
  if (available) available.textContent = data.disponibles;
  if (inUse) inUse.textContent = data.en_uso;
  if (pending) pending.textContent = data.pendientes;
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
        notice.textContent = result.mensaje || 'No se pudo registrar la entrega.';
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
    const location = activeLoan ? activeLoan.habitacion_actual : validPatient.cama || '';
    originInput.dataset.locationCode = location;
    originInput.value = String(location).replace(/-[0-9]+$/, '');
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
    status.hidden = historyLoans.length === 0;
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
        oldRecipient.value.trim() ? `Persona que entrega: ${oldRecipient.value.trim()}` : '',
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
