document.addEventListener("DOMContentLoaded", function() {
    // Render Lucide icons (<i data-lucide="name"></i>)
    if (window.lucide && typeof window.lucide.createIcons === "function") {
        window.lucide.createIcons();
    }

    // Sidebar toggle logic for mobile
    const sidebarToggle = document.getElementById("sidebarToggle");
    const mainSidebar = document.getElementById("mainSidebar");

    if (sidebarToggle && mainSidebar) {
        sidebarToggle.addEventListener("click", function(e) {
            e.stopPropagation();
            mainSidebar.classList.toggle("show");
            mainSidebar.classList.toggle("d-none");
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener("click", function(e) {
        if (window.innerWidth < 768 && mainSidebar && mainSidebar.classList.contains("show")) {
            if (!mainSidebar.contains(e.target) && e.target !== sidebarToggle) {
                mainSidebar.classList.remove("show");
                mainSidebar.classList.add("d-none");
            }
        }
    });

    // Handle active state highlighting for sidebar links
    const currentPath = window.location.pathname;
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    let bestMatch = null;

    sidebarLinks.forEach(link => {
        link.classList.remove('active');
        const href = link.getAttribute('href');
        if (!href || href === '#') return;
        if (href === currentPath) {
            bestMatch = link;
        } else if (currentPath.startsWith(href) && href !== '/') {
            // Prefer the longest prefix match (most specific section)
            if (!bestMatch || href.length > bestMatch.getAttribute('href').length) {
                if (bestMatch === null || bestMatch.getAttribute('href') !== currentPath) {
                    bestMatch = link;
                }
            }
        }
    });
    if (bestMatch) bestMatch.classList.add('active');

    // Show a loading spinner on submit buttons inside data-loading-form forms
    document.querySelectorAll('[data-loading-form]').forEach(form => {
        form.addEventListener('submit', function () {
            const btn = form.querySelector('[data-loading-btn]');
            if (btn) {
                btn.classList.add('is-loading');
                btn.disabled = true;
            }
        });
    });

    // Confirm before logging out (sidebar + settings; optional elsewhere)
    document.querySelectorAll("[data-logout-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!window.confirm("Are you sure you want to log out?")) {
                event.preventDefault();
            }
        });
    });

    // Top-right user menu (custom toggle; independent of Bootstrap dropdown)
    const userMenu = document.getElementById("userMenu");
    const userMenuToggle = document.getElementById("userMenuToggle");
    const userMenuPanel = document.getElementById("userMenuPanel");

    function closeUserMenu() {
        if (!userMenu || !userMenuToggle || !userMenuPanel) return;
        userMenu.classList.remove("is-open");
        userMenuPanel.hidden = true;
        userMenuToggle.setAttribute("aria-expanded", "false");
    }

    function openUserMenu() {
        if (!userMenu || !userMenuToggle || !userMenuPanel) return;
        userMenu.classList.add("is-open");
        userMenuPanel.hidden = false;
        userMenuToggle.setAttribute("aria-expanded", "true");
    }

    if (userMenu && userMenuToggle && userMenuPanel) {
        userMenuToggle.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            if (userMenuPanel.hidden) {
                openUserMenu();
            } else {
                closeUserMenu();
            }
        });

        document.addEventListener("click", function (event) {
            if (!userMenu.contains(event.target)) {
                closeUserMenu();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeUserMenu();
            }
        });
    }
});
