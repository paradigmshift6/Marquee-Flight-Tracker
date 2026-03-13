(function () {
    "use strict";

    var MASK = "********";
    var form = document.getElementById("settings-form");
    var statusBar = document.getElementById("status-bar");
    var btnSave = document.getElementById("btn-save");
    var btnRestart = document.getElementById("btn-restart");
    var brightnessValue = document.getElementById("brightness-value");

    // ---- Load settings from API ----

    function loadSettings() {
        fetch("/api/settings")
            .then(function (resp) {
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                return resp.json();
            })
            .then(function (data) {
                populateForm(data);
            })
            .catch(function (e) {
                showStatus("Failed to load settings: " + e.message, "error");
            });
    }

    function populateForm(data) {
        var inputs = form.querySelectorAll("[data-section][data-key]");
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            var section = input.getAttribute("data-section");
            var key = input.getAttribute("data-key");
            var sectionData = data[section];
            if (!sectionData) continue;
            var value = sectionData[key];
            if (value === undefined || value === null) {
                value = "";
            }

            if (input.type === "checkbox") {
                input.checked = !!value;
            } else if (input.type === "password" && input.getAttribute("data-sensitive")) {
                input.value = value === MASK ? "" : value;
                input.placeholder = value === MASK ? "configured (hidden)" : "not set";
                input.setAttribute("data-original", value);
            } else if (input.tagName === "SELECT") {
                input.value = value;
            } else {
                input.value = value;
            }
        }

        // Update brightness display
        var bInput = document.getElementById("renderer-brightness");
        if (bInput && brightnessValue) {
            brightnessValue.textContent = bInput.value;
        }
    }

    // ---- Collect form values ----

    function collectForm() {
        var result = {};
        var inputs = form.querySelectorAll("[data-section][data-key]");
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            var section = input.getAttribute("data-section");
            var key = input.getAttribute("data-key");

            if (!result[section]) result[section] = {};

            if (input.type === "checkbox") {
                result[section][key] = input.checked;
            } else if (input.type === "number" || input.type === "range") {
                var num = parseFloat(input.value);
                result[section][key] = isNaN(num) ? input.value : num;
            } else if (input.type === "password" && input.getAttribute("data-sensitive")) {
                // If user didn't change a sensitive field, send back the mask
                var original = input.getAttribute("data-original");
                if (input.value === "" && original === MASK) {
                    result[section][key] = MASK;
                } else {
                    result[section][key] = input.value;
                }
            } else {
                result[section][key] = input.value;
            }
        }
        return result;
    }

    // ---- Validate ----

    function validate(data) {
        var errors = [];
        var lat = (data.location || {}).latitude;
        var lon = (data.location || {}).longitude;
        if (lat === 0 && lon === 0) {
            errors.push("Set your latitude and longitude");
        }
        if ((data.weather || {}).enabled) {
            var apiKey = (data.weather || {}).api_key;
            if (!apiKey || apiKey === "" || apiKey === MASK) {
                // MASK means it's already configured, that's fine
                if (apiKey !== MASK) {
                    errors.push("Weather requires an API key");
                }
            }
        }
        return errors;
    }

    // ---- Save ----

    function saveSettings(restart) {
        var data = collectForm();

        var errors = validate(data);
        if (errors.length > 0) {
            showStatus(errors.join(". "), "error");
            return;
        }

        data._restart = !!restart;
        btnSave.disabled = true;
        btnRestart.disabled = true;

        fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(function (resp) {
                return resp.json().then(function (result) {
                    return { ok: resp.ok, result: result };
                });
            })
            .then(function (obj) {
                if (!obj.ok) {
                    var msg = obj.result.error || "Unknown error";
                    if (obj.result.details) msg += ": " + obj.result.details.join(", ");
                    showStatus(msg, "error");
                    return;
                }
                if (obj.result.restarting) {
                    showStatus("Settings saved. Restarting...", "success");
                    setTimeout(pollForRestart, 3000);
                } else {
                    showStatus("Settings saved. Restart required for changes to take effect.", "success");
                }
            })
            .catch(function (e) {
                showStatus("Failed to save: " + e.message, "error");
            })
            .finally(function () {
                btnSave.disabled = false;
                btnRestart.disabled = false;
            });
    }

    function pollForRestart() {
        fetch("/api/settings")
            .then(function (resp) {
                if (resp.ok) {
                    showStatus("Restarted! Reloading...", "success");
                    setTimeout(function () { window.location.reload(); }, 1000);
                } else {
                    setTimeout(pollForRestart, 2000);
                }
            })
            .catch(function () {
                setTimeout(pollForRestart, 2000);
            });
    }

    // ---- Status bar ----

    function showStatus(message, type) {
        statusBar.textContent = message;
        statusBar.className = "status-bar " + type;
    }

    // ---- Event listeners ----

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        saveSettings(false);
    });

    btnRestart.addEventListener("click", function () {
        saveSettings(true);
    });

    // Live brightness display
    var bInput = document.getElementById("renderer-brightness");
    if (bInput && brightnessValue) {
        bInput.addEventListener("input", function () {
            brightnessValue.textContent = bInput.value;
        });
    }

    // ---- Init ----
    loadSettings();
})();
