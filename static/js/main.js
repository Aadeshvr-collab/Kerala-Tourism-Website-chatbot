/**
 * main.js — Kerala Tourism AI — Global JavaScript
 * =================================================
 * Handles:
 * 1. Online/offline detection + status badge
 * 2. Global search functionality
 * 3. Navigation toggles (mobile, user dropdown)
 * 4. Toast notifications
 * 5. Navbar scroll effect
 * 6. Page animations
 */

// ================================================================
// 1. ONLINE / OFFLINE DETECTION
// ================================================================

/**
 * Detect if the user is online or offline.
 * 
 * THREE methods combined for reliability:
 * a) window.navigator.onLine — basic browser API
 * b) window 'online'/'offline' events — fires on change
 * c) Periodic ping to /api/connectivity — most reliable
 */

// Update the connectivity badge in navbar
function updateConnectivityBadge(isOnline) {
    const badge = document.getElementById('connectivityBadge');
    if (!badge) return;
    
    if (isOnline) {
        // Show green "Online" badge
        badge.className = 'connectivity-badge online';
        badge.innerHTML = '<span class="conn-dot"></span><span class="conn-text">Online</span>';
        badge.title = 'Connected to internet';
    } else {
        // Show red "Offline" badge
        badge.className = 'connectivity-badge offline';
        badge.innerHTML = '<span class="conn-dot"></span><span class="conn-text">Offline</span>';
        badge.title = 'No internet connection — using offline data';
    }
}

// Store last known connection state to avoid duplicate toasts
let lastConnectionState = true;

// Check connectivity by pinging our server endpoint
async function checkConnectivity() {
    try {
        const response = await fetch('/api/connectivity', {
            method: 'GET',
            cache: 'no-cache',
            signal: AbortSignal.timeout(5000)  // 5-second timeout
        });
        
        const isOnline = response.ok;
        
        // Only show toast when state CHANGES
        if (isOnline !== lastConnectionState) {
            lastConnectionState = isOnline;
            updateConnectivityBadge(isOnline);
            
            if (!isOnline) {
                showToast('📵 You\'re now offline. App will use local data.', 'offline', 5000);
            } else {
                showToast('✅ Back online! All features available.', 'online', 3000);
            }
        }
    } catch (error) {
        // Fetch failed = likely offline
        if (lastConnectionState !== false) {
            lastConnectionState = false;
            updateConnectivityBadge(false);
            showToast('📵 Connection lost. Switching to offline mode.', 'offline', 5000);
        }
    }
}

// Browser native events (fire immediately when connection changes)
window.addEventListener('online', () => {
    updateConnectivityBadge(true);
    checkConnectivity();
});

window.addEventListener('offline', () => {
    updateConnectivityBadge(false);
    showToast('📵 You\'re offline. App continues with local data.', 'offline', 5000);
});

// Periodic check every 30 seconds (catches subtle network issues)
setInterval(checkConnectivity, 30000);

// Initial check on page load
document.addEventListener('DOMContentLoaded', () => {
    updateConnectivityBadge(navigator.onLine);  // Quick immediate update
    checkConnectivity();  // Then verify with real request
});


// ================================================================
// 2. TOAST NOTIFICATION SYSTEM
// ================================================================

/**
 * Show a toast notification message at bottom-right of screen.
 * 
 * @param {string} message - Text to show
 * @param {string} type - 'online', 'offline', 'info', 'success', 'error'
 * @param {number} duration - Milliseconds before auto-dismiss
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    // Add to container (visible area)
    container.appendChild(toast);
    
    // Auto-remove after duration
    setTimeout(() => {
        toast.style.animation = 'slide-in-right 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ================================================================
// 3. NAVBAR SCROLL EFFECT
// ================================================================

/**
 * Add 'scrolled' class to navbar when page scrolls down.
 * This triggers CSS to increase blur/opacity.
 */
const navbar = document.getElementById('mainNav');

if (navbar) {
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    }, { passive: true });  // passive for performance
}


// ================================================================
// 4. MOBILE NAVIGATION TOGGLE
// ================================================================

/**
 * Toggle the mobile navigation menu (hamburger).
 * Called from onclick in base.html.
 */
function toggleMobileMenu() {
    const navLinks = document.getElementById('navLinks');
    const hamburger = document.getElementById('hamburger');
    
    if (!navLinks) return;
    
    const isOpen = navLinks.classList.toggle('open');
    hamburger.classList.toggle('active', isOpen);
}

// Close mobile menu when clicking outside
document.addEventListener('click', (e) => {
    const navLinks = document.getElementById('navLinks');
    const hamburger = document.getElementById('hamburger');
    
    if (navLinks && hamburger) {
        if (!hamburger.contains(e.target) && !navLinks.contains(e.target)) {
            navLinks.classList.remove('open');
            hamburger.classList.remove('active');
        }
    }
});


// ================================================================
// 5. USER DROPDOWN TOGGLE
// ================================================================

/**
 * Toggle the user dropdown menu.
 * Called from onclick in base.html.
 */
function toggleUserMenu() {
    const dropdown = document.getElementById('userDropdown');
    if (!dropdown) return;
    dropdown.classList.toggle('open');
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const userMenu = document.querySelector('.user-menu');
    const dropdown = document.getElementById('userDropdown');
    
    if (userMenu && dropdown) {
        if (!userMenu.contains(e.target)) {
            dropdown.classList.remove('open');
        }
    }
});


// ================================================================
// 6. GLOBAL SEARCH
// ================================================================

/**
 * Real-time search across all Kerala places.
 * As user types in the navbar search box:
 * 1. Sends request to /api/search?q=...
 * 2. Displays results as dropdown links
 */

const searchInput = document.getElementById('globalSearch');
const searchResults = document.getElementById('searchResults');

if (searchInput && searchResults) {
    let searchTimeout;  // Debounce timer
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        
        // Clear previous timer (debounce: wait 300ms after typing stops)
        clearTimeout(searchTimeout);
        
        if (!query) {
            // Hide results if search is empty
            searchResults.style.display = 'none';
            return;
        }
        
        // Wait 300ms before sending request (avoids too many requests)
        searchTimeout = setTimeout(() => performSearch(query), 300);
    });
    
    // Hide results when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.style.display = 'none';
        }
    });
}

/**
 * Perform search via API and display results
 * @param {string} query - Search term
 */
async function performSearch(query) {
    if (!searchResults) return;
    
    try {
        // Fetch search results from Flask API
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        if (data.results.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item" style="opacity:0.5; cursor:default;">No results found</div>';
            searchResults.style.display = 'block';
            return;
        }
        
        // Build dropdown HTML from results
        const html = data.results.slice(0, 6).map(place => {
            // Determine emoji based on category
            const emoji = place.category.includes('beach') ? '🏖️' :
                          place.category.includes('hill') ? '⛰️' :
                          place.category.includes('backwater') ? '🚤' :
                          place.category.includes('wildlife') ? '🐘' :
                          place.category.includes('heritage') ? '🏛️' : '🌴';
            
            return `
                <a href="/place/${place.district_id}/${place.id}" class="search-result-item">
                    <span class="sr-icon">${emoji}</span>
                    <div>
                        <div class="sr-name">${place.name}</div>
                        <div class="sr-district">${place.district_name} • ${place.category.join(', ')}</div>
                    </div>
                </a>
            `;
        }).join('');
        
        searchResults.innerHTML = html;
        searchResults.style.display = 'block';
        
    } catch (error) {
        // Offline — search doesn't work
        searchResults.innerHTML = '<div class="search-result-item" style="opacity:0.5; cursor:default;">⚠️ Search unavailable offline</div>';
        searchResults.style.display = 'block';
    }
}


// ================================================================
// 7. INTERSECTION OBSERVER — Animate cards on scroll
// ================================================================

/**
 * Animate feature cards, place cards etc. as they scroll into view.
 * Uses IntersectionObserver API (modern, performant).
 */
const observerOptions = {
    threshold: 0.15,        // Trigger when 15% of element is visible
    rootMargin: '0px 0px -50px 0px'  // Slightly before reaching viewport
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, index) => {
        if (entry.isIntersecting) {
            // Add visible class with delay based on position
            const delay = entry.target.dataset.delay || 0;
            setTimeout(() => {
                entry.target.classList.add('message-visible');
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }, parseInt(delay));
            
            // Stop observing once animated
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Observe all animatable cards
document.querySelectorAll('.feature-card, .place-card, .district-card, .hotel-card, .plan-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    observer.observe(el);
});
