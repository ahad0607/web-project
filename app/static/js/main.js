document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts after 5 seconds
  setTimeout(() => {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
      const bsAlert = new bootstrap.Alert(alert);
      bsAlert.close();
    });
  }, 5000);

  // Confirmation on delete buttons
  const deleteForms = document.querySelectorAll('form[action*="/delete"]');
  deleteForms.forEach(form => {
    form.addEventListener('submit', (e) => {
      if (!confirm('Are you sure you want to perform this soft delete? The item will be marked inactive.')) {
        e.preventDefault();
      }
    });
  });
});
