// ============================================================
// SHRISAMARTH Dashboard — seat grid interactivity
// ============================================================

const staffMain = document.querySelector('.staff-main');
const VOYAGE_ID = staffMain ? staffMain.dataset.voyageId : null;
const BASE_FARE = staffMain ? parseFloat(staffMain.dataset.baseFare) : 0;

// ============================================================
// COUNTRY CODE PHONE HELPER
// ============================================================
const COUNTRY_CODES = [
    { dial: '+91', flag: '🇮🇳', name: 'India' },
    { dial: '+1',  flag: '🇺🇸', name: 'USA / Canada' },
    { dial: '+44', flag: '🇬🇧', name: 'UK' },
    { dial: '+971', flag: '🇦🇪', name: 'UAE' },
    { dial: '+966', flag: '🇸🇦', name: 'Saudi Arabia' },
    { dial: '+974', flag: '🇶🇦', name: 'Qatar' },
    { dial: '+965', flag: '🇰🇼', name: 'Kuwait' },
    { dial: '+973', flag: '🇧🇭', name: 'Bahrain' },
    { dial: '+968', flag: '🇴🇲', name: 'Oman' },
    { dial: '+60',  flag: '🇲🇾', name: 'Malaysia' },
    { dial: '+65',  flag: '🇸🇬', name: 'Singapore' },
    { dial: '+61',  flag: '🇦🇺', name: 'Australia' },
    { dial: '+64',  flag: '🇳🇿', name: 'New Zealand' },
    { dial: '+49',  flag: '🇩🇪', name: 'Germany' },
    { dial: '+33',  flag: '🇫🇷', name: 'France' },
    { dial: '+39',  flag: '🇮🇹', name: 'Italy' },
    { dial: '+34',  flag: '🇪🇸', name: 'Spain' },
    { dial: '+31',  flag: '🇳🇱', name: 'Netherlands' },
    { dial: '+41',  flag: '🇨🇭', name: 'Switzerland' },
    { dial: '+46',  flag: '🇸🇪', name: 'Sweden' },
    { dial: '+47',  flag: '🇳🇴', name: 'Norway' },
    { dial: '+45',  flag: '🇩🇰', name: 'Denmark' },
    { dial: '+32',  flag: '🇧🇪', name: 'Belgium' },
    { dial: '+43',  flag: '🇦🇹', name: 'Austria' },
    { dial: '+90',  flag: '🇹🇷', name: 'Turkey' },
    { dial: '+7',   flag: '🇷🇺', name: 'Russia' },
    { dial: '+86',  flag: '🇨🇳', name: 'China' },
    { dial: '+81',  flag: '🇯🇵', name: 'Japan' },
    { dial: '+82',  flag: '🇰🇷', name: 'South Korea' },
    { dial: '+66',  flag: '🇹🇭', name: 'Thailand' },
    { dial: '+62',  flag: '🇮🇩', name: 'Indonesia' },
    { dial: '+63',  flag: '🇵🇭', name: 'Philippines' },
    { dial: '+92',  flag: '🇵🇰', name: 'Pakistan' },
    { dial: '+880', flag: '🇧🇩', name: 'Bangladesh' },
    { dial: '+94',  flag: '🇱🇰', name: 'Sri Lanka' },
    { dial: '+977', flag: '🇳🇵', name: 'Nepal' },
    { dial: '+27',  flag: '🇿🇦', name: 'South Africa' },
    { dial: '+55',  flag: '🇧🇷', name: 'Brazil' },
    { dial: '+52',  flag: '🇲🇽', name: 'Mexico' },
];

function buildCountrySelect(selectEl) {
    selectEl.innerHTML = COUNTRY_CODES.map(c =>
        `<option value="${c.dial}">${c.flag} ${c.dial}</option>`
    ).join('');
    selectEl.value = '+91';
}

function getPhoneValue(ccSelectEl, numInputEl) {
    const cc = ccSelectEl.value || '+91';
    const num = numInputEl.value.trim();
    return cc + ' ' + num;
}

// ============================================================

function getCsrfToken() {
    // Prefer meta tag (always present), fall back to hidden input inside a form
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : '';
}
function csrfHeaders() {
    return { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() };
}

let currentSeatId = null;
let currentBookingId = null;

// Multi-seat selection state
let multiSeatMode = false;
const selectedSeats = new Set();  // seat IDs pending group booking

// ============================================================
// PANEL SWITCHING
// ============================================================

function showPanel(name) {
    document.querySelectorAll('.panel-view').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById('panel-' + name);
    if (panel) {
        panel.classList.remove('hidden');
        // On mobile the panel is below the seat map — scroll it into view
        if (window.innerWidth < 900 && name !== 'empty' && name !== 'manifest') {
            const sidePanel = document.querySelector('.side-panel') || document.querySelector('.panel');
            const target = sidePanel || panel;
            setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
        }
    }
}

function closePanel() {
    const isDriver = !document.getElementById('panel-booking');
    if (isDriver) {
        showPanel('manifest');
    } else {
        showPanel('empty');
    }
    // Only deselect seats not part of the pending multi-select set
    document.querySelectorAll('.seat.active-single').forEach(s => s.classList.remove('active-single'));
    currentSeatId = null;
    currentBookingId = null;
}

// Manifest item click — highlights seat and shows details
function manifestClick(seatId) {
    currentSeatId = seatId;
    const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
    if (seat) {
        document.querySelectorAll('.seat.active-single').forEach(s => s.classList.remove('active-single'));
        seat.classList.add('active-single');
        seat.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    fetch(`/staff/api/seat/${VOYAGE_ID}/${seatId}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === 'booked') {
                showBookingDetails(data.booking, data.readonly);
            }
        })
        .catch(() => toast('Could not load seat information.'));
}

// ============================================================
// MULTI-SEAT SELECTION
// ============================================================

function toggleMultiSeat() {
    multiSeatMode = !multiSeatMode;
    const toggleBtn = document.getElementById('multiSeatToggle');
    const bookBtn   = document.getElementById('multiSeatBook');
    const clearBtn  = document.getElementById('multiSeatClear');
    const badge     = document.getElementById('multiSeatBadge');

    if (multiSeatMode) {
        toggleBtn.classList.add('btn-primary');
        toggleBtn.classList.remove('btn-ghost');
        toggleBtn.textContent = '✓ Multi-seat ON';
    } else {
        clearMultiSelect();
        toggleBtn.classList.remove('btn-primary');
        toggleBtn.classList.add('btn-ghost');
        toggleBtn.textContent = '+ Multi-seat';
        bookBtn.classList.add('hidden');
        clearBtn.classList.add('hidden');
        badge.classList.add('hidden');
    }
}

function clearMultiSelect() {
    selectedSeats.forEach(sid => {
        const el = document.querySelector(`.seat[data-seat="${sid}"]`);
        if (el) el.classList.remove('multi-selected');
    });
    selectedSeats.clear();
    updateMultiSeatUI();
}

function updateMultiSeatUI() {
    const bookBtn  = document.getElementById('multiSeatBook');
    const clearBtn = document.getElementById('multiSeatClear');
    const badge    = document.getElementById('multiSeatBadge');
    if (!bookBtn) return;

    if (selectedSeats.size > 0) {
        badge.textContent = selectedSeats.size + ' selected';
        badge.classList.remove('hidden');
        bookBtn.textContent = `Book ${selectedSeats.size} Seat${selectedSeats.size > 1 ? 's' : ''}`;
        bookBtn.classList.remove('hidden');
        clearBtn.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
        bookBtn.classList.add('hidden');
        clearBtn.classList.add('hidden');
    }
}

function openGroupBookingForm() {
    if (selectedSeats.size === 0) return;
    const seats = Array.from(selectedSeats).sort();
    const lang = localStorage.getItem('lang') || 'en';

    document.getElementById('groupBookingSeatBadge').textContent = seats.join(', ');

    // Get boarding/dropping options from the seat map form (if they exist)
    const boardingSelect = document.querySelector('#bookingForm select[name="boarding_point"]');
    const droppingSelect = document.querySelector('#bookingForm select[name="dropping_point"]');
    const boardingInput  = document.querySelector('#bookingForm input[name="boarding_point"]');
    const droppingInput  = document.querySelector('#bookingForm input[name="dropping_point"]');

    function makeBoardingField(id) {
        if (boardingSelect) {
            return `<select class="form-select" id="grp_boarding_${id}">` +
                Array.from(boardingSelect.options).map(o => `<option value="${o.value}">${o.text}</option>`).join('') +
                `</select>`;
        }
        return `<input type="text" class="form-input" id="grp_boarding_${id}" placeholder="${lang==='hi'?'जैसे दादर':'e.g. Dadar'}">`;
    }
    function makeDroppingField(id) {
        if (droppingSelect) {
            return `<select class="form-select" id="grp_dropping_${id}">` +
                Array.from(droppingSelect.options).map(o => `<option value="${o.value}">${o.text}</option>`).join('') +
                `</select>`;
        }
        return `<input type="text" class="form-input" id="grp_dropping_${id}" placeholder="${lang==='hi'?'जैसे शिवाजीनगर':'e.g. Shivajinagar'}">`;
    }

    // One shared block: contact + boarding/dropping
    let html = `<div class="group-seat-section">
        <div class="form-group">
            <label class="form-label">${lang==='hi'?'यात्री / समूह नाम':'Passenger / Group Name'}</label>
            <input type="text" class="form-input" id="grp_name" placeholder="${lang==='hi'?'जैसे रमेश परिवार':'e.g. Ramesh Family'}" required>
        </div>
        <div class="form-group">
            <label class="form-label">${lang==='hi'?'संपर्क':'Contact'}</label>
            <div class="phone-input-row">
                <select class="country-code-select" id="grp_cc"></select>
                <input type="text" class="form-input phone-number-input" id="grp_phone" placeholder="98765 43210">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label class="form-label">${lang==='hi'?'बोर्डिंग':'Boarding'}</label>
                ${makeBoardingField('grp')}
            </div>
            <div class="form-group">
                <label class="form-label">${lang==='hi'?'ड्रॉपिंग':'Dropping'}</label>
                ${makeDroppingField('grp')}
            </div>
        </div>
    </div>`;

    // Shared fare fields
    html += `<div class="group-seat-section" style="border-top: 2px solid var(--line); margin-top: 4px;">
        <div class="form-row">
            <div class="form-group">
                <label class="form-label">${lang==='hi'?'किराया (₹) प्रति सीट':'Fare (₹) per seat'}</label>
                <input type="number" class="form-input" id="grpFare" value="${BASE_FARE}" min="0" step="1">
            </div>
            <div class="form-group">
                <label class="form-label">${lang==='hi'?'कुल अग्रिम (₹)':'Total Advance (₹)'}</label>
                <input type="number" class="form-input" id="grpAdvance" value="0" min="0" step="1">
            </div>
        </div>
        <div class="form-actions">
            <button type="button" class="btn btn-ghost" onclick="closePanel()">${lang==='hi'?'रद्द करें':'Cancel'}</button>
            <button type="button" class="btn btn-primary" onclick="submitGroupBookingJSON()">${lang==='hi'?'पुष्टि करें':'Confirm Booking'}</button>
        </div>
    </div>`;

    document.getElementById('groupBookingBody').innerHTML = html;
    buildCountrySelect(document.getElementById('grp_cc'));

    showPanel('group-booking');
}

// ============================================================
// GROUP BOOKING SUBMIT
// ============================================================

function submitGroupBookingJSON() {
    const seats = Array.from(selectedSeats).sort();
    const lang = localStorage.getItem('lang') || 'en';
    const voyageId = VOYAGE_ID;

    if (!voyageId) {
        alert(lang === 'hi' ? 'यात्रा आईडी नहीं मिली' : 'Voyage ID not found');
        return;
    }

    // Shared contact info
    const sharedName = (document.getElementById('grp_name')?.value || '').trim();
    const ccEl = document.getElementById('grp_cc');
    const phoneEl = document.getElementById('grp_phone');
    const sharedPhone = getPhoneValue(ccEl, phoneEl).trim();

    if (!sharedName) {
        alert(lang === 'hi' ? 'यात्री / समूह नाम आवश्यक है' : 'Passenger / group name is required');
        document.getElementById('grp_name')?.focus();
        return;
    }
    if (!sharedPhone || sharedPhone === (ccEl?.value || '+91')) {
        alert(lang === 'hi' ? 'संपर्क नंबर आवश्यक है' : 'Contact number is required');
        phoneEl?.focus();
        return;
    }

    // Shared boarding/dropping
    const boardingEl = document.getElementById('grp_boarding_grp');
    const droppingEl = document.getElementById('grp_dropping_grp');
    const sharedBoarding = (boardingEl?.value || '').trim();
    const sharedDropping = (droppingEl?.value || '').trim();

    if (!sharedBoarding) {
        alert(lang === 'hi' ? 'बोर्डिंग पॉइंट आवश्यक है' : 'Boarding point is required');
        boardingEl?.focus();
        return;
    }
    if (!sharedDropping) {
        alert(lang === 'hi' ? 'ड्रॉपिंग पॉइंट आवश्यक है' : 'Dropping point is required');
        droppingEl?.focus();
        return;
    }

    const passengers = seats.map(sid => ({
        seat_id: sid, name: sharedName, phone: sharedPhone, gender: null,
        boarding_point: sharedBoarding, dropping_point: sharedDropping,
    }));

    const farePerSeat = parseFloat(document.getElementById('grpFare')?.value) || 0;
    const advancePaid = parseFloat(document.getElementById('grpAdvance')?.value) || 0;

    const payload = {
        voyage_id: voyageId,
        passengers,
        boarding_point: passengers[0]?.boarding_point || '',
        dropping_point: passengers[0]?.dropping_point || '',
        fare_per_seat: farePerSeat,
        advance_paid: advancePaid,
    };

    const submitBtn = document.querySelector('#panel-group-booking .btn-primary');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = lang === 'hi' ? 'हो रहा है…' : 'Booking…'; }

    function postGroup(p) {
        return fetch('/staff/booking/create-group', {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify(p),
        }).then(r => r.json());
    }

    postGroup(payload)
    .then(data => {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = lang === 'hi' ? 'पुष्टि करें' : 'Confirm Booking'; }
        if (data.status === 'ok' || data.status === 'success' || data.status === 'warning') {
            renderGroupSuccess(data, farePerSeat, advancePaid, lang);
        } else if (data.status === 'gender_conflict') {
            if (confirm((data.message || 'Adjacent seat gender conflict.') + '\n\nBook anyway?')) {
                payload.confirm_gender_conflict = 'yes';
                postGroup(payload).then(d => {
                    if (d.status === 'ok' || d.status === 'success') renderGroupSuccess(d, farePerSeat, advancePaid, lang);
                    else alert(d.message || d.error || (lang === 'hi' ? 'बुकिंग विफल हुई' : 'Booking failed'));
                });
            }
        } else {
            alert(data.message || data.error || (lang === 'hi' ? 'बुकिंग विफल हुई' : 'Booking failed'));
        }
    })
    .catch(err => {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = lang === 'hi' ? 'पुष्टि करें' : 'Confirm Booking'; }
        console.error('Group booking error:', err);
        alert(lang === 'hi' ? 'नेटवर्क त्रुटि' : 'Network error, please try again');
    });
}

function renderGroupSuccess(data, farePerSeat, advancePaid, lang) {
    const bookings = data.bookings || [];
    const groupCode = data.group_code || '';

    let html = `<div style="text-align:center;padding:16px 0 8px;">
        <div style="font-size:42px;margin-bottom:8px;">✅</div>
        <div style="font-size:18px;font-weight:600;margin-bottom:4px;">${lang==='hi'?'बुकिंग पुष्टि हो गई':'Booking Confirmed'}</div>
        <div style="font-size:13px;color:var(--muted);margin-bottom:16px;">${lang==='hi'?'समूह कोड:':'Group Code:'} <b>${groupCode}</b></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">`;

    bookings.forEach(b => {
        const label = `${lang==='hi'?'सीट':'Seat'} ${b.seat_id} — ${b.name}`;
        html += `<a href="/staff/booking/${b.id}/ticket" target="_blank"
            style="display:flex;align-items:center;gap:8px;padding:10px 14px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--ink);font-size:13px;">
            <span style="font-size:18px;">🎫</span>
            <span style="flex:1;">${label}</span>
            <span style="color:var(--marigold);font-weight:600;">${lang==='hi'?'डाउनलोड':'Download'} ↓</span>
        </a>`;
    });

    if (bookings.length > 1 && groupCode) {
        html += `<a href="/staff/booking/group/${groupCode}/tickets" target="_blank"
            style="display:flex;align-items:center;gap:8px;padding:10px 14px;background:var(--ink);color:var(--cream);border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;margin-top:4px;">
            <span style="font-size:18px;">📥</span>
            <span style="flex:1;">${lang==='hi'?'सभी टिकट डाउनलोड करें':'Download All Tickets'}</span>
        </a>`;
    }

    html += `</div>
    <button class="btn btn-ghost" style="width:100%;" onclick="closePanel();resetMultiSeat();">
        ${lang==='hi'?'बंद करें':'Close'}
    </button>`;

    document.getElementById('groupSuccessBody').innerHTML = html;
    showPanel('group-success');

    // Reset multi-seat selection
    selectedSeats.forEach(sid => {
        const seatEl = document.querySelector(`.seat[data-seat="${sid}"]`);
        if (seatEl) seatEl.classList.remove('multi-selected');
    });
    selectedSeats.clear();
    updateMultiSeatUI();
}

// ============================================================
// SEAT CLICK HANDLER
// ============================================================

document.querySelectorAll('.seat').forEach(seat => {
    seat.addEventListener('click', async () => {
        const seatId = seat.dataset.seat;

        // In multi-seat mode: only toggle available seats
        if (multiSeatMode) {
            const isBooked = seat.classList.contains('booked-m') || seat.classList.contains('booked-f');
            if (isBooked) return;  // can't multi-select booked seats

            if (selectedSeats.has(seatId)) {
                selectedSeats.delete(seatId);
                seat.classList.remove('multi-selected');
            } else {
                selectedSeats.add(seatId);
                seat.classList.add('multi-selected');
            }
            updateMultiSeatUI();
            return;
        }

        // Single-seat mode — normal flow
        currentSeatId = seatId;
        document.querySelectorAll('.seat.active-single').forEach(s => s.classList.remove('active-single'));
        seat.classList.add('active-single');

        try {
            const res = await fetch(`/staff/api/seat/${VOYAGE_ID}/${seatId}`);
            const data = await res.json();

            if (data.readonly) {
                if (data.status === 'booked') {
                    showBookingDetails(data.booking, true);
                } else {
                    closePanel();
                }
            } else {
                if (data.status === 'booked') {
                    showBookingDetails(data.booking, false);
                } else {
                    showSingleBookingForm(data);
                }
            }
        } catch (err) {
            console.error('Failed to load seat info:', err);
            alert('Could not load seat information. Please try again.');
        }
    });
});

// ============================================================
// GROUP SEAT HOVER HIGHLIGHT
// ============================================================

const seatMapEl = document.getElementById('seatMap');
if (seatMapEl) {
    seatMapEl.addEventListener('mouseover', (e) => {
        const seat = e.target.closest('.seat.group-seat');
        if (!seat) return;
        const grp = seat.dataset.group;
        if (!grp) return;
        document.querySelectorAll(`.seat[data-group="${grp}"]`).forEach(s => s.classList.add('group-highlight'));
    });
    seatMapEl.addEventListener('mouseout', (e) => {
        const seat = e.target.closest('.seat.group-seat');
        if (!seat) return;
        document.querySelectorAll('.seat.group-highlight').forEach(s => s.classList.remove('group-highlight'));
    });
}

// ============================================================
// BOOKING FORM (only exists for reservation/admin)
// ============================================================

function showSingleBookingForm(data) {
    // Clear any leftover group inputs
    const container = document.getElementById('groupSeatInputs');
    if (container) container.innerHTML = '';
    window._isGroupBooking = false;

    document.getElementById('bookingSeatLabel').textContent = data.seat_id;
    document.getElementById('formSeatId').value = data.seat_id;
    document.getElementById('confirmConflict').value = 'no';

    document.getElementById('bookingForm').reset();
    document.querySelector('input[name="seat_id"]').value = data.seat_id;
    document.querySelector('input[name="voyage_id"]').value = VOYAGE_ID;
    document.querySelector('input[name="fare"]').value = BASE_FARE;
    document.querySelector('input[name="advance_paid"]').value = 0;

    document.getElementById('genderWarning').classList.add('hidden');
    window._adjacentGenders = data.adjacent_genders || [];

    showPanel('booking');
}

// Gender conflict check
const genderRadios = document.querySelectorAll('input[name="gender"]');
genderRadios.forEach(radio => {
    radio.addEventListener('change', () => {
        if (window._isGroupBooking) return;  // skip conflict check for group bookings
        const selectedGender = radio.value;
        const conflicts = (window._adjacentGenders || [])
            .filter(a => a.gender !== selectedGender);

        const warning = document.getElementById('genderWarning');
        const text = document.getElementById('genderWarningText');

        if (conflicts.length > 0) {
            const names = conflicts.map(c => `seat ${c.seat} (${c.name})`).join(', ');
            text.textContent = `${names} booked by opposite gender. Confirm to proceed.`;
            warning.classList.remove('hidden');
            document.getElementById('confirmConflict').value = 'yes';
        } else {
            warning.classList.add('hidden');
            document.getElementById('confirmConflict').value = 'no';
        }
    });
});

// Submit booking — handles both single and group modes
const bookingForm = document.getElementById('bookingForm');
if (bookingForm) {
    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const singleCc = document.getElementById('singleCc');
        const singlePhone = document.getElementById('singlePhone');
        const singlePhoneCombined = document.getElementById('singlePhoneCombined');
        if (singleCc && singlePhone && singlePhoneCombined) {
            singlePhoneCombined.value = getPhoneValue(singleCc, singlePhone);
        }
        const formData = new FormData(e.target);
        const submitBtn = bookingForm.querySelector('[type="submit"]');
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Please wait…'; }
        try {
            if (window._isGroupBooking) {
                await submitGroupBooking(formData);
            } else {
                await submitSingleBooking(formData);
            }
        } finally {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Confirm Booking'; }
        }
    });
}

async function submitSingleBooking(formData) {
    function applySingleSuccess(data) {
        const seat = document.querySelector(`.seat[data-seat="${data.booking.seat_id}"]`);
        if (seat) {
            seat.classList.remove('active-single');
            seat.classList.add('booked-' + data.booking.gender.toLowerCase());
            seat.title = data.booking.name;
        }
        const oc = document.getElementById('occupancyCount');
        if (oc) oc.textContent = parseInt(oc.textContent) + 1;
        closePanel();
        toast(`Seat ${data.booking.seat_id} booked for ${data.booking.name}`);
    }

    try {
        const res = await fetch('/staff/booking/create', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.status === 'success') {
            applySingleSuccess(data);
        } else if (data.status === 'gender_conflict') {
            if (confirm(data.message + '\n\nBook anyway?')) {
                formData.set('confirm_gender_conflict', 'yes');
                const res2 = await fetch('/staff/booking/create', { method: 'POST', body: formData });
                const data2 = await res2.json();
                if (data2.status === 'success') applySingleSuccess(data2);
                else alert('Error: ' + (data2.message || JSON.stringify(data2.errors)));
            }
        } else if (data.status === 'error') {
            alert('Error: ' + (data.message || JSON.stringify(data.errors)));
        }
    } catch (err) {
        console.error('Booking failed:', err);
        alert('Booking failed. Please try again.');
    }
}

async function submitGroupBooking(formData) {
    // seat_ids[] already injected into formData via hidden inputs
    try {
        const res = await fetch('/staff/booking/create-group', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (data.status === 'success') {
            const gender = data.gender.toLowerCase();
            data.seat_ids.forEach(sid => {
                const seat = document.querySelector(`.seat[data-seat="${sid}"]`);
                if (seat) {
                    seat.classList.remove('multi-selected', 'active-single');
                    seat.classList.add('booked-' + gender);
                    if (data.group_code) {
                        seat.classList.add('group-seat');
                        seat.dataset.group = data.group_code;
                    }
                    seat.title = data.name;
                }
            });

            const oc = document.getElementById('occupancyCount');
            if (oc) oc.textContent = parseInt(oc.textContent) + data.seat_ids.length;

            selectedSeats.clear();
            updateMultiSeatUI();

            closePanel();
            if (data.group_code) {
                // True multi-seat group booking
                toast(`${data.seat_ids.length} seats booked for ${data.name}`);
                if (confirm(`Group booking confirmed!\nSeats: ${data.seat_ids.join(', ')}\nBooking ID: ${data.group_code}\n\nDownload group e-ticket?`)) {
                    window.open(`/staff/booking/group/${data.group_code}/ticket`, '_blank');
                }
            } else {
                // Single seat submitted via multi-select UI
                const b = data.bookings[0];
                toast(`Seat ${b.seat_id} booked for ${data.name}`);
                if (confirm(`Booking confirmed!\nSeat: ${b.seat_id}\nBooking ID: ${b.code}\n\nDownload e-ticket?`)) {
                    window.open(`/staff/booking/${b.id}/ticket`, '_blank');
                }
            }

        } else if (data.status === 'error') {
            alert('Error: ' + (data.message || 'Unknown error'));
        }
    } catch (err) {
        console.error('Group booking failed:', err);
        alert('Group booking failed. Please try again.');
    }
}

// ============================================================
// PASSENGER DETAILS
// ============================================================

function showBookingDetails(booking, readonly) {
    currentBookingId = booking.id;

    const seatLabel = booking.group_seats && booking.group_seats.length > 1
        ? booking.group_seats.sort().join(', ')
        : (booking.seat || currentSeatId);

    document.getElementById('detailsSeatLabel').textContent = seatLabel;
    document.getElementById('detailsName').textContent = booking.name;
    document.getElementById('detailsPhone').textContent = booking.phone;
    document.getElementById('detailsBoarding').textContent = booking.boarding;
    document.getElementById('detailsDropping').textContent = booking.dropping;
    document.getElementById('detailsFare').textContent = '₹ ' + booking.fare;
    document.getElementById('detailsAdvance').textContent = '₹ ' + booking.advance;
    document.getElementById('detailsBalance').textContent = '₹ ' + booking.balance;
    document.getElementById('detailsCode').textContent = booking.code;

    // Check-in section (visible for all roles when booking is shown)
    const checkinSection = document.getElementById('checkinSection');
    const checkinStatus = document.getElementById('checkinStatus');
    const checkinBtn = document.getElementById('checkinBtn');
    if (checkinSection) {
        window._currentCheckinBookingId = booking.id;
        window._currentCheckinSeatId = booking.seat || currentSeatId;
        window._currentCheckinName = booking.name;
        if (booking.boarded_at) {
            checkinStatus.innerHTML = `<div class="checkin-status-badge">✓ <span data-i18n="dash.checkedin">Checked In</span> ${booking.boarded_at}${booking.boarded_by ? ' · ' + booking.boarded_by : ''}</div>`;
            if (checkinBtn) checkinBtn.classList.add('hidden');
            // Undo link (shown always — admins can undo anytime, drivers within 5 min)
            const undoEl = checkinStatus.querySelector('.btn-undo-checkin') || (() => {
                const b = document.createElement('button');
                b.className = 'btn-undo-checkin';
                b.setAttribute('data-i18n', 'dash.undo_checkin');
                b.textContent = 'Undo check-in';
                b.onclick = undoCheckinFromPanel;
                checkinStatus.appendChild(b);
                return b;
            })();
        } else {
            checkinStatus.innerHTML = '';
            if (checkinBtn) checkinBtn.classList.remove('hidden');
        }
    }

    // Show group seats info if this is a group booking
    const groupSeatsDiv = document.getElementById('detailsGroupSeats');
    const groupSeatsList = document.getElementById('detailsGroupSeatsList');
    if (booking.group_code && booking.group_seats && booking.group_seats.length > 1) {
        groupSeatsList.textContent = booking.group_seats.sort().join(', ');
        groupSeatsDiv.classList.remove('hidden');
    } else {
        groupSeatsDiv.classList.add('hidden');
    }

    // Individual ticket button
    const ticketBtn = document.getElementById('ticketDownloadBtn');
    if (ticketBtn) {
        ticketBtn.dataset.bookingId = booking.id;
        ticketBtn.dataset.bookingName = booking.name;
        ticketBtn.dataset.bookingCode = booking.code;
        ticketBtn.dataset.bookingSeat = booking.seat || currentSeatId;
    }

    // Group ticket button
    const groupTicketBtn = document.getElementById('groupTicketDownloadBtn');
    if (groupTicketBtn) {
        if (booking.group_code && booking.group_seats && booking.group_seats.length > 1) {
            groupTicketBtn.dataset.groupCode = booking.group_code;
            groupTicketBtn.classList.remove('hidden');
        } else {
            groupTicketBtn.classList.add('hidden');
        }
    }

    // WhatsApp button
    const waBtn = document.getElementById('whatsappBtn');
    if (waBtn) {
        waBtn.dataset.phone = booking.phone || '';
        waBtn.dataset.name = booking.name;
        waBtn.dataset.seat = seatLabel;
        waBtn.dataset.code = booking.group_code || booking.code;
        waBtn.dataset.boarding = booking.boarding;
        waBtn.dataset.dropping = booking.dropping;
        waBtn.dataset.fare = booking.fare;
        waBtn.dataset.balance = booking.balance;
        waBtn.dataset.bookingId = booking.id;
        waBtn.dataset.departureDate = booking.departure_date || '';
        waBtn.dataset.departureTime = booking.departure_time || '';
    }

    // Hide action buttons for drivers
    const cancelBtn = document.getElementById('cancelBookingBtn');
    if (cancelBtn) cancelBtn.style.display = readonly ? 'none' : 'inline-block';
    if (ticketBtn) ticketBtn.style.display = readonly ? 'none' : 'inline-block';
    if (groupTicketBtn) groupTicketBtn.style.display = readonly ? 'none' : '';
    if (waBtn) waBtn.style.display = readonly ? 'none' : 'inline-block';

    // Driver view: hide Fare / Advance / Balance / Booking ID rows — not relevant on-board
    const detailRows = document.querySelectorAll('#panel-details .passenger-details .detail-row');
    detailRows.forEach((row, i) => {
        // rows: 0=Boarding, 1=Dropping, 2=Fare, 3=Advance, 4=Balance, 5=Booking ID
        row.style.display = (readonly && i >= 2) ? 'none' : '';
    });

    showPanel('details');
}

// ============================================================
// TICKET DOWNLOAD
// ============================================================

const ticketBtn = document.getElementById('ticketDownloadBtn');
if (ticketBtn) {
    ticketBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const id   = this.dataset.bookingId;
        const name = this.dataset.bookingName;
        const code = this.dataset.bookingCode;
        const seat = this.dataset.bookingSeat;
        if (!id) return;
        if (confirm(`Download e-ticket for ${name}?\n\nSeat ${seat} · ${code}`)) {
            window.open(`/staff/booking/${id}/ticket`, '_blank');
        }
    });
}

const groupTicketBtn = document.getElementById('groupTicketDownloadBtn');
if (groupTicketBtn) {
    groupTicketBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const code = this.dataset.groupCode;
        if (!code) return;
        window.open(`/staff/booking/group/${code}/ticket`, '_blank');
    });
}

// ============================================================
// WHATSAPP TICKET SHARE
// ============================================================

const waBtn = document.getElementById('whatsappBtn');
if (waBtn) {
    waBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();

        const name     = this.dataset.name;
        const seat     = this.dataset.seat;
        const code     = this.dataset.code;
        const boarding = this.dataset.boarding;
        const dropping = this.dataset.dropping;
        const fare     = this.dataset.fare;
        const balance  = this.dataset.balance;
        const phone    = this.dataset.phone;
        const depDate  = this.dataset.departureDate || '';
        const depTime  = this.dataset.departureTime || '';

        if (!name) return;

        const message =
            `🚌 *SHRISAMARTH TRAVELS*\n` +
            `━━━━━━━━━━━━━━━━\n\n` +
            `Dear *${name}*,\n\n` +
            `Your booking is confirmed! ✅\n\n` +
            `🎫 *Booking ID:* ${code}\n` +
            `💺 *Seat(s):* ${seat}\n` +
            (depDate ? `📅 *Date:* ${depDate}\n` : ``) +
            (depTime ? `⏰ *Departure:* ${depTime}\n` : ``) +
            `📍 *Boarding:* ${boarding}\n` +
            `📍 *Dropping:* ${dropping}\n` +
            `💰 *Fare:* ₹${fare}\n` +
            `${parseFloat(balance) > 0 ? '⚠️ *Balance Due:* ₹' + balance + '\n' : '✅ *Payment:* Complete\n'}` +
            `\n━━━━━━━━━━━━━━━━\n` +
            `Show this message at boarding.\n` +
            `Thank you for travelling with us! 🙏`;

        let cleanPhone = phone.replace(/[\s\-\(\)]/g, '');
        if (cleanPhone.startsWith('+')) cleanPhone = cleanPhone.substring(1);
        if (!cleanPhone.startsWith('91') && cleanPhone.length === 10) cleanPhone = '91' + cleanPhone;

        window.open(`https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`, '_blank');
    });
}

// ============================================================
// CANCEL BOOKING
// ============================================================

const cancelBtn = document.getElementById('cancelBookingBtn');
if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
        if (!currentBookingId) return;
        if (!confirm('Cancel this booking? This cannot be undone.')) return;

        try {
            const headers = csrfHeaders();

            const res = await fetch(`/staff/booking/${currentBookingId}/cancel`, {
                method: 'POST',
                headers: headers,
            });
            const data = await res.json();

            if (data.status === 'success') {
                const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
                seat.classList.remove('booked-m', 'booked-f', 'booked-g', 'active-single', 'multi-selected', 'group-seat', 'group-highlight');
                delete seat.dataset.group;
                seat.title = `Seat ${data.seat_id}`;

                const oc = document.getElementById('occupancyCount');
                if (oc) oc.textContent = parseInt(oc.textContent) - 1;

                closePanel();
                toast('Booking cancelled');
            }
        } catch (err) {
            console.error('Cancel failed:', err);
            alert('Could not cancel booking.');
        }
    });
}

// ============================================================
// MANUAL CHECK-IN
// ============================================================

async function checkInFromPanel() {
    const bookingId = window._currentCheckinBookingId;
    const name = window._currentCheckinName;
    const seatId = window._currentCheckinSeatId;
    if (!bookingId) return;
    const lang = document.documentElement.lang || 'en';
    const isDriverView = !document.getElementById('panel-booking');
    if (!isDriverView) {
        const msg = lang === 'hi'
            ? `${name} को सीट ${seatId} के लिए चेक-इन करें?`
            : `Check in ${name} for seat ${seatId}?`;
        if (!confirm(msg)) return;
    }

    const headers = csrfHeaders();
    try {
        const res = await fetch(`/staff/booking/${bookingId}/checkin`, { method: 'POST', headers });
        const data = await res.json();
        if (data.status === 'ok' || data.status === 'already_checked_in') {
            const lang = document.documentElement.lang || 'en';
            toast(lang === 'hi' ? `${name} चेक-इन हो गए ✓` : `${name} checked in ✓`);
            // Update seat map
            const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
            if (seat) {
                const gender = seat.classList.contains('booked-m') || seat.classList.contains('checked-in-m') ? 'm' : seat.classList.contains('booked-f') || seat.classList.contains('checked-in-f') ? 'f' : 'g';
                seat.classList.remove('booked-m', 'booked-f', 'booked-g');
                seat.classList.add(`checked-in-${gender}`);
            }
            // Update manifest row
            updateManifestRowCheckedIn(seatId, data.boarded_at);
            updateCheckinProgress(1);
            // Re-fetch and redisplay panel
            const res2 = await fetch(`/staff/api/seat/${VOYAGE_ID}/${seatId}`);
            const d2 = await res2.json();
            if (d2.status === 'booked') showBookingDetails(d2.booking, d2.readonly);
        }
    } catch (err) { console.error('Check-in failed', err); }
}

async function undoCheckinFromPanel() {
    const bookingId = window._currentCheckinBookingId;
    const name = window._currentCheckinName;
    const seatId = window._currentCheckinSeatId;
    if (!bookingId) return;
    const lang = document.documentElement.lang || 'en';
    const msg = lang === 'hi' ? `${name} का चेक-इन रद्द करें?` : `Undo check-in for ${name}?`;
    if (!confirm(msg)) return;

    const headers = csrfHeaders();
    try {
        const res = await fetch(`/staff/booking/${bookingId}/uncheckin`, { method: 'POST', headers });
        const data = await res.json();
        if (data.status === 'ok') {
            const lang = document.documentElement.lang || 'en';
            toast(lang === 'hi' ? `${name} का चेक-इन रद्द हुआ` : `Check-in undone for ${name}`);
            const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
            if (seat) {
                const gender = seat.classList.contains('checked-in-m') ? 'm' : 'f';
                seat.classList.remove('checked-in-m', 'checked-in-f');
                seat.classList.add(`booked-${gender}`);
            }
            updateManifestRowUnchecked(seatId);
            updateCheckinProgress(-1);
            const res2 = await fetch(`/staff/api/seat/${VOYAGE_ID}/${seatId}`);
            const d2 = await res2.json();
            if (d2.status === 'booked') showBookingDetails(d2.booking, d2.readonly);
        } else if (data.status === 'error') {
            const lang = document.documentElement.lang || 'en';
            alert(lang === 'hi' ? 'समय सीमा समाप्त (5 मिनट)' : data.message || 'Undo window expired');
        }
    } catch (err) { console.error('Undo check-in failed', err); }
}

async function manifestCheckin(e, btn) {
    e.stopPropagation();
    const bookingId = btn.dataset.bookingId;
    const seatId = btn.dataset.seat;
    const name = btn.dataset.name;
    const boarded = btn.dataset.boarded;
    const lang = document.documentElement.lang || 'en';

    if (boarded) {
        // Already checked in — offer undo
        const msg = lang === 'hi' ? `${name} का चेक-इन रद्द करें?` : `Undo check-in for ${name}?`;
        if (!confirm(msg)) return;
        const headers = csrfHeaders();
        const res = await fetch(`/staff/booking/${bookingId}/uncheckin`, { method: 'POST', headers });
        const data = await res.json();
        if (data.status === 'ok') {
            btn.textContent = '○';
            btn.classList.remove('checked');
            btn.dataset.boarded = '';
            const timeEl = btn.parentNode.querySelector('.manifest-checkin-time');
            if (timeEl) timeEl.remove();
            updateManifestRowUnchecked(seatId);
            updateCheckinProgress(-1);
            toast(lang === 'hi' ? `${name} का चेक-इन रद्द हुआ` : `Undo: ${name}`);
        } else if (data.status === 'error') {
            alert(lang === 'hi' ? 'समय सीमा समाप्त' : data.message || 'Undo window expired');
        }
        return;
    }

    // Not yet checked in
    const msg = lang === 'hi'
        ? `${name} को सीट ${seatId} के लिए चेक-इन करें?`
        : `Check in ${name} for seat ${seatId}?`;
    if (!confirm(msg)) return;
    const headers = csrfHeaders();
    const res = await fetch(`/staff/booking/${bookingId}/checkin`, { method: 'POST', headers });
    const data = await res.json();
    if (data.status === 'ok' || data.status === 'already_checked_in') {
        const t = data.boarded_at;
        btn.textContent = '✓';
        btn.classList.add('checked');
        btn.dataset.boarded = t;
        let timeEl = btn.parentNode.querySelector('.manifest-checkin-time');
        if (!timeEl) { timeEl = document.createElement('div'); timeEl.className = 'manifest-checkin-time'; btn.parentNode.appendChild(timeEl); }
        timeEl.textContent = t;
        updateManifestRowCheckedIn(seatId, t);
        // Update seat map
        const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
        if (seat) {
            const gender = seat.classList.contains('booked-m') || seat.classList.contains('checked-in-m') ? 'm' : seat.classList.contains('booked-f') || seat.classList.contains('checked-in-f') ? 'f' : 'g';
            seat.classList.remove('booked-m', 'booked-f');
            seat.classList.add(`checked-in-${gender}`);
        }
        updateCheckinProgress(1);
        toast(lang === 'hi' ? `${name} चेक-इन हो गए ✓` : `${name} checked in ✓`);
    }
}

// ============================================================
// SWIPE-TO-REVEAL CHECK-IN
// ============================================================
const SWIPE_ACTION_W = 90;
let _swipeOpenItem = null;

function _closeSwipeItem(item) {
    if (!item) return;
    item.classList.remove('swipe-open');
    const inner = item.querySelector('.manifest-item-inner');
    const action = item.querySelector('.manifest-swipe-action');
    if (inner) { inner.style.transition = ''; inner.style.transform = ''; }
    if (action) { action.style.transition = ''; action.style.transform = ''; }
}

function initManifestSwipe() {
    document.querySelectorAll('.manifest-item').forEach(item => {
        if (item._swipeInit) return;
        item._swipeInit = true;

        const inner = item.querySelector('.manifest-item-inner');
        const action = item.querySelector('.manifest-swipe-action');
        if (!inner || !action) return;

        let startX, startY, dragging, horizontal;

        item.addEventListener('touchstart', e => {
            if (e.touches.length !== 1) return;
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            dragging = false;
            horizontal = false;
        }, { passive: true });

        item.addEventListener('touchmove', e => {
            if (e.touches.length !== 1) return;
            const dx = e.touches[0].clientX - startX;
            const dy = e.touches[0].clientY - startY;
            if (!dragging) {
                if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
                if (Math.abs(dy) > Math.abs(dx)) { dragging = true; horizontal = false; return; }
                dragging = true;
                horizontal = true;
            }
            if (!horizontal) return;
            e.preventDefault();

            const isOpen = item.classList.contains('swipe-open');
            let offset;
            if (isOpen) {
                // Already revealed: swipe right (dx > 0) closes it
                offset = Math.min(0, Math.max(-SWIPE_ACTION_W, -SWIPE_ACTION_W + dx));
            } else {
                // Swipe left (dx < 0) slides content left to reveal action
                offset = Math.max(-SWIPE_ACTION_W, Math.min(0, dx));
            }

            inner.style.transition = 'none';
            action.style.transition = 'none';
            inner.style.transform = `translateX(${offset}px)`;
            action.style.transform = `translateX(${SWIPE_ACTION_W + offset}px)`;
        }, { passive: false });

        item.addEventListener('touchend', e => {
            if (!dragging || !horizontal) return;
            const dx = e.changedTouches[0].clientX - startX;
            const isOpen = item.classList.contains('swipe-open');

            inner.style.transition = '';
            action.style.transition = '';
            inner.style.transform = '';
            action.style.transform = '';

            if (!isOpen && dx < -55) {
                if (_swipeOpenItem && _swipeOpenItem !== item) _closeSwipeItem(_swipeOpenItem);
                item.classList.add('swipe-open');
                _swipeOpenItem = item;
            } else if (isOpen && dx > 40) {
                item.classList.remove('swipe-open');
                if (_swipeOpenItem === item) _swipeOpenItem = null;
            }
        }, { passive: true });
    });

    document.addEventListener('touchstart', e => {
        if (_swipeOpenItem && !_swipeOpenItem.contains(e.target)) {
            _closeSwipeItem(_swipeOpenItem);
            _swipeOpenItem = null;
        }
    }, { passive: true, capture: false });
}

async function swipeCheckin(btn) {
    const bookingId = btn.dataset.bookingId;
    const seatId = btn.dataset.seat;
    const name = btn.dataset.name;
    const boarded = btn.dataset.boarded;
    const lang = document.documentElement.lang || 'en';
    const headers = csrfHeaders();
    const item = btn.closest('.manifest-item');
    const action = btn.closest('.manifest-swipe-action');

    // Close swipe immediately for responsive feel
    if (item) {
        item.classList.remove('swipe-open');
        if (_swipeOpenItem === item) _swipeOpenItem = null;
    }

    if (boarded) {
        const res = await fetch(`/staff/booking/${bookingId}/uncheckin`, { method: 'POST', headers });
        const data = await res.json();
        if (data.status === 'ok') {
            btn.dataset.boarded = '';
            if (action) { action.classList.remove('action-undo'); action.classList.add('action-checkin'); }
            const icon = btn.querySelector('.manifest-swipe-icon');
            const label = btn.querySelector('[data-i18n]');
            if (icon) icon.textContent = '✓';
            if (label) { label.textContent = lang === 'hi' ? 'चेक-इन' : 'Check In'; label.dataset.i18n = 'dash.checkin_btn'; }
            const circleBtn = item && item.querySelector('.checkin-btn');
            if (circleBtn) {
                circleBtn.textContent = '○';
                circleBtn.classList.remove('checked');
                circleBtn.dataset.boarded = '';
                const timeEl = circleBtn.parentNode.querySelector('.manifest-checkin-time');
                if (timeEl) timeEl.remove();
            }
            updateManifestRowUnchecked(seatId);
            updateCheckinProgress(-1);
            toast(lang === 'hi' ? `${name} का चेक-इन रद्द हुआ` : `Undo: ${name}`);
        } else {
            toast(data.message || 'Error');
        }
    } else {
        const res = await fetch(`/staff/booking/${bookingId}/checkin`, { method: 'POST', headers });
        const data = await res.json();
        if (data.status === 'ok' || data.status === 'already_checked_in') {
            const t = data.boarded_at;
            btn.dataset.boarded = t;
            if (action) { action.classList.remove('action-checkin'); action.classList.add('action-undo'); }
            const icon = btn.querySelector('.manifest-swipe-icon');
            const label = btn.querySelector('[data-i18n]');
            if (icon) icon.textContent = '↩';
            if (label) { label.textContent = lang === 'hi' ? 'रद्द करें' : 'Undo'; label.dataset.i18n = 'dash.undo_checkin'; }
            const circleBtn = item && item.querySelector('.checkin-btn');
            if (circleBtn) {
                circleBtn.textContent = '✓';
                circleBtn.classList.add('checked');
                circleBtn.dataset.boarded = t;
                let timeEl = circleBtn.parentNode.querySelector('.manifest-checkin-time');
                if (!timeEl) { timeEl = document.createElement('div'); timeEl.className = 'manifest-checkin-time'; circleBtn.parentNode.appendChild(timeEl); }
                timeEl.textContent = t;
            }
            updateManifestRowCheckedIn(seatId, t);
            const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
            if (seat) {
                const gender = seat.classList.contains('booked-m') || seat.classList.contains('checked-in-m') ? 'm' : seat.classList.contains('booked-f') || seat.classList.contains('checked-in-f') ? 'f' : 'g';
                seat.classList.remove('booked-m', 'booked-f', 'booked-g');
                seat.classList.add(`checked-in-${gender}`);
            }
            updateCheckinProgress(1);
            toast(lang === 'hi' ? `${name} चेक-इन हो गए ✓` : `${name} checked in ✓`);
        } else {
            toast(data.message || 'Error');
        }
    }
}

function updateManifestRowCheckedIn(seatId, time) {
    const row = document.querySelector(`.manifest-item[data-seat="${seatId}"]`);
    if (!row) return;
    row.classList.add('checked-in');
    row.classList.remove('boarded');
    let badge = row.querySelector('.boarding-badge');
    if (!badge) { badge = document.createElement('div'); badge.className = 'boarding-badge'; row.querySelector('.manifest-name').parentNode.appendChild(badge); }
    badge.textContent = '✓ ' + time;
}

function updateManifestRowUnchecked(seatId) {
    const row = document.querySelector(`.manifest-item[data-seat="${seatId}"]`);
    if (!row) return;
    row.classList.remove('checked-in', 'boarded');
    const badge = row.querySelector('.boarding-badge');
    if (badge) badge.remove();
}

function updateCheckinProgress(delta) {
    const numEl = document.getElementById('checkinNum');
    if (!numEl) return;
    const current = parseInt(numEl.textContent) || 0;
    const next = Math.max(0, current + delta);
    numEl.textContent = next;
    const fill = document.getElementById('checkinProgressFill');
    if (fill) {
        const total = parseInt(fill.parentNode.previousElementSibling?.querySelector('span:last-child')?.textContent) || 1;
        fill.style.width = Math.round(next / total * 100) + '%';
    }
}

// ============================================================
// QR SCANNER (driver)
// ============================================================

let scanStream = null;
let scanInterval = null;

function openScanner() {
    const modal = document.getElementById('scannerModal');
    if (!modal) return;
    const manualDiv = document.getElementById('manualInput');
    if (manualDiv) manualDiv.style.display = 'flex';
    const codeInput = document.getElementById('manualCode');
    if (codeInput) codeInput.value = '';
    modal.classList.remove('hidden');
    startCamera();
}

function closeScanner() {
    stopCamera();
    document.getElementById('scannerModal').classList.add('hidden');
    document.getElementById('scanStatus').textContent = 'Point camera at passenger\'s QR code';
}

async function startCamera() {
    const video = document.getElementById('scanVideo');
    const status = document.getElementById('scanStatus');
    const manualDiv = document.getElementById('manualInput');
    if (!video) return;
    try {
        scanStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }
        });
        video.srcObject = scanStream;
        await video.play();
        scanInterval = setInterval(scanFrame, 150);
    } catch (err) {
        status.textContent = 'Camera not available — enter code manually.';
        if (manualDiv) manualDiv.style.display = 'flex';
    }
}

function stopCamera() {
    clearInterval(scanInterval);
    scanInterval = null;
    if (scanStream) {
        scanStream.getTracks().forEach(t => t.stop());
        scanStream = null;
    }
}

function scanFrame() {
    const video = document.getElementById('scanVideo');
    const canvas = document.getElementById('scanCanvas');
    if (!video || !canvas) return;
    if (video.readyState < video.HAVE_ENOUGH_DATA) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    if (typeof jsQR === 'undefined') return;
    const code = jsQR(imageData.data, imageData.width, imageData.height, {
        inversionAttempts: 'dontInvert',
    });
    if (code && code.data) {
        document.getElementById('scanStatus').textContent = 'QR Code Detected!';
        stopCamera();
        const match = code.data.match(/\/verify\/([A-Za-z0-9\-]+)\s*$/);
        const bookingCode = match ? match[1] : code.data.trim();
        setTimeout(() => {
            closeScanner();
            fetchAndShowVerify(bookingCode);
        }, 300);
    }
}

function submitManualCode() {
    const input = document.getElementById('manualCode');
    if (!input || !input.value.trim()) return;
    closeScanner();
    fetchAndShowVerify(input.value.trim());
}

async function fetchAndShowVerify(code) {
    try {
        const res = await fetch('/verify/' + encodeURIComponent(code) + '?format=json');
        const data = await res.json();
        showScanResult(data, code);
    } catch (err) {
        toast('Could not load booking details');
    }
}

function showScanResult(data, code) {
    const el = document.getElementById('scanResultContent');
    if (!el) return;

    if (data.state === 'valid') {
        el.innerHTML = `
            <div style="text-align:center;padding:12px 0 8px;">
                <div style="width:60px;height:60px;border-radius:50%;background:#dcfce7;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;font-size:28px;">✓</div>
                <div style="font-size:13px;font-weight:700;letter-spacing:.06em;color:#22c55e;margin-bottom:4px;">BOARDING CONFIRMED</div>
                <div style="font-size:22px;font-weight:700;color:var(--ink);margin:10px 0 4px;">${data.passenger_name}</div>
                <div style="display:inline-block;background:var(--ink);color:var(--cream);font-size:24px;font-weight:800;padding:6px 18px;border-radius:6px;font-family:monospace;margin:4px 0 14px;">${data.seat_display}</div>
            </div>
            <div class="passenger-details" style="margin-bottom:16px;">
                <div class="detail-row"><span class="muted">Route</span><span>${data.route}</span></div>
                <div class="detail-row"><span class="muted">Departure</span><span>${data.departure}</span></div>
                <div class="detail-row"><span class="muted">Boarding</span><span>${data.boarding_point}</span></div>
                <div class="detail-row"><span class="muted">Dropping</span><span>${data.dropping_point}</span></div>
                <div class="detail-row"><span class="muted">Fare</span><span>${data.has_balance ? '<span style="color:var(--marigold);font-weight:700;">⚠ Balance Due' + (data.balance_due ? ': ₹' + data.balance_due : '') + '</span>' : '<span style="color:var(--sage);font-weight:700;">Fully Paid ✓</span>'}</span></div>
            </div>
            <button class="btn btn-primary" id="scanBoardBtn"
                    style="background:#22c55e;border:none;"
                    onclick="markBoardedFromPanel('${code}','${data.passenger_name.replace(/'/g,"\\'")}')">
                Mark as Boarded
            </button>`;
    } else if (data.state === 'boarded') {
        el.innerHTML = `
            <div style="text-align:center;padding:12px 0 16px;">
                <div style="width:60px;height:60px;border-radius:50%;background:#fef3c7;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;font-size:28px;">⚠</div>
                <div style="font-size:13px;font-weight:700;letter-spacing:.06em;color:var(--marigold);margin-bottom:4px;">ALREADY BOARDED</div>
                <div style="font-size:22px;font-weight:700;color:var(--ink);margin:10px 0 4px;">${data.passenger_name}</div>
                <div style="display:inline-block;background:var(--ink);color:var(--cream);font-size:24px;font-weight:800;padding:6px 18px;border-radius:6px;font-family:monospace;margin:4px 0 14px;">${data.seat_display}</div>
                <div class="passenger-details" style="margin-bottom:12px;">
                    <div class="detail-row"><span class="muted">Route</span><span>${data.route}</span></div>
                    <div class="detail-row"><span class="muted">Boarded at</span><span style="color:var(--marigold);font-weight:700;">${data.boarded_at}</span></div>
                </div>
                <p class="muted" style="font-size:13px;">This passenger has already been checked in.</p>
            </div>`;
    } else {
        el.innerHTML = `
            <div style="text-align:center;padding:20px 0;">
                <div style="width:60px;height:60px;border-radius:50%;background:#fee2e2;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;font-size:28px;">✕</div>
                <div style="font-size:13px;font-weight:700;letter-spacing:.06em;color:var(--ruby);">INVALID TICKET</div>
                <p class="muted" style="margin-top:12px;font-size:13px;line-height:1.6;">Booking code not found or cancelled.<br>Please check the ticket.</p>
                <div class="mono" style="font-size:11px;color:var(--muted);margin-top:8px;">${code}</div>
            </div>`;
    }
    showPanel('scan');
}

async function markBoardedFromPanel(code, name) {
    const btn = document.getElementById('scanBoardBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Marking…'; }
    try {
        const headers = { 'X-CSRFToken': getCsrfToken() };
        const res = await fetch('/verify/' + encodeURIComponent(code) + '/board', {
            method: 'POST', headers,
        });
        const data = await res.json();
        if (data.status === 'ok') {
            toast('Boarded: ' + name);
            fetchAndShowVerify(code);
        } else if (data.status === 'already_boarded') {
            toast('Already boarded at ' + data.boarded_at);
            fetchAndShowVerify(code);
        } else {
            alert('Error marking as boarded.');
            if (btn) { btn.disabled = false; btn.textContent = 'Mark as Boarded'; }
        }
    } catch (err) {
        alert('Request failed. Please try again.');
        if (btn) { btn.disabled = false; btn.textContent = 'Mark as Boarded'; }
    }
}

// ============================================================
// TOAST NOTIFICATION
// ============================================================

function toast(msg) {
    let t = document.getElementById('toast');
    if (!t) {
        t = document.createElement('div');
        t.id = 'toast';
        t.className = 'toast';
        document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2400);
}

// ============================================================
// REALTIME SYNC via Socket.IO
// ============================================================

const socket = io();

socket.on('seat_booked', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (!seat || seat.classList.contains('active-single')) return;
    seat.classList.remove('booked-m', 'booked-f', 'booked-g', 'multi-selected');
    seat.classList.add('booked-' + (data.gender ? data.gender.toLowerCase() : 'g'));
    if (data.group_code) {
        seat.classList.add('group-seat');
        seat.dataset.group = data.group_code;
    }
    seat.title = data.name;
    // Remove from pending multi-select if it got booked by another agent
    if (selectedSeats.has(data.seat_id)) {
        selectedSeats.delete(data.seat_id);
        updateMultiSeatUI();
    }
    const oc = document.getElementById('occupancyCount');
    if (oc) oc.textContent = parseInt(oc.textContent) + 1;
    toast(`Seat ${data.seat_id} just booked by another agent`);
});

socket.on('seat_freed', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (!seat) return;
    seat.classList.remove('booked-m', 'booked-f', 'booked-g', 'active-single', 'multi-selected', 'group-seat', 'group-highlight');
    delete seat.dataset.group;
    seat.title = `Seat ${data.seat_id}`;
    const oc = document.getElementById('occupancyCount');
    if (oc) oc.textContent = parseInt(oc.textContent) - 1;
    toast(`Seat ${data.seat_id} is now available`);
});

socket.on('seat_locked', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (seat && !seat.classList.contains('booked-m') && !seat.classList.contains('booked-f')) {
        seat.classList.add('locked');
        seat.title = 'Being reserved by a customer';
    }
});

socket.on('seat_unlocked', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (seat && !seat.classList.contains('booked-m') && !seat.classList.contains('booked-f')) {
        seat.classList.remove('locked');
        seat.title = `Seat ${data.seat_id}`;
    }
});

socket.on('passenger_boarded', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const item = document.querySelector(`.manifest-item[data-seat="${data.seat_id}"]`);
    if (item) {
        item.classList.add('boarded');
        const nameDiv = item.querySelector('.manifest-name');
        if (nameDiv) {
            let badge = item.querySelector('.boarding-badge');
            if (!badge) {
                badge = document.createElement('div');
                badge.className = 'boarding-badge';
                nameDiv.parentNode.appendChild(badge);
            }
            badge.textContent = '✓ Boarded ' + data.boarded_at;
        }
    }
    toast(data.name + ' boarded ✓');
});

socket.on('passenger_checkin', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (seat) {
        seat.classList.remove('booked-m', 'booked-f', 'booked-g');
        seat.classList.add(`checked-in-${data.gender ? data.gender.toLowerCase() : 'g'}`);
    }
    updateManifestRowCheckedIn(data.seat_id, data.boarded_at);
    updateCheckinProgress(1);
    const btn = document.querySelector(`.checkin-btn[data-seat="${data.seat_id}"]`);
    if (btn) {
        btn.textContent = '✓';
        btn.classList.add('checked');
        btn.dataset.boarded = data.boarded_at;
        let timeEl = btn.parentNode.querySelector('.manifest-checkin-time');
        if (!timeEl) { timeEl = document.createElement('div'); timeEl.className = 'manifest-checkin-time'; btn.parentNode.appendChild(timeEl); }
        timeEl.textContent = data.boarded_at;
    }
    const swipeBtn = document.querySelector(`.manifest-swipe-action[data-seat="${data.seat_id}"] .manifest-swipe-btn, .manifest-item[data-seat="${data.seat_id}"] .manifest-swipe-btn`);
    if (swipeBtn) {
        swipeBtn.dataset.boarded = data.boarded_at;
        const icon = swipeBtn.querySelector('.manifest-swipe-icon');
        const label = swipeBtn.querySelector('[data-i18n]');
        if (icon) icon.textContent = '↩';
        if (label) { label.textContent = 'Undo'; label.dataset.i18n = 'dash.undo_checkin'; }
        const action = swipeBtn.closest('.manifest-swipe-action');
        if (action) { action.classList.remove('action-checkin'); action.classList.add('action-undo'); }
    }
});

socket.on('passenger_uncheckin', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;
    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (seat) {
        seat.classList.remove('checked-in-m', 'checked-in-f', 'checked-in-g');
        seat.classList.add(`booked-${data.gender ? data.gender.toLowerCase() : 'g'}`);
    }
    updateManifestRowUnchecked(data.seat_id);
    updateCheckinProgress(-1);
    const btn = document.querySelector(`.checkin-btn[data-seat="${data.seat_id}"]`);
    if (btn) {
        btn.textContent = '○';
        btn.classList.remove('checked');
        btn.dataset.boarded = '';
        const timeEl = btn.parentNode.querySelector('.manifest-checkin-time');
        if (timeEl) timeEl.remove();
    }
    const swipeBtn = document.querySelector(`.manifest-item[data-seat="${data.seat_id}"] .manifest-swipe-btn`);
    if (swipeBtn) {
        swipeBtn.dataset.boarded = '';
        const icon = swipeBtn.querySelector('.manifest-swipe-icon');
        const label = swipeBtn.querySelector('[data-i18n]');
        if (icon) icon.textContent = '✓';
        if (label) { label.textContent = 'Check In'; label.dataset.i18n = 'dash.checkin_btn'; }
        const action = swipeBtn.closest('.manifest-swipe-action');
        if (action) { action.classList.remove('action-undo'); action.classList.add('action-checkin'); }
    }
});

// ============================================================
// DATE PICKER + VOYAGE PICKER
// ============================================================

const datePicker = document.getElementById('datePicker');
if (datePicker) {
    datePicker.addEventListener('change', function() {
        const date = this.value;
        if (date) window.location.href = `/staff/dashboard?date=${date}`;
    });
}

const voyagePicker = document.getElementById('voyagePicker');
if (voyagePicker) {
    voyagePicker.addEventListener('change', function() {
        const voyageId = this.value;
        const date = datePicker ? datePicker.value : '';
        window.location.href = `/staff/dashboard?date=${date}&voyage_id=${voyageId}`;
    });
}

// ============================================================
// CSRF TOKEN HELPER
// ============================================================

const CSRF_TOKEN = getCsrfToken();

// ============================================================
// NOTIFICATIONS
// ============================================================

let notifOpen = false;

async function loadNotifications() {
    try {
        const res = await fetch('/staff/api/notifications');
        const data = await res.json();

        const badge = document.getElementById('notifBadge');
        if (badge) {
            if (data.unread > 0) {
                badge.textContent = data.unread > 99 ? '99+' : data.unread;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }

        const list = document.getElementById('notifList');
        if (!list) return;

        if (!data.notifications || !data.notifications.length) {
            list.innerHTML = '<div class="notif-empty">No notifications</div>';
            return;
        }

        list.innerHTML = data.notifications.map(n => {
            const icon = n.title.includes('Cancel') ? '❌' : '🎫';
            const waBtn = n.passenger_phone ?
                `<a class="notif-wa-btn" href="https://wa.me/${n.passenger_phone.replace(/\D/g,'')}" target="_blank" title="WhatsApp">💬</a>` : '';
            return `<div class="notif-item ${n.is_read ? '' : 'unread'}" data-id="${n.id}" data-link="${n.link || ''}" onclick="handleNotifClick(this)">
                <div class="notif-icon">${icon}</div>
                <div>
                    <div class="notif-title-row">${n.title}</div>
                    <div class="notif-msg">${n.message}</div>
                    <div class="notif-time">${n.time_ago}</div>
                </div>
                ${waBtn}
            </div>`;
        }).join('');
    } catch(e) { console.error('Notif load failed', e); }
}

function toggleNotifDropdown() {
    const dd = document.getElementById('notifDropdown');
    if (!dd) return;
    notifOpen = !notifOpen;
    dd.classList.toggle('hidden', !notifOpen);
    if (notifOpen) loadNotifications();
}

async function handleNotifClick(el) {
    const id = el.dataset.id;
    const link = el.dataset.link;
    try {
        await fetch(`/staff/api/notifications/read/${id}`, { method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN} });
    } catch (_) {}
    if (link) window.location.href = link;
    else toggleNotifDropdown();
}

async function markAllRead() {
    try {
        await fetch('/staff/api/notifications/read-all', { method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN} });
    } catch (_) {}
    loadNotifications();
}

// Real-time: listen for new notifications
socket.on('new_notification', (data) => {
    const badge = document.getElementById('notifBadge');
    if (badge && data.count > 0) {
        badge.textContent = data.count > 99 ? '99+' : data.count;
        badge.classList.remove('hidden');
        badge.style.animation = 'none';
        requestAnimationFrame(() => { badge.style.animation = ''; });
    }
    if (notifOpen) loadNotifications();
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (notifOpen && !e.target.closest('#notifBell') && !e.target.closest('#notifDropdown')) {
        notifOpen = false;
        document.getElementById('notifDropdown')?.classList.add('hidden');
    }
});

// Load on page load
document.addEventListener('DOMContentLoaded', loadNotifications);

// Single-seat phone country code initialization + driver helpers
document.addEventListener('DOMContentLoaded', function () {
    const singleCc = document.getElementById('singleCc');
    if (singleCc) buildCountrySelect(singleCc);
    initManifestSwipe();
    initDepartureCountdown();
});

function initDepartureCountdown() {
    const main = document.querySelector('.staff-main');
    const el = document.getElementById('departureCountdown');
    if (!main || !main.dataset.departure || !el) return;

    function update() {
        const dep = new Date(main.dataset.departure);
        const diffMin = Math.round((dep - Date.now()) / 60000);
        const lang = document.documentElement.lang || 'en';
        if (Math.abs(diffMin) < 2) {
            el.textContent = lang === 'hi' ? '· अभी प्रस्थान' : '· departing now';
            el.style.color = 'var(--marigold)';
        } else if (diffMin > 0) {
            el.textContent = lang === 'hi' ? `· ${diffMin} मिनट में` : `· in ${diffMin}m`;
            el.style.color = diffMin <= 30 ? 'var(--marigold)' : 'var(--muted)';
        } else {
            el.textContent = lang === 'hi' ? `· ${Math.abs(diffMin)} मिनट पहले` : `· departed ${Math.abs(diffMin)}m ago`;
            el.style.color = 'var(--muted)';
        }
    }
    update();
    setInterval(update, 30000);
}

// ============================================================
// STOP FILTER (driver view only)
// ============================================================
var _stopFilter = { boarding: 'ALL', dropping: 'ALL' };

function setStopFilter(type, stop, btn) {
    _stopFilter[type] = stop;

    // Update active pill in that row
    var pills = document.querySelectorAll('.stop-pill[data-type="' + type + '"]');
    pills.forEach(function(p) { p.classList.toggle('active', p.dataset.stop === stop); });

    applyStopFilter();
}

function applyStopFilter() {
    var bFilter = _stopFilter.boarding;
    var dFilter = _stopFilter.dropping;
    var isFiltered = (bFilter !== 'ALL' || dFilter !== 'ALL');

    var seats = document.querySelectorAll('#seatMap .seat');
    var manifestItems = document.querySelectorAll('.manifest-item');
    var shown = 0;
    var total = manifestItems.length;

    seats.forEach(function(seat) {
        var boarding = seat.dataset.boarding || '';
        var dropping = seat.dataset.dropping || '';
        var isBooked = boarding !== '' || dropping !== '';

        if (!isFiltered || !isBooked) {
            // Unfiltered or empty seat: restore normal
            seat.classList.remove('stop-dimmed', 'stop-highlighted');
            seat.style.pointerEvents = '';
        } else {
            var bMatch = (bFilter === 'ALL' || boarding === bFilter);
            var dMatch = (dFilter === 'ALL' || dropping === dFilter);
            if (bMatch && dMatch) {
                seat.classList.add('stop-highlighted');
                seat.classList.remove('stop-dimmed');
                seat.style.pointerEvents = '';
            } else {
                seat.classList.add('stop-dimmed');
                seat.classList.remove('stop-highlighted');
                seat.style.pointerEvents = 'none';
            }
        }
    });

    manifestItems.forEach(function(item) {
        var boarding = item.dataset.boarding || '';
        var dropping = item.dataset.dropping || '';

        if (!isFiltered) {
            item.style.display = '';
            shown++;
        } else {
            var bMatch = (bFilter === 'ALL' || boarding === bFilter);
            var dMatch = (dFilter === 'ALL' || dropping === dFilter);
            if (bMatch && dMatch) {
                item.style.display = '';
                shown++;
            } else {
                item.style.display = 'none';
            }
        }
    });

    // Update count label
    var countEl = document.getElementById('manifestFilterCount');
    var stopCountEl = document.getElementById('stopFilterCount');

    if (countEl) {
        if (isFiltered && shown < total) {
            countEl.textContent = shown + ' ' + (TRANSLATIONS && TRANSLATIONS[localStorage.getItem('lang')||'en']['dash.filter_shown'] || 'shown') + ' / ' + total + ' ' + (TRANSLATIONS && TRANSLATIONS[localStorage.getItem('lang')||'en']['dash.filter_total'] || 'total');
            countEl.classList.remove('hidden');
        } else {
            countEl.classList.add('hidden');
        }
    }
    if (stopCountEl) {
        if (isFiltered && shown < total) {
            stopCountEl.textContent = shown + ' / ' + total;
            stopCountEl.classList.remove('hidden');
        } else {
            stopCountEl.classList.add('hidden');
        }
    }
}
