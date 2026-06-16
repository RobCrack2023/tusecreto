/* Portal Secreto — main.js */

// ── Navbar hamburger ──────────────────────────
const navToggle = document.getElementById('navToggle');
const navLinks  = document.getElementById('navLinks');
if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const open = navLinks.classList.toggle('open');
    navToggle.classList.toggle('open', open);
  });
  document.addEventListener('click', (e) => {
    if (!navToggle.contains(e.target) && !navLinks.contains(e.target)) {
      navLinks.classList.remove('open');
      navToggle.classList.remove('open');
    }
  });
}

// ── Auto-dismiss flash ────────────────────────
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity 0.4s, transform 0.4s';
    el.style.opacity    = '0';
    el.style.transform  = 'translateX(120%)';
    setTimeout(() => el.remove(), 400);
  }, 4000);
});

// ── Card entrance animation ───────────────────
if ('IntersectionObserver' in window) {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.style.animationPlayState = 'running';
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  document.querySelectorAll('.story-card').forEach(c => {
    c.style.animationPlayState = 'paused';
    obs.observe(c);
  });
}

// ── Lightbox ──────────────────────────────────
const lightbox    = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');
function openLightbox(src) {
  if (!lightbox) return;
  lightboxImg.src = src;
  lightbox.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeLightbox() {
  if (!lightbox) return;
  lightbox.classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
if (lightboxImg) lightboxImg.addEventListener('click', e => e.stopPropagation());

// ── Sticker Picker ────────────────────────────
const picker = document.getElementById('stickerPicker');
if (picker) {
  let activeStoryId   = null;
  let activeTrigger   = null;

  // Abrir/cerrar picker al pulsar el botón de reacción
  document.querySelectorAll('.react-trigger').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const storyId = btn.dataset.storyId;

      if (picker.classList.contains('open') && activeStoryId === storyId) {
        closePicker();
        return;
      }

      activeStoryId  = storyId;
      activeTrigger  = btn;

      // Marcar cuál sticker tiene el usuario ya
      const bar      = btn.closest('.reaction-bar');
      const mySticker = bar ? bar.dataset.mySticker : '';
      picker.querySelectorAll('.sp-btn').forEach(sb => {
        sb.classList.toggle('active', sb.dataset.stickerId === mySticker);
      });

      positionPicker(btn);
      picker.classList.add('open');
      btn.classList.add('active');
    });
  });

  // Reaccionar al elegir un sticker
  picker.querySelectorAll('.sp-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      if (!activeStoryId) return;

      const stickerId = btn.dataset.stickerId;
      closePicker();

      try {
        const resp = await fetch(`/api/react/${activeStoryId}/${stickerId}`, { method: 'POST' });
        const data = await resp.json();
        if (data.ok) {
          renderReactions(activeStoryId, data.reactions, data.removed ? null : data.my_sticker);
        }
      } catch { /* red error silencioso */ }
    });
  });

  // Cerrar al click fuera
  document.addEventListener('click', e => {
    if (!picker.contains(e.target)) closePicker();
  });

  // También cerrar con Escape
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closePicker(); });

  function closePicker() {
    picker.classList.remove('open');
    if (activeTrigger) activeTrigger.classList.remove('active');
    activeTrigger = null;
  }

  function positionPicker(btn) {
    picker.style.visibility = 'hidden';
    picker.style.display    = 'block';
    const pw  = picker.offsetWidth;
    const ph  = picker.offsetHeight;
    picker.style.display    = '';
    picker.style.visibility = '';

    const rect    = btn.getBoundingClientRect();
    const scrollY = window.scrollY;
    const vw      = window.innerWidth;

    let top  = rect.top + scrollY - ph - 10;
    let left = rect.left + rect.width / 2 - pw / 2;

    // No salir por la izquierda/derecha
    left = Math.max(8, Math.min(left, vw - pw - 8));

    // Si no cabe arriba, abre abajo
    if (top - scrollY < 8) top = rect.bottom + scrollY + 10;

    picker.style.top  = top  + 'px';
    picker.style.left = left + 'px';
  }

  // Renderizar barra de reacciones tras respuesta API
  function renderReactions(storyId, reactions, myStickerId) {
    const chips = document.getElementById(`chips-${storyId}`);
    const bar   = document.querySelector(`.reaction-bar[data-story-id="${storyId}"]`);
    if (!chips || !bar) return;

    // Actualizar dataset para próxima apertura del picker
    bar.dataset.mySticker = myStickerId || '';

    // Reconstruir chips
    chips.innerHTML = reactions.map(r => {
      const isMine = myStickerId && String(r.sticker_id) === String(myStickerId);
      const inner  = r.type === 'emoji'
        ? `<span class="s-emoji">${r.value}</span>`
        : `<img src="/stickers/${r.value}" alt="${r.name}" class="s-img">`;
      return `<span class="reaction-chip${isMine ? ' mine' : ''} popping"
                    data-sticker-id="${r.sticker_id}"
                    data-story-id="${storyId}">
                ${inner}
                <span class="r-count">${r.count}</span>
              </span>`;
    }).join('');

    // Quitar clase de animación tras terminar
    chips.querySelectorAll('.popping').forEach(el => {
      el.addEventListener('animationend', () => el.classList.remove('popping'), { once: true });
    });
  }
}
