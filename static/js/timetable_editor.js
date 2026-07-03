(function () {
    "use strict";

    const config = document.getElementById("timetableEditorConfig");
    const grid = document.getElementById("timetableGrid");

    if (!config || !grid) {
        return;
    }

    const moveUrl = config.dataset.moveUrl;
    const unlockUrl = config.dataset.unlockUrl;
    const selectedRoomId = config.dataset.selectedRoomId || "";
    let draggedCard = null;
    let originalCell = null;

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split(";") : [];
        for (const cookie of cookies) {
            const trimmed = cookie.trim();
            if (trimmed.startsWith(name + "=")) {
                return decodeURIComponent(trimmed.substring(name.length + 1));
            }
        }
        return "";
    }

    function showToast(message, variant) {
        const container = document.getElementById("timetableToastContainer");
        if (!container) {
            window.alert(message);
            return;
        }

        const toastEl = document.createElement("div");
        toastEl.className = "toast align-items-center text-bg-" + variant + " border-0";
        toastEl.setAttribute("role", "alert");
        toastEl.setAttribute("aria-live", "assertive");
        toastEl.setAttribute("aria-atomic", "true");
        toastEl.innerHTML = [
            '<div class="d-flex">',
            '<div class="toast-body"></div>',
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>',
            '</div>'
        ].join("");
        toastEl.querySelector(".toast-body").textContent = message;
        container.appendChild(toastEl);

        if (window.bootstrap && window.bootstrap.Toast) {
            const toast = new window.bootstrap.Toast(toastEl, { delay: 5000 });
            toast.show();
            toastEl.addEventListener("hidden.bs.toast", function () {
                toastEl.remove();
            });
        } else {
            setTimeout(function () {
                toastEl.remove();
            }, 5000);
        }
    }

    function moveCardBack() {
        if (draggedCard && originalCell) {
            originalCell.appendChild(draggedCard);
        }
    }

    function setCardLocked(card, locked) {
        card.classList.toggle("is-locked", locked);
        let header = card.querySelector(".activity-card-header");
        if (!header) {
            header = document.createElement("div");
            header.className = "activity-card-header";
            card.prepend(header);
        }

        header.innerHTML = "";
        if (locked) {
            const indicator = document.createElement("span");
            indicator.className = "lock-indicator";
            indicator.title = "Locked manual placement";
            indicator.innerHTML = '<i class="bi bi-lock-fill"></i>';
            header.appendChild(indicator);

            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-link btn-sm unlock-slot-button";
            button.dataset.slotId = card.dataset.slotId;
            button.title = "Unlock slot";
            button.setAttribute("aria-label", "Unlock slot");
            button.innerHTML = '<i class="bi bi-unlock"></i>';
            header.appendChild(button);
        }
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: JSON.stringify(payload)
        });

        let data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }

        if (!response.ok || data.ok === false) {
            throw new Error(data.error || "The timetable update failed.");
        }
        return data;
    }

    grid.addEventListener("dragstart", function (event) {
        const card = event.target.closest(".activity-card");
        if (!card) {
            return;
        }

        draggedCard = card;
        originalCell = card.closest(".timetable-drop-zone");
        card.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.slotId);
    });

    grid.addEventListener("dragend", function () {
        if (draggedCard) {
            draggedCard.classList.remove("is-dragging");
        }
        grid.querySelectorAll(".drop-zone-active").forEach(function (cell) {
            cell.classList.remove("drop-zone-active");
        });
        draggedCard = null;
        originalCell = null;
    });

    grid.addEventListener("dragover", function (event) {
        const cell = event.target.closest(".timetable-drop-zone");
        if (!cell || !draggedCard) {
            return;
        }
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        cell.classList.add("drop-zone-active");
    });

    grid.addEventListener("dragleave", function (event) {
        const cell = event.target.closest(".timetable-drop-zone");
        if (cell && !cell.contains(event.relatedTarget)) {
            cell.classList.remove("drop-zone-active");
        }
    });

    grid.addEventListener("drop", async function (event) {
        const cell = event.target.closest(".timetable-drop-zone");
        if (!cell || !draggedCard) {
            return;
        }

        event.preventDefault();
        cell.classList.remove("drop-zone-active");

        const roomId = cell.dataset.roomId || selectedRoomId || draggedCard.dataset.roomId;
        if (!roomId) {
            showToast("Choose a room-specific grid before moving this slot.", "warning");
            moveCardBack();
            return;
        }

        const card = draggedCard;
        cell.appendChild(card);

        try {
            const data = await postJson(moveUrl, {
                slot_id: card.dataset.slotId,
                target_day: Number(cell.dataset.day),
                target_period: Number(cell.dataset.period),
                target_room: Number(roomId)
            });
            card.dataset.roomId = String(data.target_room);
            card.dataset.originalCell = cell.id;
            setCardLocked(card, true);
            showToast("Slot moved and locked.", "success");
        } catch (error) {
            moveCardBack();
            showToast(error.message || "Could not move this slot.", "danger");
        }
    });

    grid.addEventListener("click", async function (event) {
        const button = event.target.closest(".unlock-slot-button");
        if (!button) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        const card = button.closest(".activity-card");
        try {
            await postJson(unlockUrl, { slot_id: button.dataset.slotId });
            if (card) {
                setCardLocked(card, false);
            }
            showToast("Slot unlocked for future regeneration.", "success");
        } catch (error) {
            showToast(error.message || "Could not unlock this slot.", "danger");
        }
    });

    if (!("draggable" in document.createElement("span"))) {
        showToast("This browser does not support drag-and-drop editing.", "warning");
    }
})();
