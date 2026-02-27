/**
 * frontend_guide.js — How the Frontend Should Collect & Send Behavioral Data
 * ─────────────────────────────────────────────────────────────────────────
 * This is a REFERENCE GUIDE for your frontend team.
 * It shows how to measure behavioral signals in a browser and
 * send them to the Django backend in the correct format.
 *
 * NOTE: Device and location data must be HASHED before sending —
 * never send raw fingerprint strings to the server.
 */


// ─── 1. COLLECT BEHAVIORAL SIGNALS ──────────────────────────────────────────

class BehaviorCollector {
    constructor() {
        this.keyPressTimestamps = [];  // [{ key, pressTime, releaseTime }]
        this.mousePositions     = [];  // [{ x, y, timestamp }]
        this.clickTimestamps    = [];  // [timestamp, timestamp, ...]
        this.scrollPositions    = [];  // [scrollY at various moments]
        this.sessionStartTime   = Date.now();

        this._attachListeners();
    }

    _attachListeners() {
        // Track key press/release for typing speed + hold time
        document.addEventListener('keydown', (e) => {
            this.keyPressTimestamps.push({ key: e.key, pressTime: Date.now(), releaseTime: null });
        });
        document.addEventListener('keyup', (e) => {
            const entry = this.keyPressTimestamps.find(k => k.key === e.key && !k.releaseTime);
            if (entry) entry.releaseTime = Date.now();
        });

        // Track mouse movement for velocity
        let lastMousePos = null;
        document.addEventListener('mousemove', (e) => {
            const now = Date.now();
            if (lastMousePos) {
                this.mousePositions.push({
                    x: e.clientX, y: e.clientY,
                    timestamp: now,
                    prevX: lastMousePos.x, prevY: lastMousePos.y,
                    prevTime: lastMousePos.time
                });
            }
            lastMousePos = { x: e.clientX, y: e.clientY, time: now };
        });

        // Track click timing for click_interval
        document.addEventListener('click', () => {
            this.clickTimestamps.push(Date.now());
        });

        // Track scroll depth
        document.addEventListener('scroll', () => {
            const scrolled = window.scrollY + window.innerHeight;
            const total    = document.documentElement.scrollHeight;
            this.scrollPositions.push(scrolled / total);
        });
    }

    // ── Compute engineered features ──────────────────────────────────────

    getTypingSpeed() {
        // Characters per second during the session
        const completed = this.keyPressTimestamps.filter(k => k.releaseTime);
        if (completed.length < 2) return 0;
        const duration = (Date.now() - this.sessionStartTime) / 1000; // seconds
        return completed.length / duration;
    }

    getKeyHoldTime() {
        // Average milliseconds a key is held down
        const completed = this.keyPressTimestamps.filter(k => k.releaseTime);
        if (!completed.length) return 0;
        const total = completed.reduce((sum, k) => sum + (k.releaseTime - k.pressTime), 0);
        return total / completed.length;
    }

    getMouseVelocity() {
        // Average pixels per millisecond of mouse movement
        if (this.mousePositions.length < 2) return 0;
        let totalVelocity = 0;
        this.mousePositions.forEach(pos => {
            const dist = Math.hypot(pos.x - pos.prevX, pos.y - pos.prevY);
            const time = pos.timestamp - pos.prevTime;
            if (time > 0) totalVelocity += (dist / time) * 1000; // px/sec
        });
        return totalVelocity / this.mousePositions.length;
    }

    getClickInterval() {
        // Average milliseconds between consecutive clicks
        if (this.clickTimestamps.length < 2) return 0;
        let totalInterval = 0;
        for (let i = 1; i < this.clickTimestamps.length; i++) {
            totalInterval += this.clickTimestamps[i] - this.clickTimestamps[i - 1];
        }
        return totalInterval / (this.clickTimestamps.length - 1);
    }

    getScrollDepth() {
        // Max scroll depth reached (0.0 = top, 1.0 = bottom)
        if (!this.scrollPositions.length) return 0;
        return Math.min(1.0, Math.max(...this.scrollPositions));
    }


    // ── Get all features as a flat object ────────────────────────────────

    getFeatureVector() {
        return {
            typing_speed:   this.getTypingSpeed(),
            key_hold_time:  this.getKeyHoldTime(),
            mouse_velocity: this.getMouseVelocity(),
            click_interval: this.getClickInterval(),
            scroll_depth:   this.getScrollDepth(),
        };
    }
}


// ─── 2. HASH DEVICE & LOCATION ───────────────────────────────────────────────

async function sha256(str) {
    /** Browser-native SHA-256 hashing (no library needed) */
    const msgBuffer  = new TextEncoder().encode(str);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray  = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function getDeviceHash() {
    /**
     * Build a fingerprint from non-sensitive browser attributes,
     * then hash it. NEVER send the raw string to the server.
     */
    const fingerprint = [
        navigator.userAgent,
        navigator.language,
        screen.width + 'x' + screen.height,
        screen.colorDepth,
        new Date().getTimezoneOffset(),
        navigator.hardwareConcurrency || 'unknown',
    ].join('|');

    return await sha256(fingerprint);
}

async function getLocationHash() {
    /**
     * Use a coarse location signal (timezone + language region),
     * NOT GPS. Hash it before sending. This gives city/region-level
     * context without exposing precise location.
     */
    const coarseLocation = [
        Intl.DateTimeFormat().resolvedOptions().timeZone,
        navigator.language,
    ].join('|');

    return await sha256(coarseLocation);
}

async function getNetworkLatency() {
    /**
     * Measure round-trip time to the server with a lightweight ping.
     * Use the /api/auth/login/ endpoint itself, or a dedicated /ping/ route.
     */
    const start = performance.now();
    try {
        await fetch('/api/auth/login/', { method: 'HEAD' });
        return Math.round(performance.now() - start);
    } catch {
        return 999; // Can't measure → return high value
    }
}


// ─── 3. ASSEMBLE & SEND TO BACKEND ──────────────────────────────────────────

async function loginWithBehavior(email) {
    /**
     * Full login flow:
     *   1. Collect behavioral features from the collector
     *   2. Gather device/location hashes + network latency
     *   3. POST to /api/auth/login/
     */
    const collector = window._behaviorCollector; // Must be started at page load

    const [device_hash, location_hash, network_latency] = await Promise.all([
        getDeviceHash(),
        getLocationHash(),
        getNetworkLatency(),
    ]);

    const behaviorFeatures = collector.getFeatureVector();

    const payload = {
        email: email,
        behavior_data: {
            ...behaviorFeatures,
            network_latency: network_latency,
            device_hash:     device_hash,
            location_hash:   location_hash,
            time_of_day:     new Date().getUTCHours(),  // 0-23, UTC
        }
    };

    console.log('Sending behavioral payload:', payload);

    const response = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (response.ok) {
        console.log('✅ Authenticated! Trust score:', result.trust_score);
        // Store session_token for subsequent API calls
        localStorage.setItem('session_token', result.session_token);
    } else {
        console.warn('❌ Auth failed. Trust score:', result.trust_score);
    }

    return result;
}


// ─── 4. USAGE EXAMPLE ───────────────────────────────────────────────────────

// Start collecting as soon as the page loads (before the user hits "login")
window._behaviorCollector = new BehaviorCollector();

// When the user clicks "Login":
// loginWithBehavior('user@example.com');


/*
 * ─── EXAMPLE JSON REQUEST (what gets sent to POST /api/auth/login/) ───────
 *
 * {
 *   "email": "johndoe@example.com",
 *   "behavior_data": {
 *     "typing_speed":    4.2,       // chars/sec
 *     "key_hold_time":   112.5,     // avg ms per key
 *     "mouse_velocity":  380.0,     // avg px/sec
 *     "click_interval":  620.0,     // avg ms between clicks
 *     "scroll_depth":    0.65,      // 65% of page scrolled
 *     "network_latency": 45.0,      // ms round-trip
 *     "device_hash":     "a3f1c8d2...64 hex chars...",
 *     "location_hash":   "9c2b4e71...64 hex chars...",
 *     "time_of_day":     14         // 2pm UTC
 *   }
 * }
 *
 * ─── EXAMPLE JSON RESPONSE (success, 200 OK) ─────────────────────────────
 *
 * {
 *   "message": "Behavioral authentication successful.",
 *   "session_token": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
 *   "trust_score": 82,
 *   "threshold": 60,
 *   "user": {
 *     "id": "550e8400-e29b-41d4-a716-446655440000",
 *     "email": "johndoe@example.com",
 *     "username": "johndoe",
 *     "created_at": "2025-01-15T10:22:00Z"
 *   }
 * }
 *
 * ─── EXAMPLE JSON RESPONSE (failure, 401 Unauthorized) ───────────────────
 *
 * {
 *   "error": "Behavioral authentication failed. Access denied.",
 *   "trust_score": 38,
 *   "threshold": 60,
 *   "hint": "Your behavioral patterns did not match your profile."
 * }
 */
