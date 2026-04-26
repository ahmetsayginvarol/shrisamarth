// ============================================================
// SHRISAMARTH Dashboard — seat grid interactivity
// ============================================================

const VOYAGE_ID = document.querySelector('.staff-main').dataset.voyageId;
const BASE_FARE = parseFloat(document.querySelector('.staff-main').dataset.baseFare);

let currentSeatId = null;
let currentBookingId = null;

// ----- Panel switching -----
function showPanel(name) {
    document.querySelectorAll('.panel-view').forEach(p => p.classList.add('hidden'));
    document.getElementById('panel-' + name).classList.remove('hidden');
}

function closePanel() {
    showPanel('empty');
    document.querySelectorAll('.seat.selected').forEach(s => s.classList.remove('selected'));
    currentSeatId = null;
    currentBookingId = null;
}

// ----- Seat click handler -----
document.querySelectorAll('.seat').forEach(seat => {
    seat.addEventListener('click', async () => {
        const seatId = seat.dataset.seat;
        currentSeatId = seatId;

        // Visual selection
        document.querySelectorAll('.seat.selected').forEach(s => s.classList.remove('selected'));
        seat.classList.add('selected');

        try {
            const res = await fetch(`/staff/api/seat/${VOYAGE_ID}/${seatId}`);
            const data = await res.json();

            if (data.status === 'booked') {
                showBookingDetails(data.booking);
            } else {
                showBookingForm(data);
            }
        } catch (err) {
            console.error('Failed to load seat info:', err);
            alert('Could not load seat information. Please try again.');
        }
    });
});

// ----- Show booking form for empty seat -----
function showBookingForm(data) {
    document.getElementById('bookingSeatLabel').textContent = data.seat_id;
    document.getElementById('formSeatId').value = data.seat_id;
    document.getElementById('confirmConflict').value = 'no';

    // Reset form
    document.getElementById('bookingForm').reset();
    document.querySelector('input[name="seat_id"]').value = data.seat_id;
    document.querySelector('input[name="voyage_id"]').value = VOYAGE_ID;
    document.querySelector('input[name="fare"]').value = BASE_FARE;
    document.querySelector('input[name="advance_paid"]').value = 0;

    // Hide warning by default
    document.getElementById('genderWarning').classList.add('hidden');

    // Store adjacency info on the form for gender-change handler
    window._adjacentGenders = data.adjacent_genders || [];

    showPanel('booking');
}

// ----- Gender change → check for conflict -----
document.querySelectorAll('input[name="gender"]').forEach(radio => {
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
            document.getElementById('confirmConflict').value = 'yes'; // user has been warned
        } else {
            warning.classList.add('hidden');
            document.getElementById('confirmConflict').value = 'no';
        }
    });
});

// ----- Show passenger details for booked seat -----
function showBookingDetails(booking) {
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
    showPanel('details');
}

// ----- Submit booking -----
document.getElementById('bookingForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    try {
        const res = await fetch('/staff/booking/create', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (data.status === 'success') {
            // Update seat visually
            const seat = document.querySelector(`.seat[data-seat="${data.booking.seat_id}"]`);
            seat.classList.remove('selected');
            seat.classList.add('booked-' + data.booking.gender.toLowerCase());
            seat.title = data.booking.name;

            // Update occupancy
            const oc = document.getElementById('occupancyCount');
            oc.textContent = parseInt(oc.textContent) + 1;

            closePanel();
            toast(`Seat ${data.booking.seat_id} booked for ${data.booking.name}`);
        } else if (data.status === 'gender_conflict') {
            // Shouldn't normally hit this since we set confirm flag, but handle anyway
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

// ----- Cancel booking -----
document.getElementById('cancelBookingBtn').addEventListener('click', async () => {
    if (!currentBookingId) return;
    if (!confirm('Cancel this booking? This cannot be undone.')) return;

    try {
        const res = await fetch(`/staff/booking/${currentBookingId}/cancel`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value,
            }
        });
        const data = await res.json();

        if (data.status === 'success') {
            const seat = document.querySelector(`.seat[data-seat="${data.seat_id}"]`);
            seat.classList.remove('booked-m', 'booked-f');
            seat.title = `Seat ${data.seat_id}`;

            const oc = document.getElementById('occupancyCount');
            oc.textContent = parseInt(oc.textContent) - 1;

            closePanel();
            toast(`Booking cancelled`);
        }
    } catch (err) {
        console.error('Cancel failed:', err);
        alert('Could not cancel booking.');
    }
});

// ----- Toast notification -----
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