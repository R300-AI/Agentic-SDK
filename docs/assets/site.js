const toggle = document.querySelector('[data-mobile-nav-toggle]');
const sidebar = document.querySelector('.sidebar');

if (toggle && sidebar) {
  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
}
