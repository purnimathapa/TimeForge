(function () {
    "use strict";

    const config = document.getElementById("timetableEditorConfig");
    const grid = document.getElementById("timetableGrid");

    if (!config || !grid) {
        return;
    }

    const timetableId = Number(config.dataset.timetableId);
    const unlockUrl = config.dataset.unlockUrl;
    const validateBatchUrl = config.dataset.validateBatchUrl;
    const publishUrl = config.dataset.publishUrl;
    const discardUrl = config.dataset.discardUrl;
    const selectedRoomId = config.dataset.selectedRoomId || "";

    const checkBtn = document.getElementById("checkChangesBtn");
    const publishBtn = document.getElementById("publishChangesBtn");
    const discardBtn = document.getElementById("discardChangesBtn");
    const pendingSummary = document.getElementById("pendingMoveSummary");
    const validationResults = document.getElementById("batchValidationResults");
    const penaltyBadge = document.getElementById("timetablePenaltyBadge");

    let pendingMoves = {};
    let changeSetId = null;
    let lastCheckValid = false;
    let dirtySinceCheck = false;

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

    function pendingCount() {
        return Object.keys(pendingMoves).length;
    }

    function resolveRoomId(cell, card) {
        return cell.dataset.roomId || selectedRoomId || card.dataset.roomId;
    }

    function isCommittedPosition(card, cell, roomId) {
        return cell.id === card.dataset.originalCell && String(roomId) === String(card.dataset.roomId);
    }

    function setCardPending(card, pending) {
        card.classList.toggle("is-pending", pending);
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

    function invalidateCheckState() {
        lastCheckValid = false;
        dirtySinceCheck = true;
        changeSetId = null;
        updateToolbarState();
    }

    function updateToolbarState() {
        const count = pendingCount();
        if (pendingSummary) {
            pendingSummary.textContent = count
                ? count + " staged move" + (count === 1 ? "" : "s") + "."
                : "No staged moves.";
        }
        if (checkBtn) {
            checkBtn.disabled = count === 0;
        }
        if (publishBtn) {
            publishBtn.disabled = !(lastCheckValid && !dirtySinceCheck && changeSetId);
        }
        if (discardBtn) {
            discardBtn.disabled = count === 0 && !changeSetId;
        }
    }

    function showValidationResults(isValid, violations, penaltyScore) {
        if (!validationResults) {
            return;
        }

        validationResults.classList.remove("d-none", "is-valid", "is-invalid");
        if (isValid) {
            validationResults.classList.add("is-valid");
            validationResults.innerHTML = "<strong>Batch check passed.</strong> Penalty score: " + penaltyScore + ".";
        } else {
            validationResults.classList.add("is-invalid");
            const items = violations.map(function (violation) {
                return "<li>" + violation + "</li>";
            }).join("");
            validationResults.innerHTML = "<strong>Conflicts found.</strong><ul>" + items + "</ul>";
        }
    }

    function clearValidationResults() {
        if (!validationResults) {
            return;
        }
        validationResults.classList.add("d-none");
        validationResults.classList.remove("is-valid", "is-invalid");
        validationResults.innerHTML = "";
    }

    function updatePenaltyBadge(penaltyScore) {
        if (!penaltyBadge) {
            return;
        }
        if (penaltyScore === 0) {
            penaltyBadge.className = "badge bg-success";
            penaltyBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i>No Conflicts';
        } else {
            penaltyBadge.className = "badge bg-warning text-dark";
            penaltyBadge.innerHTML = '<i class="bi bi-exclamation-triangle me-1"></i>Penalty: ' + penaltyScore;
        }
    }

    function stageMove(card, cell, roomId) {
        const slotId = card.dataset.slotId;
        if (isCommittedPosition(card, cell, roomId)) {
            delete pendingMoves[slotId];
            setCardPending(card, false);
        } else {
            pendingMoves[slotId] = {
                slot_id: Number(slotId),
                target_day: Number(cell.dataset.day),
                target_period: Number(cell.dataset.period),
                target_room: Number(roomId),
                target_cell_id: cell.id
            };
            setCardPending(card, true);
        }
        invalidateCheckState();
        clearValidationResults();
        updateToolbarState();
    }

    function revertAllPendingMoves() {
        Object.keys(pendingMoves).forEach(function (slotId) {
            const card = grid.querySelector('.activity-card[data-slot-id="' + slotId + '"]');
            if (!card) {
                return;
            }
            const originalCell = document.getElementById(card.dataset.originalCell);
            if (originalCell) {
                originalCell.appendChild(card);
            }
            setCardPending(card, false);
        });
        pendingMoves = {};
        lastCheckValid = false;
        dirtySinceCheck = false;
        changeSetId = null;
        clearValidationResults();
        updateToolbarState();
    }

    const DAY_NAMES = {
        1: "Monday",
        2: "Tuesday",
        3: "Wednesday",
        4: "Thursday",
        5: "Friday",
        6: "Saturday",
        7: "Sunday"
    };

    function revertCard(card) {
        const originalCell = document.getElementById(card.dataset.originalCell);
        if (originalCell) {
            originalCell.appendChild(card);
        }
    }

    function describeMove(card, cell) {
        const subjectEl = card.querySelector(".activity-subject");
        const subject = subjectEl ? subjectEl.textContent.trim() : "this class";
        const dayName = DAY_NAMES[Number(cell.dataset.day)] || ("Day " + cell.dataset.day);
        const periodLabel = cell.dataset.periodLabel || ("Period " + cell.dataset.period);
        return { subject: subject, dayName: dayName, periodLabel: periodLabel };
    }

    function handleSortableEnd(evt) {
        const card = evt.item;
        const cell = evt.to;
        if (!card || !cell || !cell.classList.contains("timetable-drop-zone")) {
            return;
        }

        // Dropped back where it started, nothing to confirm.
        if (evt.to === evt.from) {
            return;
        }

        const roomId = resolveRoomId(cell, card);
        if (!roomId) {
            showToast("Choose a room-specific grid before moving this slot.", "warning");
            revertCard(card);
            return;
        }

        const info = describeMove(card, cell);
        const confirmed = window.confirm(
            "Move " + info.subject + " to " + info.dayName + ", " + info.periodLabel + "?\n\n"
            + "The move will be staged so you can review conflicts, then Publish to apply it."
        );

        if (!confirmed) {
            revertCard(card);
            showToast("Move cancelled. The class was left in its original slot.", "secondary");
            return;
        }

        stageMove(card, cell, roomId);
    }

    async function checkChanges() {
        const moves = Object.values(pendingMoves);
        try {
            const data = await postJson(validateBatchUrl, {
                timetable_id: timetableId,
                moves: moves
            });
            changeSetId = data.change_set_id;
            lastCheckValid = data.is_valid;
            dirtySinceCheck = false;
            showValidationResults(data.is_valid, data.violations || [], data.penalty_score);
            if (data.is_valid) {
                showToast("Batch check passed. You can publish these moves.", "success");
            } else {
                showToast("Batch check found conflicts. Review the list and adjust moves.", "danger");
            }
            updateToolbarState();
        } catch (error) {
            showToast(error.message || "Could not validate staged moves.", "danger");
        }
    }

    async function publishChanges() {
        if (!changeSetId || !lastCheckValid || dirtySinceCheck) {
            showToast("Run Check Changes before publishing.", "warning");
            return;
        }

        try {
            const data = await postJson(publishUrl, { change_set_id: changeSetId });
            Object.keys(pendingMoves).forEach(function (slotId) {
                const card = grid.querySelector('.activity-card[data-slot-id="' + slotId + '"]');
                const move = pendingMoves[slotId];
                if (!card || !move) {
                    return;
                }
                card.dataset.originalCell = move.target_cell_id;
                card.dataset.roomId = String(move.target_room);
                setCardPending(card, false);
                setCardLocked(card, true);
            });
            pendingMoves = {};
            changeSetId = null;
            lastCheckValid = false;
            dirtySinceCheck = false;
            clearValidationResults();
            updatePenaltyBadge(data.penalty_score);
            updateToolbarState();
            showToast("Staged moves published and locked.", "success");
        } catch (error) {
            showToast(error.message || "Could not publish staged moves.", "danger");
        }
    }

    async function discardChanges() {
        const discardId = changeSetId;
        revertAllPendingMoves();
        if (discardId) {
            try {
                await postJson(discardUrl, { change_set_id: discardId });
            } catch (error) {
                showToast(error.message || "Could not discard the draft change set.", "warning");
            }
        }
        updateToolbarState();
        showToast("Staged moves discarded.", "secondary");
    }

    function initSortable() {
        if (!window.Sortable) {
            showToast("SortableJS failed to load. Drag-and-drop editing is unavailable.", "danger");
            return;
        }

        grid.querySelectorAll(".timetable-drop-zone").forEach(function (cell) {
            Sortable.create(cell, {
                group: "timetable-slots",
                animation: 150,
                draggable: ".activity-card",
                ghostClass: "sortable-ghost",
                chosenClass: "sortable-chosen",
                delay: 100,
                delayOnTouchOnly: true,
                touchStartThreshold: 3,
                onEnd: handleSortableEnd
            });
        });
    }

    if (checkBtn) {
        checkBtn.addEventListener("click", checkChanges);
    }
    if (publishBtn) {
        publishBtn.addEventListener("click", publishChanges);
    }
    if (discardBtn) {
        discardBtn.addEventListener("click", discardChanges);
    }

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

    initSortable();
    updateToolbarState();
})();
