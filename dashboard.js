const roomBrands = {
  '301': 'SONY', '302': 'SONY', '303': 'SONY', '304': 'SONY', '305': 'SAMSUNG', '306': 'SONY', '307': 'PANASONIC',
  '308-1': 'SAMSUNG', '308-2': 'SONY', '309-1': 'KALLEY', '309-2': 'SAMSUNG', '310-1': 'SONY', '310-2': 'KALLEY',
  '311-1': 'PANASONIC', '311-2': 'PANASONIC', '312': 'SONY', '313': 'SONY', '315': 'KALLEY', '316': 'SONY',
  '317-1': 'KALLEY', '317-2': 'KALLEY', '318': 'SONY', '319': 'SAMSUNG', '320': 'PANASONIC', '321': 'SONY',
  '322': 'SAMSUNG', '323': 'SONY', '324': 'KALLEY', '325': 'SAMSUNG', '326-1 Y 2': 'SONY', '327-1 Y 2': 'LG',
  '328-1 Y 2': 'SAMSUNG', '329-1 Y 2': 'SONY', '330-1 Y 2': 'SONY', '331-1 Y 2': 'SONY', '332-1 Y 2': 'SONY',
  '333-1 Y 2': 'KALLEY', '334': 'SONY', '335-1 Y 2': 'PANASONIC', '336-1 Y 2': 'SONY', '337-1 Y 2': 'SAMSUNG',
  '338-1 Y 2': 'SONY', '339-1 Y 2': 'SONY', '340-1 Y 2': 'SONY', '341-1 Y 2': 'SONY', '342': 'SAMSUNG',
  '343': 'SONY', '344': 'SAMSUNG', '345': 'SONY', '346': 'SAMSUNG', '347': 'SONY',
  '401-1': 'SONY', '401-2': 'SONY', '402-1': 'LG', '402-2': 'SONY', '403-1': 'SONY', '403-2': 'SONY',
  '404-1': 'SONY', '404-2': 'SONY', '405': 'LG', '406': 'SONY', '407': 'SONY', '408': 'PANASONIC',
  '409': 'KALLEY', '410': 'SONY', '411': 'SONY', '412-1': 'PANASONIC', '412-2': 'SONY', '413-1': 'SONY',
  '413-2': 'SONY', '414-1': 'PANASONIC', '415-1': 'SONY', '415-2': 'SAMSUNG', '416-1': 'KALLEY', '416-2': 'SONY',
  '417-1': 'SONY', '417-2': 'SONY', '418': 'SONY',
  '4T1-418': 'SAMSUNG', '4T1-419': 'KALLEY', '4T1-420': 'SONY', '4T1-421': 'SONY', '4T1-4221': 'SONY',
  '4T1-4222': 'SONY', '4T1-4231': 'SONY', '4T1-4232': 'SONY', '4T1-4241': 'KALLEY', '4T1-4242': 'SONY',
  '4T1-4251': 'SONY', '4T1-4252': 'SONY', '4T1-426': 'SONY', '4T1-4271': 'SONY', '4T1-4272': 'SONY',
  '4T1-4281': 'SAMSUNG', '4T1-4282': 'SONY', '4T1-4291': 'KALLEY', '4T1-4292': 'SONY', '4T1-4301': 'LG',
  '4T1-4311': 'SONY', '4T1-4312': 'SONY', '4T1-4322': 'SONY', '4T1-4331': 'SAMSUNG', '4T1-4342': 'SONY',
  '4T1-4351': 'SONY', '4T1-4352': 'SONY', '4T1-4361': 'SONY', '4T1-4362': 'SONY', '4T1-4371': 'SONY',
  '4T1-4372': 'SONY', '4T1-4381': 'SONY', '4T1-4382': 'SONY', '4T1-4391': 'SONY', '4T1-4392': 'SONY',
  '4T2': 'SONY', '5T3': 'SAMSUNG', '6T3': 'SONY',
  'UCE-1': 'SAMSUNG', 'UCE-2': 'SONY', 'UCE-3': 'PANASONIC', 'UCE-4': 'SONY', 'UCE-5': 'SONY',
  'UCE-6': 'LG', 'UCE-7': 'KALLEY', 'UCE-8': 'SONY', 'UCE-9': 'SAMSUNG', 'UCE-10': 'SONY',
  'UCE-11': 'SAMSUNG', 'UCE-12': 'SAMSUNG', 'UCE-13': 'SONY', 'UCE-14': 'SONY', 'UCE-15': 'SAMSUNG',
  'UCE-16': 'SAMSUNG', 'UCE-17': 'PANASONIC', 'UCE-18': 'SONY', 'UCE-19': 'SONY', 'UCE-20': 'SAMSUNG',
  'UCE-21': 'SONY', 'UCE-22': 'SAMSUNG', 'UCE-23': 'SAMSUNG', 'UCE-24': 'SAMSUNG', 'UCE-25': 'SAMSUNG',
  'UCE-26': 'SAMSUNG', 'UCE-27': 'SAMSUNG', 'UCE-28': 'SONY', 'UCE-29': 'SONY', 'UCE-30': 'SAMSUNG'
};

const roomEntries = Object.entries(roomBrands);
const controls = roomEntries.map(([room, brand]) => ({
  id: `CTRL-${String(roomEntries.findIndex(([name]) => name === room) + 1).padStart(3, '0')}`,
  room,
  brand,
  model: `TV · ${brand}`,
  location: room.includes('-') ? 'habitación especial' : 'habitación registrada',
  status: 'available'
}));

const statusLabels = { available: 'Disponible', loaned: 'En préstamo', repair: 'En revisión' };
const DAILY_RATE = 3000;
const grid = document.querySelector('#control-grid');
const activeLoans = document.querySelector('#active-loans');
const searchInput = document.querySelector('#search-query');
const searchForm = document.querySelector('#search-form');
const modal = document.querySelector('#loan-modal') || { hidden: true, addEventListener() {} };
const loanForm = document.querySelector('#loan-form');
const controlSelect = document.querySelector('#loan-control');
const roomInput = document.querySelector('#loan-room');
const roomNumberInput = document.querySelector('#loan-room-number');
const roomSuggestions = document.querySelector('#room-suggestions');
const roomBrandHint = document.querySelector('#room-brand-hint') || { textContent: '', classList: { add() {}, remove() {} } };
const rulesModal = document.querySelector('#rules-modal');
const patientResult = document.querySelector('#patient-result');
const loanDocument = document.querySelector('#loan-document');
let activeStatusFilter = 'all';
const testLoans = [
  { name: 'María González', document: '10000001', bed: '301-1', room: '301', control: 'CTRL-001', delivered: '24 sep 2026', returned: '26 sep 2026', status: 'En uso' },
  { name: 'Carlos Ramírez', document: '10000002', bed: '402-1', room: '402', control: 'CTRL-002', delivered: '24 sep 2026', returned: '27 sep 2026', status: 'En uso' },
  { name: 'Laura Torres', document: '10000003', bed: '305-1', room: '305', control: 'CTRL-006', delivered: '23 sep 2026', returned: '24 sep 2026', status: 'Devuelto' }
];

function availableCount() {
  return controls.filter((control) => control.status === 'available').length;
}

function formatElapsed(startedAt) {
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - startedAt) / 60000));
  return `${Math.floor(elapsedMinutes / 60)}h ${String(elapsedMinutes % 60).padStart(2, '0')}m`;
}

function loanDays(startedAt) {
  return Math.max(1, Math.ceil((Date.now() - startedAt) / 86400000));
}

function loanTotal(startedAt) {
  return loanDays(startedAt) * DAILY_RATE;
}

function money(value) {
  return `$${value.toLocaleString('es-CO')}`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
}

function renderSummary() {
  const available = availableCount();
  document.querySelector('#stat-available').textContent = available;
  document.querySelector('#stat-in-use').textContent = controls.filter((control) => control.status === 'loaned').length;
  document.querySelector('#availability-count').textContent = available;
  document.querySelector('#inventory-summary').textContent = `${available} de ${controls.length} disponibles`;
  document.querySelector('#loans-summary').textContent = `${controls.filter((control) => control.status === 'loaned').length} en curso`;
}

function matchesSearch(control, query) {
  const searchable = [control.id, control.brand, control.model, control.location, control.room].filter(Boolean).join(' ').toLowerCase();
  return searchable.includes(query.toLowerCase());
}

function renderControls() {
  const query = searchInput.value.trim();
  const visibleControls = controls.filter((control) => (activeStatusFilter === 'all' || control.status === activeStatusFilter) && matchesSearch(control, query));
  grid.innerHTML = visibleControls.map((control) => `
    <article class="control-card">
      <div class="control-card-heading">
        <h3>${control.id}</h3>
        <span class="status-badge status-${control.status}">${statusLabels[control.status]}</span>
      </div>
      <p>${control.brand} · ${control.location}</p>
      ${control.status === 'loaned' ? `<small>Hab. ${control.room} · ${control.patient}</small><small>${loanDays(control.startedAt)} día(s) · ${money(loanTotal(control.startedAt))}</small>` : control.status === 'repair' ? `<small>Desde ${new Date(control.repairStartedAt).toLocaleString('es-CO')}</small>` : '<small>&nbsp;</small>'}
      ${actionFor(control)}
    </article>
  `).join('');
  document.querySelector('#empty-results').hidden = visibleControls.length > 0;
  renderSummary();
}

function actionFor(control) {
  if (control.status === 'available') return `<button class="card-action card-action-primary" data-action="loan" data-control-id="${control.id}" type="button">Prestar</button>`;
  if (control.status === 'loaned') return `<button class="card-action" data-action="return" data-control-id="${control.id}" type="button">Devolver</button>`;
  return `<button class="card-action" data-action="repair" data-control-id="${control.id}" type="button">Marcar como reparado</button>`;
}

function renderLoans() {
  const loans = controls.filter((control) => control.status === 'loaned');
  activeLoans.innerHTML = loans.map((loan) => `
    <article class="active-loan-row">
      <div><strong>Habitación ${loan.room} · ${loan.patient}</strong><small>${loan.id} · prestado por ${loan.borrower} · ${loan.document || 'Cédula pendiente'}</small><small>${loanDays(loan.startedAt)} día(s) · ${money(loanTotal(loan.startedAt))}</small></div>
      <time data-started-at="${loan.startedAt}">${formatElapsed(loan.startedAt)}</time>
      <button class="card-action" data-action="return" data-control-id="${loan.id}" type="button">Devolver</button>
    </article>
  `).join('');
  renderSummary();
}

function showPatientResult(patient) {
  patientResult.innerHTML = `<div><strong>${escapeHtml(patient.name)}</strong><small>Documento: ${escapeHtml(patient.document)} · Cama: ${escapeHtml(patient.bed)} · Habitación: ${escapeHtml(patient.room)}</small><small>Control: ${escapeHtml(patient.control)} · Entrega: ${escapeHtml(patient.delivered)} · Devolución: ${escapeHtml(patient.returned)} · Estado: ${escapeHtml(patient.status)}</small></div><button class="primary-action" data-patient-room="${escapeHtml(patient.room)}" data-patient-name="${escapeHtml(patient.name)}" data-patient-document="${escapeHtml(patient.document)}" type="button">Nuevo préstamo</button>`;
  patientResult.hidden = false;
}

function renderPatientResult() {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) {
    patientResult.hidden = true;
    return;
  }

  const type = document.querySelector('input[name="search-type"]:checked').value;
  const patient = testLoans.find((loan) => (type === 'document' ? loan.document : loan.bed).toLowerCase() === query);
  if (patient) showPatientResult(patient);
  else patientResult.innerHTML = '<small class="patient-search-error">No encontramos un préstamo de prueba con ese dato.</small>';
  patientResult.hidden = false;
}

function updateTimers() {
  document.querySelectorAll('[data-started-at]').forEach((element) => {
    element.textContent = formatElapsed(Number(element.dataset.startedAt));
  });
}

function openModal(controlId) {
  const availableControls = controls.filter((control) => control.status === 'available');
  controlSelect.innerHTML = availableControls.map((control) => `<option value="${control.id}" data-room="${control.room}" data-brand="${control.brand}">${control.id} — ${control.brand}</option>`).join('');
  roomSuggestions.innerHTML = roomEntries.map(([room]) => `<option value="${room}">`).join('');
  if (controlId) controlSelect.value = controlId;
  modal.hidden = false;
  roomInput.focus();
}

function prefillRemotePatient(button) {
  roomInput.value = button.dataset.patientRoom;
  document.querySelector('#loan-patient').value = button.dataset.patientName;
  loanDocument.value = button.dataset.patientDocument;
  roomInput.dispatchEvent(new Event('input'));
}

function closeModal() {
  modal.hidden = true;
  loanForm.reset();
}

document.addEventListener('click', (event) => {
  const patientButton = event.target.closest('[data-patient-room]');
  if (patientButton) {
    openModal();
    prefillRemotePatient(patientButton);
    return;
  }
  const actionButton = event.target.closest('[data-action]');
  if (!actionButton) return;
  const control = controls.find((item) => item.id === actionButton.dataset.controlId);
  if (!control) return;
  if (actionButton.dataset.action === 'loan') openModal(control.id);
  if (actionButton.dataset.action === 'return') {
    control.status = 'available';
    delete control.room;
    delete control.patient;
    delete control.borrower;
    delete control.startedAt;
    renderControls();
    renderLoans();
  }
  if (actionButton.dataset.action === 'repair') {
    control.status = 'available';
    delete control.repairStartedAt;
    renderControls();
  }
});

searchForm.addEventListener('submit', (event) => { event.preventDefault(); renderPatientResult(); });
document.querySelectorAll('[data-status-filter]').forEach((button) => button.addEventListener('click', () => {
  activeStatusFilter = button.dataset.statusFilter;
  document.querySelectorAll('[data-status-filter]').forEach((item) => item.classList.toggle('is-active', item === button));
  renderControls();
}));
document.querySelector('#focus-new-loan').addEventListener('click', () => document.querySelector('#nuevo-prestamo').scrollIntoView({ behavior: 'smooth' }));
modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });

if (rulesModal) {
  document.querySelector('#open-rules-modal')?.addEventListener('click', () => { rulesModal.hidden = false; });
  document.querySelector('#close-rules-modal')?.addEventListener('click', () => { rulesModal.hidden = true; });
  rulesModal.addEventListener('click', (event) => { if (event.target === rulesModal) rulesModal.hidden = true; });
}

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (!modal.hidden) closeModal();
  if (rulesModal && !rulesModal.hidden) rulesModal.hidden = true;
});

roomNumberInput.addEventListener('input', () => {
  const room = roomNumberInput.value.trim().toUpperCase();
  const match = roomEntries.find(([name]) => name.toUpperCase() === room);
  if (!match) {
    roomBrandHint.textContent = 'La marca se seleccionará según la habitación.';
    roomBrandHint.classList.remove('is-confirmed');
    return;
  }
  const brand = match[1];
  const matchingControl = [...controlSelect.options].find((option) => option.dataset.room === match[0]);
  if (matchingControl) controlSelect.value = matchingControl.value;
  roomBrandHint.textContent = `Marca asignada: ${brand}`;
  roomBrandHint.classList.add('is-confirmed');
});

loanForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const control = controls.find((item) => item.id === controlSelect.value);
  if (!control) return;
  control.status = 'loaned';
  control.room = roomNumberInput.value.trim();
  control.patient = document.querySelector('#loan-patient').value.trim();
  control.document = loanDocument.value.trim();
  control.borrower = document.querySelector('#loan-borrower').value.trim();
  control.startedAt = Date.now();
  closeModal();
  renderControls();
  renderLoans();
  addRecentLoan(control);
});

const startDate = document.querySelector('#loan-start-date');
const endDate = document.querySelector('#loan-end-date');
const daysInput = document.querySelector('#loan-days');
const totalInput = document.querySelector('#loan-total');
const today = new Date().toISOString().slice(0, 10);
startDate.value = today;
endDate.value = today;
function updateLoanTotal() {
  const start = new Date(`${startDate.value}T00:00:00`);
  const end = new Date(`${endDate.value}T00:00:00`);
  const days = Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) ? 1 : Math.max(1, Math.ceil((end - start) / 86400000) + 1);
  daysInput.value = days;
  totalInput.value = money(days * DAILY_RATE);
}
startDate.addEventListener('change', updateLoanTotal);
endDate.addEventListener('change', updateLoanTotal);
loanForm.addEventListener('reset', () => setTimeout(() => {
  startDate.value = today;
  endDate.value = today;
  updateLoanTotal();
}));
updateLoanTotal();

function addRecentLoan(control) {
  const row = document.createElement('tr');
  row.innerHTML = `<td><strong>${escapeHtml(control.patient)}</strong><small>CC ${escapeHtml(control.document)}</small></td><td>${escapeHtml(control.room)}</td><td>${escapeHtml(control.id)}</td><td>${new Date().toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })}</td><td><span class="table-status status-active">Activo</span></td><td><button class="table-action" type="button">Ver</button></td>`;
  document.querySelector('#recent-loans').prepend(row);
}

openModal();
document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => {
  document.querySelectorAll('.nav-item').forEach((navItem) => navItem.classList.toggle('is-active', navItem === item));
}));

renderControls();
renderLoans();
setInterval(updateTimers, 30000);
setInterval(() => { renderControls(); renderLoans(); }, 60000);
