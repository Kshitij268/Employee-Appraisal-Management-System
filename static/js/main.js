/**
 * Employee Appraisal Management System (EAMS)
 * Client-side Suite: UI Animations, Dark Theme Visualizations, Nano Loading Bar & Utilities
 */

// ============================================================
// TOP NANO LOADING BAR
// ============================================================

const LoadingBar = {
    el: null,
    timer: null,

    init() {
        this.el = document.getElementById("topLoadingBar");
        if (!this.el) {
            this.el = document.createElement("div");
            this.el.id = "topLoadingBar";
            this.el.className = "top-loading-bar";
            document.body.prepend(this.el);
        }
        this.start();
    },

    start() {
        if (!this.el) return;
        clearTimeout(this.timer);
        this.el.style.opacity = "1";
        this.el.style.width = "25%";
        this.el.classList.add("active");

        this.timer = setTimeout(() => {
            if (this.el) this.el.style.width = "75%";
        }, 150);
    },

    finish() {
        if (!this.el) return;
        clearTimeout(this.timer);
        this.el.style.width = "100%";
        this.timer = setTimeout(() => {
            if (this.el) {
                this.el.style.opacity = "0";
                this.el.classList.remove("active");
                setTimeout(() => {
                    if (this.el) this.el.style.width = "0%";
                }, 400);
            }
        }, 250);
    }
};

// Initialize loading bar immediately
LoadingBar.init();

window.addEventListener("DOMContentLoaded", () => {
    LoadingBar.finish();
});

// Attach loading bar to page navigations and form submits
document.addEventListener("click", (e) => {
    const link = e.target.closest("a");
    if (link && link.href && !link.target && !link.href.startsWith("javascript:") && !link.href.includes("#")) {
        const url = new URL(link.href, window.location.origin);
        if (url.origin === window.location.origin) {
            LoadingBar.start();
        }
    }
});

document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form && !form.dataset.noProgress) {
        LoadingBar.start();
    }
});

// ============================================================
// CHART.JS DARK THEME GLOBAL CONFIGURATION
// ============================================================

if (typeof Chart !== "undefined") {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.font.family = "'Plus Jakarta Sans', Inter, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(16, 21, 34, 0.95)";
    Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
    Chart.defaults.plugins.tooltip.bodyColor = "#cbd5e1";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(255, 255, 255, 0.12)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.boxPadding = 6;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.pointStyle = "circle";
    Chart.defaults.plugins.legend.labels.padding = 16;
}

// ============================================================
// API REQUEST HELPER
// ============================================================

async function apiRequest(url, method = "GET", data = null) {
    LoadingBar.start();
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

        LoadingBar.finish();
        return result;
    } catch (error) {
        LoadingBar.finish();
        console.error("API Request Error:", error);
        throw error;
    }
}

// ============================================================
// PASSWORD STRENGTH EVALUATOR WITH ANIMATED METER
// ============================================================

function evaluatePasswordStrength(password) {
    if (!password || password.length === 0) {
        return { label: "", className: "", percent: 0, color: "#64748b" };
    }

    let score = 0;
    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[a-z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;

    if (score < 3 || password.length < 8) {
        return { label: "Weak", className: "strength-weak", percent: 30, color: "#f43f5e" };
    } else if (score < 5) {
        return { label: "Medium", className: "strength-medium", percent: 65, color: "#f59e0b" };
    } else {
        return { label: "Strong", className: "strength-strong", percent: 100, color: "#10b981" };
    }
}

function bindPasswordStrength(inputId, labelId, barId = null) {
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);
    if (!input || !label) return;

    let bar = barId ? document.getElementById(barId) : null;
    if (!bar) {
        const parent = label.parentElement;
        if (parent && !parent.querySelector(".password-strength-bar")) {
            const barContainer = document.createElement("div");
            barContainer.className = "password-strength-bar";
            bar = document.createElement("div");
            bar.className = "password-strength-bar-fill";
            barContainer.appendChild(bar);
            parent.insertBefore(barContainer, label);
        }
    }

    input.addEventListener("input", function () {
        const val = input.value;
        const res = evaluatePasswordStrength(val);
        label.textContent = res.label ? `Strength: ${res.label}` : "";
        label.className = `strength-label ${res.className}`;
        if (bar) {
            bar.style.width = `${res.percent}%`;
            bar.style.backgroundColor = res.color;
        }
    });
}

// ============================================================
// MODAL CONTROLS
// ============================================================

function openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.add("open");
        document.body.style.overflow = "hidden";
    }
}

function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.remove("open");
        document.body.style.overflow = "";
    }
}

// Close modal when clicking on overlay background
document.addEventListener("click", function (e) {
    if (e.target && (e.target.classList.contains("modal-overlay") || e.target.classList.contains("modal-backdrop"))) {
        e.target.classList.remove("open");
        document.body.style.overflow = "";
    }
});

// ============================================================
// TOAST ALERTS & NOTIFICATIONS
// ============================================================

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) {
        alert(message);
        return;
    }

    const alertBox = document.createElement("div");
    alertBox.className = `alert alert-${type === "error" ? "danger" : type}`;
    
    let iconClass = "fa-circle-info";
    if (type === "success") iconClass = "fa-circle-check";
    else if (type === "danger" || type === "error") iconClass = "fa-triangle-exclamation";
    else if (type === "warning") iconClass = "fa-circle-exclamation";

    alertBox.innerHTML = `
        <div class="alert-content">
            <i class="fas ${iconClass}"></i>
            <span>${message}</span>
        </div>
        <button onclick="this.parentElement.remove()" class="alert-close" aria-label="Close notification">&times;</button>
    `;

    container.prepend(alertBox);
    setTimeout(() => {
        if (alertBox.parentElement) {
            alertBox.style.opacity = "0";
            alertBox.style.transform = "translateY(-10px)";
            alertBox.style.transition = "all 0.3s";
            setTimeout(() => alertBox.remove(), 300);
        }
    }, 4500);
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
        emailInput.focus();
        
        // Visual feedback on inputs
        [emailInput, pwdInput].forEach(inp => {
            inp.style.borderColor = "var(--primary-light)";
            inp.style.boxShadow = "0 0 0 3px var(--primary-glow)";
            setTimeout(() => {
                inp.style.borderColor = "";
                inp.style.boxShadow = "";
            }, 600);
        });
    }
}

// ============================================================
// NUMBER COUNTER ANIMATION FOR STATS
// ============================================================

function animateCounters() {
    const valueElements = document.querySelectorAll(".metric-value, .stat-value");
    valueElements.forEach(el => {
        const text = el.textContent.trim();
        const num = parseFloat(text);
        if (!isNaN(num) && num > 0 && !text.includes(".") && !text.includes("/")) {
            let start = 0;
            const end = num;
            const duration = 800;
            const startTime = performance.now();

            function updateCounter(currentTime) {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                // Ease out cubic
                const easeOut = 1 - Math.pow(1 - progress, 3);
                el.textContent = Math.floor(easeOut * end);

                if (progress < 1) {
                    requestAnimationFrame(updateCounter);
                } else {
                    el.textContent = end;
                }
            }
            requestAnimationFrame(updateCounter);
        }
    });
}

// ============================================================
// LIVE SYSTEM CLOCK
// ============================================================

function updateLiveClock() {
    const clockText = document.getElementById("liveClockText");
    if (!clockText) return;

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    clockText.textContent = `${timeStr}`;
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
    // Mobile navigation toggle
    const toggleBtn = document.getElementById("mobileToggle");
    const sidebar = document.getElementById("sidebar");

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }

    // Bind password strength if inputs exist
    bindPasswordStrength("regPassword", "regStrengthLabel");
    bindPasswordStrength("newPassword", "newStrengthLabel");

    // Animate counters
    animateCounters();

    // Start Live Clock
    updateLiveClock();
    setInterval(updateLiveClock, 1000);

    // Auto-dismiss initial flashed alerts after 6 seconds
    const initialAlerts = document.querySelectorAll(".page-content > .alert, .login-form-wrapper .alert");
    initialAlerts.forEach(alert => {
        setTimeout(() => {
            if (alert.parentElement) {
                alert.style.opacity = "0";
                alert.style.transform = "translateY(-8px)";
                alert.style.transition = "all 0.4s ease";
                setTimeout(() => alert.remove(), 400);
            }
        }, 6000);
    });
});
