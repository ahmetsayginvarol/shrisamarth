// ============================================================
// SHRISAMARTH Customer Booking — seat selection + real-time
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
    { dial: '+92',  flag: '🇵🇰', name: 'Pakistan' },
    { dial: '+880', flag: '🇧🇩', name: 'Bangladesh' },
    { dial: '+94',  flag: '🇱🇰', name: 'Sri Lanka' },
    { dial: '+977', flag: '🇳🇵', name: 'Nepal' },
];

function buildCountrySelect(selectEl) {
    selectEl.innerHTML = COUNTRY_CODES.map(c =>
        `<option value="${c.dial}">${c.flag} ${c.dial}</option>`
    ).join('');
    selectEl.value = '+91';
}

function getPhoneValue(ccEl, numEl) {
    return (ccEl.value || '+91') + ' ' + numEl.value.trim();
}

const bookApp = document.getElementById('bookApp');
const VOYAGE_ID = parseInt(bookApp.dataset.voyageId);
const BASE_FARE = parseFloat(bookApp.dataset.baseFare);
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;
const STOP_FARES = JSON.parse(bookApp.dataset.stopFares || '{}');

const _prefill = JSON.parse(bookApp.dataset.prefill || '{}');
const _boardingStops = JSON.parse(bookApp.dataset.boardingStops || '[]');
const _droppingStops = JSON.parse(bookApp.dataset.droppingStops || '[]');

function getStopFare(stopName) {
    return (stopName && STOP_FARES[stopName] != null) ? STOP_FARES[stopName] : BASE_FARE;
}

let myLockedSeats = new Set();  // seat IDs locked by this session
let selectedSeats = new Set();  // seats selected for booking (subset of myLockedSeats)

// ============================================================
// INIT
// ============================================================

async function initSeatStatus() {
    try {
        const res = await fetch(`/api/seat-status/${VOYAGE_ID}`);
        const data = await res.json();

        data.locked_other.forEach(sid => {
            const el = document.querySelector(`.seat[data-seat="${sid}"]`);
            if (el) {
                el.classList.add('locked');
                el.title = 'Being reserved by another passenger';
            }
        });

        data.locked_mine.forEach(sid => {
            const el = document.querySelector(`.seat[data-seat="${sid}"]`);
            if (el) {
                el.classList.add('active-single');
            }
            myLockedSeats.add(sid);
            selectedSeats.add(sid);
        });

        updateSelectionUI();
    } catch (e) {
        console.error('Failed to load seat status', e);
    }
}

// ============================================================
// SEAT CLICK HANDLER
// ============================================================

document.querySelectorAll('.seat').forEach(seat => {
    seat.addEventListener('click', async () => {
        const sid = seat.dataset.seat;

        // Skip booked seats
        if (seat.classList.contains('booked-m') || seat.classList.contains('booked-f')) return;
        // Skip seats locked by others
        if (seat.classList.contains('locked') && !myLockedSeats.has(sid)) return;

        if (myLockedSeats.has(sid)) {
            // Deselect: unlock
            await unlockSeat(sid);
            myLockedSeats.delete(sid);
            selectedSeats.delete(sid);
            seat.classList.remove('active-single');
        } else {
            // Select: lock
            const ok = await lockSeat(sid);
            if (ok) {
                myLockedSeats.add(sid);
                selectedSeats.add(sid);
                seat.classList.add('active-single');
            }
        }
        updateSelectionUI();
    });
});

// ============================================================
// LOCK / UNLOCK
// ============================================================

async function lockSeat(sid) {
    try {
        const res = await fetch('/api/lock-seat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ voyage_id: VOYAGE_ID, seat_id: sid }),
        });

        if (res.status === 409) {
            const d = await res.json();
            if (d.error === 'already_booked') {
                alert(t('c.seat_just_booked'));
                const el = document.querySelector(`.seat[data-seat="${sid}"]`);
                if (el) {
                    el.classList.add('booked-m');  // generic placeholder until refresh
                    el.title = 'Booked';
                }
            } else if (d.error === 'locked_by_other') {
                alert(t('c.seat_being_reserved'));
                const el = document.querySelector(`.seat[data-seat="${sid}"]`);
                if (el) {
                    el.classList.add('locked');
                    el.title = 'Being reserved by another passenger';
                }
            }
            return false;
        }
        return res.ok;
    } catch (e) {
        console.error('Lock failed', e);
        return false;
    }
}

async function unlockSeat(sid) {
    try {
        await fetch('/api/unlock-seat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ voyage_id: VOYAGE_ID, seat_id: sid }),
        });
    } catch (e) {
        console.error('Unlock failed', e);
    }
}

// ============================================================
// UI STATE
// ============================================================

function scrollToPanel() {
    if (window.innerWidth >= 900) return;
    const panel = document.querySelector('.c-book-panel');
    if (panel) setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
}

function updateSelectionUI() {
    const count = selectedSeats.size;
    const totalFare = count * BASE_FARE;

    const panelEmpty = document.getElementById('panel-empty');
    const panelSelected = document.getElementById('panel-selected');
    const panelForm = document.getElementById('panel-form');
    const panelGroupForm = document.getElementById('panel-group-form');

    if (count > 0) {
        panelEmpty.classList.add('hidden');
        panelSelected.classList.remove('hidden');
        panelForm.classList.add('hidden');
        panelGroupForm.classList.add('hidden');

        document.getElementById('selectedSeatsList').textContent =
            Array.from(selectedSeats).sort().join(', ');
        document.getElementById('totalFareDisplay').textContent =
            '₹ ' + totalFare.toLocaleString('en-IN');
        document.getElementById('seatCountDisplay').textContent =
            `${count} seat${count !== 1 ? 's' : ''}`;

        scrollToPanel();
    } else {
        panelEmpty.classList.remove('hidden');
        panelSelected.classList.add('hidden');
        panelForm.classList.add('hidden');
        panelGroupForm.classList.add('hidden');
    }
}

function updateSingleFareDisplay(stopName) {
    const fare = getStopFare(stopName);
    const fareEl = document.getElementById('formFareSummary');
    if (fareEl) fareEl.textContent = '₹ ' + fare.toLocaleString('en-IN');
    const noteEl = document.getElementById('singleFareNote');
    if (!noteEl) return;
    if (fare < BASE_FARE) {
        const saving = BASE_FARE - fare;
        noteEl.innerHTML = `<span style="color:var(--sage,#5a8a5a);">Fare for your journey: ₹${fare.toLocaleString('en-IN')} <span style="font-size:12px;">(₹${saving.toLocaleString('en-IN')} off base fare)</span></span>`;
        noteEl.style.display = 'block';
    } else {
        noteEl.innerHTML = `Fare for your journey: ₹${fare.toLocaleString('en-IN')}`;
        noteEl.style.display = fare !== BASE_FARE ? 'block' : 'none';
    }
}

function showBookingForm() {
    document.getElementById('panel-empty').classList.add('hidden');
    document.getElementById('panel-selected').classList.add('hidden');
    document.getElementById('panel-group-form').classList.add('hidden');
    scrollToPanel();

    const seats = Array.from(selectedSeats).sort();

    if (seats.length === 1) {
        // Single seat: show static form
        document.getElementById('panel-form').classList.remove('hidden');
        // Inject seat_id
        const container = document.getElementById('seatInputsContainer');
        container.innerHTML = '';
        const inp = document.createElement('input');
        inp.type = 'hidden'; inp.name = 'seat_ids[]'; inp.value = seats[0];
        container.appendChild(inp);
        document.getElementById('formSeatSummary').textContent = seats[0];
        // Prefill phone number input
        const custPhone = document.getElementById('custSinglePhone');
        if (custPhone && _prefill.phone) custPhone.value = _prefill.phone;
        // Set initial fare based on first boarding stop option
        const boardingSel = document.querySelector('#panel-form select[name="boarding_point"]');
        const initStop = boardingSel ? boardingSel.value : '';
        updateSingleFareDisplay(initStop);
        // Wire boarding stop change to live fare update
        if (boardingSel && !boardingSel._fareWired) {
            boardingSel._fareWired = true;
            boardingSel.addEventListener('change', () => updateSingleFareDisplay(boardingSel.value));
        }
    } else {
        // Multi-seat: show per-passenger form
        document.getElementById('panel-form').classList.add('hidden');
        renderGroupForm(seats);
        document.getElementById('panel-group-form').classList.remove('hidden');
    }
}

function renderGroupForm(seats) {
    document.getElementById('groupFormSeatSummary').textContent = seats.join(', ');
    document.getElementById('groupFormFareSummary').textContent =
        '₹ ' + (seats.length * BASE_FARE).toLocaleString('en-IN');

    function makeBoardingField() {
        if (_boardingStops.length) {
            return `<select class="form-select" id="cgrp_boarding">` +
                _boardingStops.map(s => `<option value="${s}">${s}</option>`).join('') +
                `</select>`;
        }
        return `<input type="text" class="form-input" id="cgrp_boarding" placeholder="${t('c.boarding_stop_ph')}">`;
    }
    function makeDroppingField() {
        if (_droppingStops.length) {
            return `<select class="form-select" id="cgrp_dropping">` +
                _droppingStops.map(s => `<option value="${s}">${s}</option>`).join('') +
                `</select>`;
        }
        return `<input type="text" class="form-input" id="cgrp_dropping" placeholder="${t('c.dropping_stop_ph')}">`;
    }

    const html = `<div class="group-seat-section">
        <div class="form-group">
            <label class="form-label">${t('c.group_name_label')}</label>
            <input type="text" class="form-input" id="cgrp_name" value="${_prefill.name || ''}" placeholder="Full name" required>
        </div>
        <div class="form-group">
            <label class="form-label">${t('c.contact')}</label>
            <div class="phone-input-row">
                <select class="country-code-select" id="cgrp_cc"></select>
                <input type="text" class="form-input phone-number-input" id="cgrp_phone" placeholder="XXXXX XXXXX" value="${_prefill.phone || ''}">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label class="form-label">${t('c.boarding')}</label>
                ${makeBoardingField()}
            </div>
            <div class="form-group">
                <label class="form-label">${t('c.dropping')}</label>
                ${makeDroppingField()}
            </div>
        </div>
        <div class="form-group">
            <label class="form-label">${t('c.email_optional')}</label>
            <input type="email" class="form-input" id="cgrp_email" placeholder="you@email.com" value="${_prefill.email || ''}">
        </div>
        <div style="background:var(--cream-2); border:1px solid var(--line); border-radius:6px; padding:14px; margin-bottom:16px; font-size:13px; color:var(--muted);">
            ${t('c.balance_info')}
        </div>
        <div class="form-actions" style="justify-content:space-between;">
            <button type="button" class="btn btn-ghost" onclick="cancelForm()">${t('c.back')}</button>
            <button type="button" class="btn btn-primary" style="width:auto; flex:1; margin-left:10px;" onclick="submitGroupCustomerBooking()">
                ${t('c.confirm_booking')}
            </button>
        </div>
    </div>`;

    document.getElementById('groupFormBody').innerHTML = html;
    buildCountrySelect(document.getElementById('cgrp_cc'));

    // Wire boarding stop change to update group fare summary
    const grpBoarding = document.getElementById('cgrp_boarding');
    if (grpBoarding) {
        const updateGroupFare = () => {
            const fare = getStopFare(grpBoarding.value);
            const total = seats.length * fare;
            document.getElementById('groupFormFareSummary').textContent =
                '₹ ' + total.toLocaleString('en-IN');
        };
        grpBoarding.addEventListener('change', updateGroupFare);
        updateGroupFare();
    }
}

function cancelForm() {
    document.getElementById('panel-form').classList.add('hidden');
    document.getElementById('panel-group-form').classList.add('hidden');
    updateSelectionUI();
}

// ============================================================
// GROUP BOOKING SUBMIT
// ============================================================

async function submitGroupCustomerBooking() {
    const seats = Array.from(selectedSeats).sort();

    const name = (document.getElementById('cgrp_name')?.value || '').trim();
    const ccEl = document.getElementById('cgrp_cc');
    const numEl = document.getElementById('cgrp_phone');
    const phone = getPhoneValue(ccEl, numEl).trim();
    const boardingEl = document.getElementById('cgrp_boarding');
    const droppingEl = document.getElementById('cgrp_dropping');
    const boarding = (boardingEl?.value || '').trim();
    const dropping = (droppingEl?.value || '').trim();
    const email = (document.getElementById('cgrp_email')?.value || '').trim() || null;

    if (!name) { alert(t('c.name_required')); document.getElementById('cgrp_name')?.focus(); return; }
    if (!numEl?.value.trim()) { alert(t('c.phone_required')); numEl?.focus(); return; }
    if (!boarding) { alert(t('c.boarding_required')); boardingEl?.focus(); return; }
    if (!dropping) { alert(t('c.dropping_required')); droppingEl?.focus(); return; }

    const passengers = seats.map(sid => ({ seat_id: sid, name, phone, gender: null }));

    const submitBtn = document.querySelector('#panel-group-form button.btn-primary');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = t('c.confirming'); }

    try {
        const res = await fetch('/api/customer/book', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
            body: JSON.stringify({
                voyage_id: VOYAGE_ID,
                passengers,
                boarding_point: boarding,
                dropping_point: dropping,
                email,
            }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            window.location.href = `/booking/confirmation/${data.code}`;
        } else {
            alert(t('c.booking_failed_err'));
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = t('c.confirm_booking'); }
        }
    } catch (err) {
        alert(t('c.booking_failed_err'));
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = t('c.confirm_booking'); }
    }
}

// ============================================================
// BOOKING FORM SUBMIT (single-seat)
// ============================================================

const bookingForm = document.getElementById('customerBookingForm');
if (bookingForm) {
    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        // Combine country code + phone number before capturing FormData
        const ccEl = document.getElementById('custSingleCc');
        const numEl = document.getElementById('custSinglePhone');
        const combined = document.getElementById('custSinglePhoneCombined');
        if (ccEl && numEl && combined) combined.value = getPhoneValue(ccEl, numEl);

        const submitBtn = bookingForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = t('c.confirming');

        try {
            const formData = new FormData(bookingForm);
            const res = await fetch('/api/customer/book', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (data.status === 'success') {
                window.location.href = `/booking/confirmation/${data.code}`;
            } else if (data.status === 'captcha_required') {
                document.getElementById('captchaQuestion').textContent = data.question;
                document.getElementById('captchaTokenInput').value = data.token;
                document.getElementById('captchaSection').style.display = 'block';
                document.getElementById('captchaAnswerInput').focus();
                const errEl = document.getElementById('captchaError');
                if (data.error) { errEl.textContent = data.error; errEl.style.display = 'block'; }
                else { errEl.style.display = 'none'; }
                submitBtn.disabled = false;
                submitBtn.textContent = t('c.confirm_booking');
            } else {
                alert(data.message || t('c.booking_failed_err'));
                submitBtn.disabled = false;
                submitBtn.textContent = t('c.confirm_booking');
            }
        } catch (err) {
            alert(t('c.booking_failed_err'));
            submitBtn.disabled = false;
            submitBtn.textContent = t('c.confirm_booking');
        }
    });
}

// ============================================================
// DOM CONTENT LOADED — initialize single-seat CC dropdown
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    const ccEl = document.getElementById('custSingleCc');
    if (ccEl) buildCountrySelect(ccEl);
});

// ============================================================
// SOCKET.IO REAL-TIME UPDATES
// ============================================================

const socket = io();

socket.on('seat_locked', (data) => {
    if (parseInt(data.voyage_id) !== VOYAGE_ID) return;
    const sid = data.seat_id;
    if (myLockedSeats.has(sid)) return;  // it's ours
    const el = document.querySelector(`.seat[data-seat="${sid}"]`);
    if (el && !el.classList.contains('booked-m') && !el.classList.contains('booked-f') && !el.classList.contains('booked-g')) {
        el.classList.add('locked');
        el.title = 'Being reserved by another passenger';
    }
});

socket.on('seat_unlocked', (data) => {
    if (parseInt(data.voyage_id) !== VOYAGE_ID) return;
    const el = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (el) {
        el.classList.remove('locked');
        el.title = `Seat ${data.seat_id}`;
    }
});

socket.on('seat_booked', (data) => {
    if (parseInt(data.voyage_id) !== VOYAGE_ID) return;
    const sid = data.seat_id;
    const el = document.querySelector(`.seat[data-seat="${sid}"]`);
    if (el) {
        el.classList.remove('locked', 'active-single');
        el.classList.add('booked-' + (data.gender ? data.gender.toLowerCase() : 'g'));
        el.title = data.name;

        if (myLockedSeats.has(sid)) {
            myLockedSeats.delete(sid);
            selectedSeats.delete(sid);
            updateSelectionUI();
        }
    }
});

socket.on('seat_freed', (data) => {
    if (parseInt(data.voyage_id) !== VOYAGE_ID) return;
    const el = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (el) {
        el.classList.remove('booked-m', 'booked-f', 'active-single', 'locked');
        el.title = `Seat ${data.seat_id}`;
    }
});

// ============================================================
// BOOTSTRAP
// ============================================================

initSeatStatus();
