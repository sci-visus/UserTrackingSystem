import panel as pn
import param
import openslide
from panel.reactive import ReactiveHTML
from PIL import Image
import logging
import os
import json
import glob
import time
from datetime import datetime
from dotenv import load_dotenv
from utility import *


class SVSLeafletViewer(ReactiveHTML):
    """
    Interactive SVS viewer using Leaflet for smooth pan and zoom.
    Uses Leaflet-DeepZoom to display DZI tiles.
    """
    
    dzi_url = param.String(default='', doc="URL to DZI descriptor file")
    
    max_zoom = param.Integer(default=17, doc="Maximum zoom level")
    
    width_px = param.Integer(default=1000, doc="Image width in pixels")
    
    height_px = param.Integer(default=1000, doc="Image height in pixels")
    
    zoom = param.Integer(default=0, bounds=(0, 10), doc="Current zoom level")
    
    zoom_level = param.String(default="Level 3 (1x)", doc="Current zoom level display")

    center = param.List(default=[0, 0], doc="Current center of the map [lat, lng]")
    
    level_dimensions = param.List(default=[], doc="List of [width, height] for each pyramid level")
    
    # Metadata-driven parameters for automatic configuration
    start_level = param.Integer(default=11, doc="DZI level to use as Leaflet zoom 0")
    
    center_offset_y = param.Number(default=-1.12, doc="Y center adjustment multiplier")
    
    # DZI server port configuration
    dzi_server_port = param.String(default='10566', doc="Port for DZI tile server")
    
    # Force re-render trigger
    reload_counter = param.Integer(default=0, doc="Increment to force map reload")

    # Scalebar configuration
    mm_per_pixel = param.Number(default=0.0004, doc="Millimeters per pixel at base resolution")
    
    # SVS metadata for accurate magnification display
    objective_power = param.Number(default=40.0, doc="Base magnification from SVS metadata")
    level_downsamples = param.List(default=[1.0, 4.0, 16.0, 32.0], doc="Downsample factors from SVS metadata")
    
    # Annotation saving/loading parameters
    image_name = param.String(default='', doc="Current image name for annotation storage")
    save_annotation_trigger = param.Integer(default=0, doc="Trigger to save current annotations")
    load_annotation_trigger = param.Integer(default=0, doc="Trigger to load annotations")
    annotation_data = param.String(default='', doc="JSON string of annotations to load")
    undo_trigger = param.Integer(default=0, doc="Trigger undo operation")
    redo_trigger = param.Integer(default=0, doc="Trigger redo operation")
    prev_saved_trigger = param.Integer(default=0, doc="Load previous saved view")
    next_saved_trigger = param.Integer(default=0, doc="Load next saved view")
    keyboard_trigger = param.String(default='', doc="Keyboard shortcut trigger")
    image_nav_trigger = param.String(default='', doc="Image navigation keyboard trigger")
    
    # Keyboard shortcuts configuration (JSON string)
    shortcuts_config = param.String(default='', doc="JSON string of keyboard shortcuts configuration")

    
    _template = """
    <style>
        .leaflet-container {
            background-color: #dadae3 !important;
            user-select: none !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
        }
        .leaflet-tile-pane, .leaflet-tile-container {
            background-color: transparent !important;
        }
        /* Drawing toolbar styles */
        .leaflet-draw-toolbar a {
            background-color: white !important;
            user-select: none !important;
            -webkit-user-select: none !important;
        }
        /* Disable text selection on all leaflet elements */
        .leaflet-control, .leaflet-bar, .leaflet-control a {
            user-select: none !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
        }
        /* Custom pen cursor */
        .pen-cursor {
            cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 16 16'%3E%3Cpath fill='%23000' d='M12.854 0.854l2.292 2.292-9.5 9.5-2.292 0.146-0.146-2.292 9.5-9.5zM13.207 3.5l-1.207-1.207-7.5 7.5 0.073 1.134 1.134 0.073 7.5-7.5z'/%3E%3C/svg%3E") 0 16, crosshair !important;
        }
    </style>
    <div id="map_div" style="position: relative; width: 100%; height: 100%; min-height: 600px;"></div>
    """
    
    _scripts = {
        'render': """
            console.log('=== SVS VIEWER v5.0 - Fixed Viewport ===');
            console.log('Render script executed');
            
            // Inline MiniMap CSS
            if (!document.getElementById('minimap-css')) {
                const style = document.createElement('style');
                style.id = 'minimap-css';
                style.textContent = `.leaflet-control-minimap{border:rgba(255,255,255,1) solid;box-shadow:0 1px 5px rgba(0,0,0,.65);border-radius:3px;background:#f8f8f9;transition:all .6s}.leaflet-control-minimap a{background-color:rgba(255,255,255,1);background-repeat:no-repeat;z-index:99999;transition:all .6s}.leaflet-control-minimap a.minimized-bottomright{-webkit-transform:rotate(180deg);transform:rotate(180deg);border-radius:0}.leaflet-control-minimap a.minimized-topleft{-webkit-transform:rotate(0deg);transform:rotate(0deg);border-radius:0}.leaflet-control-minimap a.minimized-bottomleft{-webkit-transform:rotate(270deg);transform:rotate(270deg);border-radius:0}.leaflet-control-minimap a.minimized-topright{-webkit-transform:rotate(90deg);transform:rotate(90deg);border-radius:0}.leaflet-control-minimap-toggle-display{background-image:url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOSIgaGVpZ2h0PSIxOSI+PHBhdGggZD0iTTkuNSAwTDAgOS41IDE5IDkuNXoiIGZpbGw9IiNmZmYiLz48L3N2Zz4=);background-size:cover;position:absolute;border-radius:3px 0 0}.leaflet-control-minimap-toggle-display-bottomright{bottom:0;right:0}.leaflet-control-minimap-toggle-display-topleft{top:0;left:0;-webkit-transform:rotate(180deg);transform:rotate(180deg)}.leaflet-control-minimap-toggle-display-bottomleft{bottom:0;left:0;-webkit-transform:rotate(90deg);transform:rotate(90deg)}.leaflet-control-minimap-toggle-display-topright{top:0;right:0;-webkit-transform:rotate(270deg);transform:rotate(270deg)}`;
                document.head.appendChild(style);
                console.log('✓ MiniMap CSS injected');
            }
        """,
        
        'after_layout': """
            console.log('=== after_layout v11.0: Dynamic Keyboard Shortcuts + MiniMap + Freehand Drawing ===');
            
            // Parse shortcuts configuration from Python
            let shortcuts = {};
            try {
                if (data.shortcuts_config) {
                    shortcuts = JSON.parse(data.shortcuts_config);
                    console.log('✓ Loaded custom keyboard shortcuts:', Object.keys(shortcuts).length, 'actions');
                }
            } catch (e) {
                console.error('Error parsing shortcuts config:', e);
            }
            
            // Helper function to check if key combination matches
            function matchesKeyCombination(event, keyCombo) {
                const parts = keyCombo.split('+');
                let hasCtrl = false, hasCmd = false, hasAlt = false, hasShift = false;
                let mainKey = null;
                
                for (const part of parts) {
                    const partLower = part.toLowerCase();
                    if (partLower === 'ctrl') hasCtrl = true;
                    else if (partLower === 'cmd' || partLower === 'meta') hasCmd = true;
                    else if (partLower === 'alt') hasAlt = true;
                    else if (partLower === 'shift') hasShift = true;
                    else mainKey = part;
                }
                
                // Check modifiers
                const ctrlMatch = hasCtrl || hasCmd ? (event.ctrlKey || event.metaKey) : (!event.ctrlKey && !event.metaKey);
                const altMatch = hasAlt ? event.altKey : !event.altKey;
                const shiftMatch = hasShift ? event.shiftKey : !event.shiftKey;
                
                // Check main key
                let keyMatch = false;
                if (mainKey) {
                    keyMatch = event.key.toLowerCase() === mainKey.toLowerCase();
                }
                
                return ctrlMatch && altMatch && shiftMatch && keyMatch;
            }
            
            // Keyboard shortcuts handler - set up once
            if (!window.keyboardShortcutsRegistered) {
                document.addEventListener('keydown', function(e) {
                    // Check each configured shortcut
                    for (const [actionName, config] of Object.entries(shortcuts)) {
                        const keys = config.keys || [];
                        
                        // Check if any of the key combinations match
                        for (const keyCombo of keys) {
                            if (matchesKeyCombination(e, keyCombo)) {
                                e.preventDefault();
                                const action = config.action || actionName;
                                console.log('⌨️  Keyboard:', action, '(' + keyCombo + ')');
                                data.keyboard_trigger = action;
                                return; // Exit after first match
                            }
                        }
                    }
                });
                window.keyboardShortcutsRegistered = true;
                console.log('✓ Keyboard shortcuts registered dynamically from configuration');
            }
            
            // Inline freehand drawing module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'freehand_drawing.js'), 'r').read() + """
            
            // Inline scale bar module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'scale_bar.js'), 'r').read() + """
            
            // Inline minimap overview module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'minimap_overview.js'), 'r').read() + """
            
            // Define DZITileLayer if not already defined (fallback for CDN issues)
            if (typeof DZITileLayer === 'undefined' && typeof L !== 'undefined') {
                console.log('Defining DZITileLayer inline...');
                var DZITileLayer = L.TileLayer.extend({
                    getTileUrl: function(coords) {
                        return 'http://localhost:' + data.dzi_server_port + '/' + 
                               data.dzi_url.replace('.dzi', '_files') + '/' + 
                               coords.z + '/' + coords.x + '_' + coords.y + '.png';
                    }
                });
                console.log('✓ DZITileLayer defined');
            }
            
            // Wait for essential libraries to load before initializing
            let initAttempts = 0;
            const maxAttempts = 50; // 5 seconds max wait
            
            function checkLibraries() {
                const leafletReady = typeof L !== 'undefined';
                const dziReady = typeof DZITileLayer !== 'undefined';
                const minimapReady = leafletReady && typeof L.Control.MiniMap !== 'undefined';
                
                // Only require essential libraries (Leaflet, DZI)
                // MiniMap is optional
                return {
                    ready: leafletReady && dziReady,
                    leaflet: leafletReady,
                    dzi: dziReady,
                    minimap: minimapReady
                };
            }
            
            function initializeMap() {
                initAttempts++;
                const libStatus = checkLibraries();
                
                console.log('📦 Library Check (attempt ' + initAttempts + '):');
                console.log('  - Leaflet:', libStatus.leaflet ? '✓' : '❌');
                console.log('  - Leaflet DeepZoom:', libStatus.dzi ? '✓' : '❌');
                console.log('  - Leaflet MiniMap:', libStatus.minimap ? '✓ (optional)' : '❌ (optional)');
                
                if (!libStatus.ready) {
                    if (initAttempts >= maxAttempts) {
                        console.error('❌ Timeout waiting for libraries to load');
                        return;
                    }
                    console.log('⏳ Waiting for libraries to load...');
                    setTimeout(initializeMap, 100);
                    return;
                }
                
                console.log('✓ Essential libraries loaded, initializing map...');
                if (!libStatus.minimap) {
                    console.warn('⚠️ MiniMap plugin not available - continuing without it');
                }
                
                // Panel ReactiveHTML components are in shadow DOM
                // Need to find the shadow root first
                let mapDiv = null;
                
                // Search ALL elements in the document for shadow roots
                const allElements = document.querySelectorAll('*');
                console.log('Total elements in document:', allElements.length);
                
                let shadowRootsFound = 0;
                for (let element of allElements) {
                    if (element.shadowRoot) {
                        shadowRootsFound++;
                        
                        // Check specifically for ReactiveHTML component
                        if (element.className.includes('ReactiveHTML')) {
                            console.log('✓ Found ReactiveHTML shadow root!');
                            
                            // Try to find the map div by ID using querySelector (searches all descendants)
                            mapDiv = element.shadowRoot.querySelector('#map_div');
                            
                            if (mapDiv) {
                                console.log('✓ Found map_div by querySelector!');
                                break;
                            }
                            
                            // Fallback: Search ALL divs in shadow root (including nested ones)
                            const allDivs = element.shadowRoot.querySelectorAll('div');
                            console.log('  DIV children found:', allDivs.length);
                            
                            for (let div of allDivs) {
                                const style = div.getAttribute('style') || '';
                                const id = div.getAttribute('id') || '';
                                console.log('  Checking div - id:', id, 'style:', style);
                                
                                // Our map_div has id="map_div"
                                if (id === 'map_div') {
                                    mapDiv = div;
                                    console.log('✓ Found map_div by id attribute!');
                                    break;
                                }
                                
                                // Or look for the position: relative style with min-height
                                if (style.includes('position: relative') && style.includes('min-height')) {
                                    mapDiv = div;
                                    console.log('✓ Found map_div by style attributes!');
                                    break;
                                }
                            }
                            
                            if (mapDiv) break;
                        }
                    }
                }
                
                console.log('Total shadow roots searched:', shadowRootsFound);
                
                if (!mapDiv) {
                    console.error('Map div not found! Aborting.');
                    return;
                }
                
                console.log('✓ Map div found, initializing Leaflet map...');
                
                // CRITICAL: Remove existing map if it exists to prevent stale tile URLs
                if (state.map) {
                    console.log('Removing existing map instance...');
                    state.map.remove();
                    state.map = null;
                    state.tileLayer = null;
                }
                    
                const imageWidth = data.width_px;
                const imageHeight = data.height_px;
                const maxZoom = data.max_zoom;
                
                console.log('Image size:', imageWidth, 'x', imageHeight);
                console.log('Max DZI zoom level:', maxZoom);
                
                // Calculate the scale factor - at max zoom, 1 pixel = 1 coordinate unit
                // DZI max zoom (17) shows full resolution image
                const scale = Math.pow(2, maxZoom);
                const scaledWidth = imageWidth / scale;
                const scaledHeight = imageHeight / scale;
                
                console.log('Scale at zoom 0:', scaledWidth, 'x', scaledHeight);
                
                // SOLUTION AFTER INVESTIGATION:
                // Problem: DZI level 8 tile is 182×139px, but level 9+ tiles are 257×257px
                // This inconsistency causes Leaflet to scale incorrectly
                //
                // FIX: Start at DZI level 9 (not 8) where tiles are consistently sized
                // At Leaflet zoom 0 = DZI level 9 (2×2 tiles = 512×512 coordinate space)
                // This gives uniform tile sizes across all zoom levels
                
                console.log('Container size:', mapDiv.offsetWidth, 'x', mapDiv.offsetHeight);
                console.log('Image dimensions:', imageWidth, 'x', imageHeight);
                
                // Get start level and center offset from metadata
                //const startLevel = data.recommended_start_level || 9;
                const startLevel = 8;
                console.log('Using fixed start level:', startLevel);
                const centerOffsetY = data.center_offset_y || -1.15;
                
                console.log('Starting at DZI level', startLevel);
                console.log('Center offset Y multiplier:', centerOffsetY);
                
                // Calculate dimensions at start level
                const scaleAtStart = Math.pow(2, maxZoom - startLevel);
                const widthAtStartLevel = imageWidth / scaleAtStart;
                const heightAtStartLevel = imageHeight / scaleAtStart;
                
                console.log('Image at level', startLevel + ':', widthAtStartLevel.toFixed(1), 'x', heightAtStartLevel.toFixed(1), 'pixels');
                
                // Use actual image dimensions as coordinate space
                const centerY = heightAtStartLevel / 2;
                const centerX = widthAtStartLevel / 2;
                
                state.map = L.map(mapDiv, {
                    crs: L.CRS.Simple,
                    minZoom: 0,
                    maxZoom: maxZoom - startLevel,  // Max Leaflet zoom
                    zoomControl: false,  // Disable default zoom control, we'll add custom one
                    attributionControl: false,
                    zoomSnap: 1,
                    zoomDelta: 1,
                    wheelPxPerZoomLevel: 60,
                    boxZoom: false  // Disable box zoom (Shift+drag) to allow freehand drawing
                });
                
                console.log('Map object created, max Leaflet zoom:', maxZoom - startLevel);
                
                // Add custom zoom control with magnification display
                L.Control.CustomZoom = L.Control.extend({
                    options: {
                        position: 'topleft'
                    },
                    
                    onAdd: function(map) {
                        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                        container.style.display = 'flex';
                        container.style.flexDirection = 'column';
                        container.style.gap = '0';
                        
                        // Zoom in button
                        const zoomInButton = L.DomUtil.create('a', 'leaflet-control-zoom-in', container);
                        zoomInButton.innerHTML = '+';
                        zoomInButton.href = '#';
                        zoomInButton.title = 'Zoom in';
                        zoomInButton.setAttribute('role', 'button');
                        zoomInButton.setAttribute('aria-label', 'Zoom in');
                        
                        // Magnification display
                        const magDisplay = L.DomUtil.create('div', 'leaflet-control-zoom-mag', container);
                        magDisplay.style.backgroundColor = 'white';
                        magDisplay.style.padding = '2px 8px';
                        magDisplay.style.textAlign = 'center';
                        magDisplay.style.fontSize = '12px';
                        magDisplay.style.fontWeight = 'bold';
                        magDisplay.style.borderTop = '1px solid #ccc';
                        magDisplay.style.borderBottom = '1px solid #ccc';
                        magDisplay.style.cursor = 'default';
                        magDisplay.innerHTML = '0x';
                        
                        // Zoom out button
                        const zoomOutButton = L.DomUtil.create('a', 'leaflet-control-zoom-out', container);
                        zoomOutButton.innerHTML = '−';
                        zoomOutButton.href = '#';
                        zoomOutButton.title = 'Zoom out';
                        zoomOutButton.setAttribute('role', 'button');
                        zoomOutButton.setAttribute('aria-label', 'Zoom out');
                        
                        // Event handlers
                        L.DomEvent.on(zoomInButton, 'click', function(e) {
                            L.DomEvent.stopPropagation(e);
                            L.DomEvent.preventDefault(e);
                            map.zoomIn();
                        });
                        
                        L.DomEvent.on(zoomOutButton, 'click', function(e) {
                            L.DomEvent.stopPropagation(e);
                            L.DomEvent.preventDefault(e);
                            map.zoomOut();
                        });
                        
                        L.DomEvent.disableClickPropagation(container);
                        L.DomEvent.disableScrollPropagation(container);
                        
                        // Update magnification display
                        this._magDisplay = magDisplay;
                        this._updateMagDisplay = function() {
                            const zoom = map.getZoom();
                            
                            // Calculate actual magnification based on SVS metadata
                            // DZI level = startLevel + Leaflet zoom
                            const dziLevel = startLevel + Math.floor(zoom);
                            
                            // Base magnification from SVS metadata (e.g., 40×)
                            const baseMag = data.objective_power || 40.0;
                            
                            // Downsample at this DZI level: 2^(maxZoom - dziLevel)
                            const downsample = Math.pow(2, maxZoom - dziLevel);
                            
                            // Actual magnification = base / downsample
                            const actualMag = baseMag / downsample;
                            
                            // Format based on magnitude
                            let magText;
                            if (actualMag >= 1.0) {
                                // Show whole numbers for 1× and above
                                magText = actualMag.toFixed(0) + '×';
                            } else if (actualMag >= 0.01) {
                                // Show 2-3 decimals for smaller magnifications
                                magText = actualMag.toFixed(3) + '×';
                            } else {
                                // Scientific notation for very small magnifications
                                magText = actualMag.toExponential(1);
                            }
                            
                            magDisplay.innerHTML = magText;
                        };
                        
                        map.on('zoomend', this._updateMagDisplay, this);
                        this._updateMagDisplay();
                        
                        return container;
                    },
                    
                    onRemove: function(map) {
                        map.off('zoomend', this._updateMagDisplay, this);
                    }
                });
                
                // Add the custom zoom control
                new L.Control.CustomZoom().addTo(state.map);
                console.log('✓ Custom zoom control with magnification display added');
                
                // Set initial view at zoom 0 with center adjusted from metadata
                // Lower Y value = higher on screen in Leaflet
                const adjustedCenterY = centerY * centerOffsetY;
                state.map.setView([adjustedCenterY, centerX], 0);
                console.log('Initial view set with adjusted center:', [adjustedCenterY, centerX], '(offset multiplier:', centerOffsetY + ')');
                
                // Add DZI tile layer with proper coordinate system
                const dziBaseName = data.dzi_url.replace('.dzi', '');
                const baseUrl = 'http://' + window.location.hostname + ':' + data.dzi_server_port + '/' + dziBaseName + '_files';
                
                console.log('DZI base URL:', baseUrl);
                console.log('DZI zoom levels: 0 (small) to', maxZoom, '(full res)');
                
                // Create custom tile layer with DZI-specific getTileUrl and proper edge tile handling
                const DZITileLayer = L.TileLayer.extend({
                    getTileUrl: function(coords) {
                        // Map Leaflet zoom to DZI zoom: DZI zoom = Leaflet zoom + startLevel
                        const dziZoom = coords.z + startLevel;
                        
                        // Calculate how many tiles exist at this DZI zoom level
                        // Tiles double at each level starting from level 9
                        const tilesAtThisZoom = Math.pow(2, Math.max(0, dziZoom - 8));
                        
                        // ONLY accept coordinates in the valid range [0, tilesAtThisZoom)
                        if (coords.x < 0 || coords.x >= tilesAtThisZoom || 
                            coords.y < 0 || coords.y >= tilesAtThisZoom) {
                            return '';  // Don't load tiles outside valid range
                        }
                        
                        // Valid coordinates - request the tile from DZI
                        const url = baseUrl + '/' + dziZoom + '/' + coords.x + '_' + coords.y + '.png';
                        
                        // DETAILED LOGGING for debugging aspect ratio issues
                        if (coords.z <= 2) {  // Only log first few zoom levels to avoid spam
                            console.log(`[TILE] Leaflet zoom=${coords.z}, DZI level=${dziZoom}, ` +
                                       `coords=(${coords.x},${coords.y}), tiles=${tilesAtThisZoom}x${tilesAtThisZoom}, ` +
                                       `url=${dziZoom}/${coords.x}_${coords.y}.png`);
                        }
                        
                        return url;
                    },
                    
                    // CRITICAL FIX: Override createTile to handle variable tile sizes
                    // DZI tiles can be ANY size at ANY zoom level - we must use actual loaded dimensions
                    createTile: function(coords, done) {
                        const tile = document.createElement('img');
                        
                        // Get the tile URL
                        const url = this.getTileUrl(coords);
                        
                        if (!url) {
                            // Empty tile
                            done(null, tile);
                            return tile;
                        }
                        
                        // Calculate image dimensions at this DZI level for reference
                        const dziZoom = coords.z + startLevel;
                        const scaleAtLevel = Math.pow(2, maxZoom - dziZoom);
                        const levelWidth = imageWidth / scaleAtLevel;
                        const levelHeight = imageHeight / scaleAtLevel;
                        
                        // DZI tile configuration
                        const baseTileSize = 256;  // Base tile size without overlap
                        const overlap = 1;  // Standard DZI overlap
                        const fullTileSize = baseTileSize + overlap;  // Expected: 257
                        
                        // Calculate tile grid dimensions
                        const tileCols = Math.ceil(levelWidth / baseTileSize);
                        const tileRows = Math.ceil(levelHeight / baseTileSize);
                        
                        // Calculate expected dimensions (for reference/debugging only)
                        let expectedWidth, expectedHeight;
                        
                        if (coords.x < tileCols - 1) {
                            expectedWidth = fullTileSize;
                        } else {
                            const remainingWidth = levelWidth - (coords.x * baseTileSize);
                            expectedWidth = Math.ceil(Math.min(remainingWidth + overlap, fullTileSize));
                        }
                        
                        if (coords.y < tileRows - 1) {
                            expectedHeight = fullTileSize;
                        } else {
                            const remainingHeight = levelHeight - (coords.y * baseTileSize);
                            expectedHeight = Math.ceil(Math.min(remainingHeight + overlap, fullTileSize));
                        }
                        
                        // Set tile properties
                        tile.alt = '';
                        tile.setAttribute('role', 'presentation');
                        
                        // **KEY FIX**: Hide tile until we know its actual dimensions
                        tile.style.visibility = 'hidden';
                        
                        // Load the image and use its ACTUAL dimensions
                        L.DomEvent.on(tile, 'load', function() {
                            // Get actual loaded image dimensions - THIS is the truth
                            const actualWidth = tile.naturalWidth;
                            const actualHeight = tile.naturalHeight;
                            
                            // Set exact dimensions based on what was actually loaded
                            tile.width = actualWidth;
                            tile.height = actualHeight;
                            tile.style.width = actualWidth + 'px';
                            tile.style.height = actualHeight + 'px';
                            tile.style.maxWidth = actualWidth + 'px';
                            tile.style.maxHeight = actualHeight + 'px';
                            tile.style.minWidth = actualWidth + 'px';
                            tile.style.minHeight = actualHeight + 'px';
                            
                            // Now show the properly sized tile
                            tile.style.visibility = 'visible';
                            
                            // Debug logging at low zoom levels
                            if (coords.z <= 2) {
                                const mismatch = (actualWidth !== expectedWidth || actualHeight !== expectedHeight);
                                if (mismatch) {
                                    console.log(`[TILE SIZE] DZI level ${dziZoom}, tile (${coords.x},${coords.y}): ` +
                                               `Expected ${expectedWidth}×${expectedHeight}px, ` +
                                               `Got ${actualWidth}×${actualHeight}px ` +
                                               `(grid: ${tileCols}×${tileRows}, level: ${Math.round(levelWidth)}×${Math.round(levelHeight)})`);
                                }
                            }
                            
                            this._tileOnLoad(done, tile);
                        }.bind(this));
                        
                        L.DomEvent.on(tile, 'error', function(e) {
                            console.error(`[TILE ERROR] DZI level ${dziZoom}, tile (${coords.x},${coords.y}): ${url}`);
                            this._tileOnError(done, tile, e);
                        }.bind(this));
                        
                        if (this.options.crossOrigin || this.options.crossOrigin === '') {
                            tile.crossOrigin = this.options.crossOrigin === true ? '' : this.options.crossOrigin;
                        }
                        
                        tile.src = url;
                        
                        return tile;
                    }
                });
                
                // Create tile layer with proper edge tile handling
                state.tileLayer = new DZITileLayer('', {
                    tileSize: 257,  // Standard tile size (DZI tiles with 1px overlap)
                    noWrap: true,
                    minNativeZoom: 0,
                    maxNativeZoom: maxZoom - startLevel,
                    tms: false,
                    updateWhenIdle: false,  // Update tiles while panning
                    updateWhenZooming: true,  // Update tiles while zooming
                    keepBuffer: 2  // Keep 2 tile rows/cols around viewport
                }).addTo(state.map);
                
                console.log('DZI tile layer added with edge tile handling');
                console.log('Map center:', state.map.getCenter());
                console.log('Map zoom:', state.map.getZoom());
                console.log('Map pixel bounds:', state.map.getPixelBounds());
                console.log('Map size:', state.map.getSize());
                
                // Log on every zoom to see coordinate space changes
                state.map.on('zoomend', function() {
                    const zoom = state.map.getZoom();
                    const center = state.map.getCenter();
                    const bounds = state.map.getBounds();
                    const pixelBounds = state.map.getPixelBounds();
                    console.log(`[ZOOM] Level=${zoom}, Center=[${center.lat.toFixed(1)}, ${center.lng.toFixed(1)}], ` +
                               `Bounds=${JSON.stringify([[bounds.getSouth().toFixed(1), bounds.getWest().toFixed(1)], ` +
                               `[bounds.getNorth().toFixed(1), bounds.getEast().toFixed(1)]])}, ` +
                               `PixelBounds=${JSON.stringify(pixelBounds)}`);
                });
            
            // Update zoom indicator
            function updateZoomInfo() {
                if (!state.map) return;
                try {
                    const currentZoom = state.map.getZoom();
                    if (typeof currentZoom === 'undefined' || isNaN(currentZoom)) return;
                    
                    // Calculate DZI level from Leaflet zoom
                    const dziLevel = startLevel + Math.floor(currentZoom);
                    const magnification = Math.pow(2, currentZoom);
                    const zoomText = `Level ${dziLevel} (${magnification.toFixed(2)}x)`;
                    
                    // Update Panel parameters
                    if (data) {
                        if (typeof data.zoom_level !== 'undefined') {
                            data.zoom_level = zoomText;
                        }
                        if (typeof data.zoom !== 'undefined') {
                            data.zoom = Math.floor(currentZoom);
                        }
                    }
                    
                    console.log('Zoom updated - Leaflet zoom:', currentZoom, 'DZI level:', dziLevel, 'Magnification:', magnification.toFixed(2) + 'x');
                } catch (e) {
                    console.error('Error in updateZoomInfo:', e);
                }
            }
            
            // Event listeners
            state.map.on('zoom', updateZoomInfo);
            state.map.on('zoomend', updateZoomInfo);  // Also update on zoomend
            state.map.on('move', () => {
                if (!state.map) return;
                const center = state.map.getCenter();
                data.center = [center.lat, center.lng];
            });
            
            // Initialize zoom display
            updateZoomInfo();
            
            // Initialize minimap from external module
            if (typeof initializeMiniMap === 'function') {
                initializeMiniMap(state.map, DZITileLayer, imageWidth, imageHeight, startLevel, maxZoom, state);
            } else {
                console.error('initializeMiniMap function not found. Make sure minimap_overview.js is loaded.');
            }
            
            // Initialize scale bar from external module
            // mm/pixel ratio at base resolution (DZI max zoom level)
            const mmPerPixel = data.mm_per_pixel || 0.0004;
            
            console.log('Using mm_per_pixel from metadata:', mmPerPixel);

            if (typeof initializeScaleBar === 'function') {
                initializeScaleBar(state.map, mmPerPixel, startLevel, maxZoom);
            } else {
                console.error('initializeScaleBar function not found. Make sure scale_bar.js is loaded.');
            }
            
            // ADD DRAWING CAPABILITIES
            // Create feature group to store drawn items
            state.drawnItems = new L.FeatureGroup();
            state.map.addLayer(state.drawnItems);
            
            // Initialize freehand drawing from external module
            if (typeof initializeFreehandDrawing === 'function') {
                initializeFreehandDrawing(state.map, state.drawnItems);
                console.log('Map initialized successfully with freehand drawing tool');
            } else {
                console.error('initializeFreehandDrawing function not found. Make sure freehand_drawing.js is loaded.');
            }
            
            // ANNOTATION SAVE/LOAD FUNCTIONS
            window.getAnnotationsData = function() {
                if (!state.drawnItems) return null;
                
                const annotations = [];
                state.drawnItems.eachLayer(function(layer) {
                    if (layer instanceof L.Polyline) {
                        const geojson = layer.toGeoJSON();
                        annotations.push({
                            type: 'polyline',
                            coordinates: geojson.geometry.coordinates,
                            color: layer.options.originalColor || layer.options.color,
                            weight: layer.options.originalWeight || layer.options.weight
                        });
                    }
                });
                
                const currentZoom = state.map.getZoom();
                const currentCenter = state.map.getCenter();
                
                return {
                    image_name: data.image_name,
                    zoom: currentZoom,
                    center: [currentCenter.lat, currentCenter.lng],
                    annotations: annotations,
                    timestamp: new Date().toISOString()
                };
            };
            
            window.loadAnnotationsData = function(data) {
                if (!state.drawnItems || !state.map) return;
                
                console.log('Loading annotations:', data);
                
                // Clear existing annotations
                state.drawnItems.clearLayers();
                
                // Load annotations
                if (data.annotations && data.annotations.length > 0) {
                    data.annotations.forEach(function(anno) {
                        if (anno.type === 'polyline') {
                            // Convert GeoJSON coordinates to LatLng
                            const latlngs = anno.coordinates.map(function(coord) {
                                return [coord[1], coord[0]]; // GeoJSON is [lng, lat], Leaflet is [lat, lng]
                            });
                            
                            const polyline = L.polyline(latlngs, {
                                color: anno.color,
                                weight: anno.weight,
                                originalColor: anno.color,
                                originalWeight: anno.weight
                            });
                            
                            state.drawnItems.addLayer(polyline);
                        }
                    });
                    console.log('Loaded', data.annotations.length, 'annotations');
                }
                
                // Restore view if available
                if (data.zoom !== undefined && data.center) {
                    state.map.setView(data.center, data.zoom);
                    console.log('Restored view: zoom', data.zoom, 'center', data.center);
                }
            };
            
            } // End of initializeMap function
            
            // Start the initialization process
            initializeMap();
        """,
        
        'dzi_url': """
            // When dzi_url changes, force re-initialization
            console.log('=== DZI URL CHANGED ===');
            console.log('New dzi_url:', data.dzi_url);
            
            // Only re-initialize if we have a valid map already
            // This prevents re-initialization on sidebar toggle
            if (state.map) {
                console.log('Map exists, triggering re-initialization...');
                // Trigger after_layout to re-initialize the map
                self.after_layout();
            } else {
                console.log('No map yet, skipping re-initialization (will initialize on first render)');
            }
        """,
        
        'save_annotation_trigger': """
            // Triggered when save is requested from Python
            console.log('Save annotation trigger:', data.save_annotation_trigger);
            if (typeof window.getAnnotationsData === 'function') {
                const annotationsData = window.getAnnotationsData();
                if (annotationsData) {
                    // Send data back to Python
                    data.annotation_data = JSON.stringify(annotationsData);
                    console.log('Annotations data sent to Python');
                } else {
                    console.log('No annotations to save');
                    data.annotation_data = JSON.stringify({
                        zoom: state.map ? state.map.getZoom() : 0,
                        center: state.map ? [state.map.getCenter().lat, state.map.getCenter().lng] : [0, 0],
                        annotations: [],
                        timestamp: new Date().toISOString()
                    });
                }
            }
        """,
        
        'load_annotation_trigger': """
            // Triggered when load is requested from Python
            console.log('Load annotation trigger:', data.load_annotation_trigger);
            if (data.annotation_data && typeof window.loadAnnotationsData === 'function') {
                try {
                    const annotationsData = JSON.parse(data.annotation_data);
                    
                    // Check if this is a special action (like toggle_minimap)
                    if (annotationsData.action === 'toggle_minimap') {
                        console.log('🗺️  Toggle minimap action received');
                        if (typeof state !== 'undefined' && state.miniMap && state.miniMap._toggleButton) {
                            state.miniMap._toggleButton.click();
                            console.log('✓ Minimap toggled via keyboard shortcut');
                        } else {
                            console.warn('⚠️ Minimap not available or not initialized');
                        }
                    } else {
                        // Normal annotation loading
                        window.loadAnnotationsData(annotationsData);
                        console.log('Annotations loaded successfully');
                    }
                } catch (e) {
                    console.error('Error loading annotations:', e);
                }
            }
        """
    }
    
    __css__ = [
        'https://unpkg.com/leaflet@1.7.1/dist/leaflet.css'
    ]
    __javascript__ = [
        'https://unpkg.com/leaflet@1.7.1/dist/leaflet.js'
    ]
