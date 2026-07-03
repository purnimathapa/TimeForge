document.addEventListener("DOMContentLoaded", function() {
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
    
    sidebarLinks.forEach(link => {
        // If href matches current path and isn't just '#'
        if (link.getAttribute('href') !== '#' && link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
});
