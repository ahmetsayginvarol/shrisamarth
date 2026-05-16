// ============================================================
// SHRISAMARTH Dashboard — seat grid interactivity
// ============================================================

const staffMain = document.querySelector('.staff-main');
const VOYAGE_ID = staffMain ? staffMain.dataset.voyageId : null;
const BASE_FARE = staffMain ? parseFloat(staffMain.dataset.baseFare) : 0;

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
        });
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

    // Populate hidden seat inputs for group form
    const container = document.getElementById('groupSeatInputs');
    if (container) {
        container.innerHTML = '';
        seats.forEach(sid => {
            const inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'seat_ids[]';
            inp.value = sid;
            container.appendChild(inp);
        });
    }

    // Hide the single seat_id field — group uses seat_ids[] instead
    const singleSeatInput = document.getElementById('formSeatId');
    if (singleSeatInput) singleSeatInput.value = '';

    document.getElementById('bookingSeatLabel').textContent = seats.join(', ');
    document.getElementById('bookingForm').reset();
    document.querySelector('input[name="fare"]').value = BASE_FARE;
    document.querySelector('input[name="advance_paid"]').value = 0;
    document.getElementById('genderWarning').classList.add('hidden');
    window._adjacentGenders = [];
    window._isGroupBooking = true;

    showPanel('booking');
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
        const formData = new FormData(e.target);

        if (window._isGroupBooking) {
            await submitGroupBooking(formData);
        } else {
            await submitSingleBooking(formData);
        }
    });
}

async function submitSingleBooking(formData) {
    try {
        const res = await fetch('/staff/booking/create', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (data.status === 'success') {
            const seat = document.querySelector(`.seat[data-seat="${data.booking.seat_id}"]`);
            seat.classList.remove('active-single');
            seat.classList.add('booked-' + data.booking.gender.toLowerCase());
            seat.title = data.booking.name;

            const oc = document.getElementById('occupancyCount');
            if (oc) oc.textContent = parseInt(oc.textContent) + 1;

            closePanel();
            toast(`Seat ${data.booking.seat_id} booked for ${data.booking.name}`);

        } else if (data.status === 'gender_conflict') {
            alert(data.message);

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
                    seat.title = data.name;
                }
            });

            const oc = document.getElementById('occupancyCount');
            if (oc) oc.textContent = parseInt(oc.textContent) + data.seat_ids.length;

            selectedSeats.clear();
            updateMultiSeatUI();

            // Offer group ticket download
            closePanel();
            toast(`${data.seat_ids.length} seats booked for ${data.name}`);

            // Show a quick follow-up prompt for group ticket
            if (confirm(`Group booking confirmed!\nSeats: ${data.seat_ids.join(', ')}\nBooking ID: ${data.group_code}\n\nDownload group e-ticket?`)) {
                window.open(`/staff/booking/group/${data.group_code}/ticket`, '_blank');
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
            const csrfEl = document.querySelector('input[name="csrf_token"]');
            const headers = {};
            if (csrfEl) headers['X-CSRFToken'] = csrfEl.value;

            const res = await fetch(`/staff/booking/${currentBookingId}/cancel`, {
                method: 'POST',
                headers: headers,
            });
            const data = await res.json();

            if (data.status === 'success') {
                const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
                seat.classList.remove('booked-m', 'booked-f', 'active-single', 'multi-selected');
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
    seat.classList.remove('booked-m', 'booked-f', 'multi-selected');
    seat.classList.add('booked-' + data.gender.toLowerCase());
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
    seat.classList.remove('booked-m', 'booked-f', 'active-single', 'multi-selected');
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

const csrfEl = document.querySelector('input[name="csrf_token"]');
const CSRF_TOKEN = csrfEl ? csrfEl.value : '';

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
    await fetch(`/staff/api/notifications/read/${id}`, { method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN} });
    if (link) window.location.href = link;
    else toggleNotifDropdown();
}

async function markAllRead() {
    await fetch('/staff/api/notifications/read-all', { method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN} });
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
