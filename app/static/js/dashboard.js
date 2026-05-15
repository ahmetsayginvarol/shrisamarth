// ============================================================
// SHRISAMARTH Dashboard — seat grid interactivity
// ============================================================

const staffMain = document.querySelector('.staff-main');
const VOYAGE_ID = staffMain ? staffMain.dataset.voyageId : null;
const BASE_FARE = staffMain ? parseFloat(staffMain.dataset.baseFare) : 0;

let currentSeatId = null;
let currentBookingId = null;

// ============================================================
// PANEL SWITCHING
// ============================================================

function showPanel(name) {
    document.querySelectorAll('.panel-view').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.remove('hidden');
}

function closePanel() {
    const isDriver = !document.getElementById('panel-booking');

    if (isDriver) {
        showPanel('manifest');
    } else {
        showPanel('empty');
    }

    document.querySelectorAll('.seat.selected').forEach(s => s.classList.remove('selected'));
    currentSeatId = null;
    currentBookingId = null;
}

// Manifest item click — highlights seat and shows details
function manifestClick(seatId) {
    const seat = document.querySelector(`.seat[data-seat="${seatId}"]`);
    if (seat) {
        document.querySelectorAll('.seat.selected').forEach(s => s.classList.remove('selected'));
        seat.classList.add('selected');
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
// SEAT CLICK HANDLER
// ============================================================

document.querySelectorAll('.seat').forEach(seat => {
    seat.addEventListener('click', async () => {
        const seatId = seat.dataset.seat;
        currentSeatId = seatId;

        document.querySelectorAll('.seat.selected').forEach(s => s.classList.remove('selected'));
        seat.classList.add('selected');

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
                    showBookingForm(data);
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

function showBookingForm(data) {
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

// Submit booking — only attach if form exists
const bookingForm = document.getElementById('bookingForm');
if (bookingForm) {
    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);

        try {
            const res = await fetch('/staff/booking/create', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (data.status === 'success') {
                const seat = document.querySelector(`.seat[data-seat="${data.booking.seat_id}"]`);
                seat.classList.remove('selected');
                seat.classList.add('booked-' + data.booking.gender.toLowerCase());
                seat.title = data.booking.name;

                const oc = document.getElementById('occupancyCount');
                if (oc) oc.textContent = parseInt(oc.textContent) + 1;

                closePanel();
                toast(`Seat ${data.booking.seat_id} booked for ${data.booking.name}`);

            } else if (data.status === 'gender_conflict') {
                alert(data.message);

            } else if (data.status === 'error') {
                const msg = data.message || JSON.stringify(data.errors);
                alert('Error: ' + msg);
            }
        } catch (err) {
            console.error('Booking failed:', err);
            alert('Booking failed. Please try again.');
        }
    });
}

// ============================================================
// PASSENGER DETAILS
// ============================================================

function showBookingDetails(booking, readonly) {
    currentBookingId = booking.id;

    document.getElementById('detailsSeatLabel').textContent = booking.seat || currentSeatId;
    document.getElementById('detailsName').textContent = booking.name;
    document.getElementById('detailsPhone').textContent = booking.phone;
    document.getElementById('detailsBoarding').textContent = booking.boarding;
    document.getElementById('detailsDropping').textContent = booking.dropping;
    document.getElementById('detailsFare').textContent = '₹ ' + booking.fare;
    document.getElementById('detailsAdvance').textContent = '₹ ' + booking.advance;
    document.getElementById('detailsBalance').textContent = '₹ ' + booking.balance;
    document.getElementById('detailsCode').textContent = booking.code;

    // Store booking info for ticket download
    const ticketBtn = document.getElementById('ticketDownloadBtn');
    if (ticketBtn) {
        ticketBtn.dataset.bookingId = booking.id;
        ticketBtn.dataset.bookingName = booking.name;
        ticketBtn.dataset.bookingCode = booking.code;
        ticketBtn.dataset.bookingSeat = booking.seat || currentSeatId;
    }

    // Store booking info for WhatsApp
    const waBtn = document.getElementById('whatsappBtn');
    if (waBtn) {
        waBtn.dataset.phone = booking.phone || '';
        waBtn.dataset.name = booking.name;
        waBtn.dataset.seat = booking.seat || currentSeatId;
        waBtn.dataset.code = booking.code;
        waBtn.dataset.boarding = booking.boarding;
        waBtn.dataset.dropping = booking.dropping;
        waBtn.dataset.fare = booking.fare;
        waBtn.dataset.balance = booking.balance;
        waBtn.dataset.bookingId = booking.id;
    }

    // Hide action buttons for drivers
    const cancelBtn = document.getElementById('cancelBookingBtn');
    if (cancelBtn) cancelBtn.style.display = readonly ? 'none' : 'inline-block';
    if (ticketBtn) ticketBtn.style.display = readonly ? 'none' : 'inline-block';
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

        const id = this.dataset.bookingId;
        const name = this.dataset.bookingName;
        const code = this.dataset.bookingCode;
        const seat = this.dataset.bookingSeat;

        if (!id) return;

        const confirmed = confirm(
            `Download e-ticket for ${name}?\n\nSeat ${seat} · ${code}`
        );

        if (confirmed) {
            window.open(`/staff/booking/${id}/ticket`, '_blank');
        }
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

        const name = this.dataset.name;
        const seat = this.dataset.seat;
        const code = this.dataset.code;
        const boarding = this.dataset.boarding;
        const dropping = this.dataset.dropping;
        const fare = this.dataset.fare;
        const balance = this.dataset.balance;
        const phone = this.dataset.phone;

        if (!name) return;

        // Build WhatsApp message
        const message =
            `🚌 *SHRISAMARTH TRAVELS*\n` +
            `━━━━━━━━━━━━━━━━\n\n` +
            `Dear *${name}*,\n\n` +
            `Your booking is confirmed! ✅\n\n` +
            `🎫 *Booking ID:* ${code}\n` +
            `💺 *Seat:* ${seat}\n` +
            `📍 *Boarding:* ${boarding}\n` +
            `📍 *Dropping:* ${dropping}\n` +
            `💰 *Fare:* ₹${fare}\n` +
            `${parseFloat(balance) > 0 ? '⚠️ *Balance Due:* ₹' + balance + '\n' : '✅ *Payment:* Complete\n'}` +
            `\n━━━━━━━━━━━━━━━━\n` +
            `Show this message at boarding.\n` +
            `Thank you for travelling with us! 🙏`;

        // Clean phone number for WhatsApp URL
        let cleanPhone = phone.replace(/[\s\-\(\)]/g, '');
        if (cleanPhone.startsWith('+')) {
            cleanPhone = cleanPhone.substring(1);
        }
        if (!cleanPhone.startsWith('91') && cleanPhone.length === 10) {
            cleanPhone = '91' + cleanPhone;
        }

        const waUrl = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`;
        window.open(waUrl, '_blank');
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
                seat.classList.remove('booked-m', 'booked-f', 'selected');
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
    if (!seat || seat.classList.contains('selected')) return;

    seat.classList.remove('booked-m', 'booked-f');
    seat.classList.add('booked-' + data.gender.toLowerCase());
    seat.title = data.name;

    const oc = document.getElementById('occupancyCount');
    if (oc) oc.textContent = parseInt(oc.textContent) + 1;

    toast(`Seat ${data.seat_id} just booked by another agent`);
});
// ============================================================
// DATE PICKER + VOYAGE PICKER
// ============================================================

const datePicker = document.getElementById('datePicker');
if (datePicker) {
    datePicker.addEventListener('change', function() {
        const date = this.value;
        if (date) {
            window.location.href = `/staff/dashboard?date=${date}`;
        }
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
socket.on('seat_freed', (data) => {
    if (parseInt(data.voyage_id) !== parseInt(VOYAGE_ID)) return;

    const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
    if (!seat) return;

    seat.classList.remove('booked-m', 'booked-f', 'selected');
    seat.title = `Seat ${data.seat_id}`;

    const oc = document.getElementById('occupancyCount');
    if (oc) oc.textContent = parseInt(oc.textContent) - 1;

    toast(`Seat ${data.seat_id} is now available`);
});