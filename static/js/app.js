/* ═══════════════════════════════════════════════════════
   TAXI GAB+ BDC — JavaScript principal
   ═══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function() {

  // ── AUTO-DISMISS ALERTS ──────────────────────────────
  const alerts = document.querySelectorAll('.alert.alert-dismissible');
  alerts.forEach(function(alert) {
    setTimeout(function() {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  // ── SIDEBAR TOGGLE (MOBILE) ──────────────────────────
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar   = document.getElementById('sidebar');
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', function() {
      sidebar.classList.toggle('open');
    });
    // Fermer en cliquant en dehors
    document.addEventListener('click', function(e) {
      if (sidebar.classList.contains('open') &&
          !sidebar.contains(e.target) &&
          e.target !== toggleBtn) {
        sidebar.classList.remove('open');
      }
    });
  }

  // ── CONFIRMATION BEFORE FORM SUBMIT ─────────────────
  document.querySelectorAll('[data-confirm]').forEach(function(el) {
    el.addEventListener('submit', function(e) {
      if (!confirm(el.dataset.confirm)) {
        e.preventDefault();
      }
    });
  });

  // ── TOOLTIPS BOOTSTRAP ───────────────────────────────
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipTriggerList.forEach(function(el) {
    new bootstrap.Tooltip(el);
  });

  // ── RÉCEPTION : Auto-fill qté reçue ─────────────────
  document.querySelectorAll('select[name="statut_reception"]').forEach(function(sel) {
    sel.addEventListener('change', function() {
      const row  = this.closest('.reception-ligne') || this.closest('form');
      const qteInput = row ? row.querySelector('input[name="quantite_recue"]') : null;
      const maxQte = qteInput ? parseInt(qteInput.max) : 0;
      if (this.value === 'recu' && qteInput) {
        qteInput.value = maxQte;
      } else if (this.value === 'non_recu' && qteInput) {
        qteInput.value = 0;
      }
    });
  });

  // ── FILTRES : Soumettre avec ENTRÉE ─────────────────
  document.querySelectorAll('#filter-form input').forEach(function(input) {
    input.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        this.closest('form').submit();
      }
    });
  });

  // ── PRINT SHORTCUT ───────────────────────────────────
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
      // Laisser le comportement par défaut du navigateur
    }
  });

});

// ── FONCTION GLOBALE : Afficher/masquer mot de passe ──
function togglePassword() {
  const field = document.getElementById('password-field');
  const eye   = document.getElementById('pw-eye');
  if (!field) return;
  if (field.type === 'password') {
    field.type = 'text';
    if (eye) eye.classList.replace('bi-eye', 'bi-eye-slash');
  } else {
    field.type = 'password';
    if (eye) eye.classList.replace('bi-eye-slash', 'bi-eye');
  }
}
