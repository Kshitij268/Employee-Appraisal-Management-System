/**
 * Employee Appraisal Management System (EAMS)
 * Client-side Utilities & Password Strength Evaluation
 */

// ============================================================
// API REQUEST HELPER
// ============================================================

async function apiRequest(url, method = "GET", data = null) {
    const options = {
        method: method,
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    };

    if (data && (method === "POST" || method === "PUT" || method === "PATCH")) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);
        const result = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(result.message || `Request failed with status ${response.status}`);
        }

        return result;
    } catch (error) {
        console.error("API Request Error:", error);
        throw error;
    }
}

// ============================================================
// PASSWORD STRENGTH EVALUATOR
// ============================================================

function evaluatePasswordStrength(password) {
    if (!password || password.length === 0) {
        return { label: "", className: "" };
    }

    let score = 0;

    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[a-z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;

    if (score < 3 || password.length < 8) {
        return { label: "Weak", className: "strength-weak" };
    } else if (score < 5) {
        return { label: "Medium", className: "strength-medium" };
    } else {
        return { label: "Strong", className: "strength-strong" };
    }
}

function bindPasswordStrength(inputId, labelId) {
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);
    if (!input || !label) return;

    input.addEventListener("input", function () {
        const val = input.value;
        const res = evaluatePasswordStrength(val);
        label.textContent = res.label ? `Strength: ${res.label}` : "";
        label.className = `strength-label ${res.className}`;
    });
}

// ============================================================
// MODAL CONTROLS
// ============================================================

function openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.add("open");
    }
}

function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.remove("open");
    }
}

// Close modal when clicking on overlay background
document.addEventListener("click", function (e) {
    if (e.target && e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("open");
    }
});

// ============================================================
// TOAST ALERTS
// ============================================================

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) {
        alert(message);
        return;
    }

    const alertBox = document.createElement("div");
    alertBox.className = `alert alert-${type === "error" ? "danger" : type}`;
    alertBox.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;font-size:1.1rem;color:inherit;">&times;</button>
    `;

    container.prepend(alertBox);
    setTimeout(() => {
        if (alertBox.parentElement) {
            alertBox.remove();
        }
    }, 5000);
}

// ============================================================
// QUICK LOGIN HELPER
// ============================================================

function fillLogin(email, password) {
    const emailInput = document.getElementById("loginEmail");
    const pwdInput = document.getElementById("loginPassword");
    if (emailInput && pwdInput) {
        emailInput.value = email;
        pwdInput.value = password;
    }
}

// ============================================================
// MOBILE NAVIGATION TOGGLE
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("mobileToggle");
    const sidebar = document.getElementById("sidebar");

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }
});
