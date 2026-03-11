const marquee = document.getElementById('marquee');
const sectionsEl = document.getElementById('sections');
const statusEl = document.getElementById('status');

let sections = [];
let allMessages = [];  // flattened for marquee scroll
let currentIndex = 0;
let idleMessage = 'Loading...';

async function fetchMessages() {
    try {
        const resp = await fetch('/api/messages');
        const data = await resp.json();
        sections = data.sections || [];
        idleMessage = data.idle_message || 'No data yet...';

        // Flatten all section messages for marquee scrolling
        allMessages = [];
        sections.forEach(s => {
            s.messages.forEach(m => allMessages.push(m));
        });

        renderSections();
        updateStatus();
    } catch (e) {
        console.error('Failed to fetch messages:', e);
    }
}

function updateMarquee() {
    if (allMessages.length === 0) {
        marquee.textContent = idleMessage;
        setScrollDuration(idleMessage.length);
        return;
    }

    currentIndex = currentIndex % allMessages.length;
    const text = allMessages[currentIndex];
    marquee.textContent = text;
    setScrollDuration(text.length);
    currentIndex++;
}

function setScrollDuration(textLength) {
    const duration = Math.max(textLength / 8, 4);
    marquee.style.animationDuration = duration + 's';
}

function renderSections() {
    if (sections.length === 0 || allMessages.length === 0) {
        sectionsEl.innerHTML = '<div class="idle">' + idleMessage + '</div>';
        return;
    }

    let html = '';
    sections.forEach(section => {
        if (section.messages.length === 0) return;

        html += '<div class="section">';
        html += '<div class="section-title">' + escapeHtml(section.display_name).toUpperCase() + '</div>';
        section.messages.forEach((msg, i) => {
            html += '<div class="section-item">';
            html += '<span class="index">' + (i + 1) + '.</span>';
            html += '<span>' + escapeHtml(msg) + '</span>';
            html += '</div>';
        });
        html += '</div>';
    });

    sectionsEl.innerHTML = html;
}

function updateStatus() {
    const total = allMessages.length;
    if (total === 0) {
        statusEl.textContent = '';
    } else {
        const parts = [];
        sections.forEach(s => {
            if (s.messages.length > 0) {
                parts.push(s.messages.length + ' ' + s.display_name.toLowerCase());
            }
        });
        statusEl.textContent = parts.join(' / ');
    }
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

// Poll API every 5 seconds
fetchMessages();
setInterval(fetchMessages, 5000);

// Cycle marquee text when animation ends
marquee.addEventListener('animationiteration', updateMarquee);

// Initial marquee setup
updateMarquee();
