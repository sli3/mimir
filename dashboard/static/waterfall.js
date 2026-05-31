/**
 * Waterfall display for Mimir RF Scanner.
 *
 * How a waterfall works (for beginners):
 * ---------------------------------------
 * The canvas is like a grid of coloured pixels, one pixel wide for each
 * frequency bin in the spectrum. Think of it as a horizontal ruler where
 * left = low frequency, right = high frequency.
 *
 * Each time we receive new spectrum data:
 * 1. We add ONE NEW ROW at the TOP of the canvas
 * 2. All existing rows shift DOWN by one pixel
 * 3. The colour of each pixel = signal power at that frequency
 *    - Dark blue/black = weak noise
 *    - Bright yellow/white = strong signal
 *
 * Over time this creates a scrolling effect like water flowing down a
 * waterfall, showing you how signals change over time. It's great for
 * spotting intermittent signals or interference patterns.
 *
 * Why this matters:
 * -----------------
 * A static spectrum shows you what's there NOW. A waterfall shows you
 * what's been there OVER TIME. You can see if a signal is constant,
 * fleeting, or repeating at regular intervals.
 */

// Connection settings
const WS_URL = "ws://" + window.location.hostname + ":8899/ws/spectrum";

// Number of frequency bins (must match FFT size used in capture_loop.py)
const NUM_BINS = 2048;

// Colour scale anchors - maps dB values to colours
const MIN_DB = -50;   // noise floor anchor — below this = black
const MAX_DB = -20;   // strong signal anchor — above this = white

/**
 * Get the canvas element by its ID.
 */
const canvas = document.getElementById("waterfall");
const ctx = canvas.getContext("2d");

function resizeCanvas() {
    const container = document.getElementById("waterfall-container");
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
}

/**
 * Convert a dB value to an RGB colour object.
 *
 * Uses a classic spectrum analyser palette:
 * - 0.0 to 0.2: black → dark blue (quiet noise)
 * - 0.2 to 0.5: dark blue → cyan (weak signal)
 * - 0.5 to 0.8: cyan → yellow (moderate signal)
 * - 0.8 to 1.0: yellow → white (strong signal)
 *
 * @param {number} db - Signal power in dBFS
 * @returns {Object} RGB colour object like {r: 0, g: 255, b: 255}
 */
function powerToColour(db) {
    // Clamp to valid range
    const clamped = Math.min(MAX_DB, Math.max(MIN_DB, db));

    // Normalize to 0.0 - 1.0
    const normalized = (clamped - MIN_DB) / (MAX_DB - MIN_DB);

    // Predefined colours for the four segments
    const colours = [
        { r: 0, g: 0, b: 0 },         // black
        { r: 0, g: 0, b: 139 },       // dark blue
        { r: 0, g: 255, b: 255 },     // cyan
        { r: 255, g: 255, b: 0 },     // yellow
        { r: 255, g: 255, b: 255 },   // white
    ];

    let r, g, b;

    if (normalized < 0.2) {
        // black to dark blue
        const t = normalized / 0.2;
        r = colours[0].r + (colours[1].r - colours[0].r) * t;
        g = colours[0].g + (colours[1].g - colours[0].g) * t;
        b = colours[0].b + (colours[1].b - colours[0].b) * t;
    } else if (normalized < 0.5) {
        // dark blue to cyan
        const t = (normalized - 0.2) / 0.3;
        r = colours[1].r + (colours[2].r - colours[1].r) * t;
        g = colours[1].g + (colours[2].g - colours[1].g) * t;
        b = colours[1].b + (colours[2].b - colours[1].b) * t;
    } else if (normalized < 0.8) {
        // cyan to yellow
        const t = (normalized - 0.5) / 0.3;
        r = colours[2].r + (colours[3].r - colours[2].r) * t;
        g = colours[2].g + (colours[3].g - colours[2].g) * t;
        b = colours[2].b + (colours[3].b - colours[2].b) * t;
    } else {
        // yellow to white
        const t = (normalized - 0.8) / 0.2;
        r = colours[3].r + (colours[4].r - colours[3].r) * t;
        g = colours[3].g + (colours[4].g - colours[3].g) * t;
        b = colours[3].b + (colours[4].b - colours[3].b) * t;
    }

    return { r: Math.round(r), g: Math.round(g), b: Math.round(b) };
}

/**
 * Draw a single row of spectrum data onto the canvas.
 *
 * Takes the psd_db array (2048 floats) from the WebSocket message,
 * scales it to canvas.width pixels, then shifts all existing rows
 * down by one pixel and places the new row at the top.
 *
 * @param {Array} psdDb - Array of 2048 dBFS values
 */
function drawRow(psdDb) {
    // Create a 1-pixel-tall row with canvas.width columns
    const rowData = ctx.createImageData(canvas.width, 1);

    // Fill the row with colours based on signal power
    for (let i = 0; i < canvas.width; i++) {
        // Map canvas pixel to nearest bin index
        const binIndex = Math.floor(i * NUM_BINS / canvas.width);
        const db = psdDb[binIndex];
        const colour = powerToColour(db);
        const index = i * 4;

        rowData.data[index] = colour.r; // r
        rowData.data[index + 1] = colour.g; // g
        rowData.data[index + 2] = colour.b; // b
        rowData.data[index + 3] = 255; // alpha (fully opaque)
    }

    // Shift existing content down by 1 pixel using drawImage
    ctx.drawImage(canvas, 0, 0, canvas.width, canvas.height - 1,
                            0, 1, canvas.width, canvas.height - 1);

    // Put the new row at the top (y=0)
    ctx.putImageData(rowData, 0, 0);
}

/**
 * Main loop that processes incoming spectrum data.
 */
function processSpectrum(data) {
    if (data.type === "spectrum" && Array.isArray(data.psd_db)) {
        drawRow(data.psd_db);
    }
}

/**
 * Set up WebSocket connection to the dashboard server.
 */
function connectWebSocket() {
    const ws = new WebSocket(WS_URL);

    ws.onopen = function () {
        console.log("Waterfall: Connected to spectrum websocket");
    };

    ws.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            processSpectrum(data);
        } catch (e) {
            console.error("Waterfall: Failed to parse message", e);
        }
    };

    ws.onclose = function () {
        console.log("Waterfall: WebSocket closed");
    };

    ws.onerror = function () {
        console.log("Waterfall: WebSocket error");
    };
}

window.addEventListener("resize", function () {
    resizeCanvas();
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
});

// Start immediately when script runs - no event listener needed
// since defer was removed from the script tag
(function () {
    resizeCanvas();
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    connectWebSocket();
})();
