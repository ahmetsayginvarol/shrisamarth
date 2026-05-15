// ============================================================
// SHRISAMARTH Customer Booking — seat selection + real-time
// ============================================================

const bookApp = document.getElementById('bookApp');
const VOYAGE_ID = parseInt(bookApp.dataset.voyageId);
const BASE_FARE = parseFloat(bookApp.dataset.baseFare);
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;

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
                alert('This seat was just booked. Please choose another.');
                const el = document.querySelector(`.seat[data-seat="${sid}"]`);
                if (el) {
                    el.classList.add('booked-m');  // generic placeholder until refresh
                    el.title = 'Booked';
                }
            } else if (d.error === 'locked_by_other') {
                alert('Another passenger is reserving this seat. Please choose another.');
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

function updateSelectionUI() {
    const count = selectedSeats.size;
    const totalFare = count * BASE_FARE;

    const panelEmpty = document.getElementById('panel-empty');
    const panelSelected = document.getElementById('panel-selected');
    const panelForm = document.getElementById('panel-form');

    if (count > 0) {
        panelEmpty.classList.add('hidden');
        panelSelected.classList.remove('hidden');
        panelForm.classList.add('hidden');

        document.getElementById('selectedSeatsList').textContent =
            Array.from(selectedSeats).sort().join(', ');
        document.getElementById('totalFareDisplay').textContent =
            '₹ ' + totalFare.toLocaleString('en-IN');
        document.getElementById('seatCountDisplay').textContent =
            `${count} seat${count !== 1 ? 's' : ''}`;
    } else {
        panelEmpty.classList.remove('hidden');
        panelSelected.classList.add('hidden');
        panelForm.classList.add('hidden');
    }
}

function showBookingForm() {
    document.getElementById('panel-empty').classList.add('hidden');
    document.getElementById('panel-selected').classList.add('hidden');
    document.getElementById('panel-form').classList.remove('hidden');

    // Inject seat_ids hidden inputs
    const container = document.getElementById('seatInputsContainer');
    container.innerHTML = '';
    Array.from(selectedSeats).sort().forEach(sid => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'seat_ids[]';
        inp.value = sid;
        container.appendChild(inp);
    });

    document.getElementById('formSeatSummary').textContent =
        Array.from(selectedSeats).sort().join(', ');
    document.getElementById('formFareSummary').textContent =
        '₹ ' + (selectedSeats.size * BASE_FARE).toLocaleString('en-IN');
}

function cancelForm() {
    updateSelectionUI();
}

// ============================================================
// BOOKING FORM SUBMIT
// ============================================================

const bookingForm = document.getElementById('customerBookingForm');
if (bookingForm) {
    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = bookingForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Confirming…';

        try {
            const formData = new FormData(bookingForm);
            const res = await fetch('/api/customer/book', {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN },
                body: formData,
            });
            const data = await res.json();

            if (data.status === 'success') {
                window.location.href = `/booking/confirmation/${data.code}`;
            } else {
                alert('Booking failed: ' + (data.message || 'Unknown error'));
                submitBtn.disabled = false;
                submitBtn.textContent = 'Confirm Booking';
            }
        } catch (err) {
            alert('Booking failed. Please try again.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirm Booking';
        }
    });
}

// ============================================================
// SOCKET.IO REAL-TIME UPDATES
// ============================================================

const socket = io();

socket.on('seat_locked', (data) => {
    if (parseInt(data.voyage_id) !== VOYAGE_ID) return;
    const sid = data.seat_id;
    if (myLockedSeats.has(sid)) return;  // it's ours
    const el = document.querySelector(`.seat[data-seat="${sid}"]`);
    if (el && !el.classList.contains('booked-m') && !el.classList.contains('booked-f')) {
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
        el.classList.add('booked-' + data.gender.toLowerCase());
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
