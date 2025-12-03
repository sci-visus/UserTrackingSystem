/**
 * MiniMap Overview Module for Leaflet Map
 * 
 * Provides an overview minimap showing the entire image with viewport indicator.
 * 
 * Usage:
 *   initializeMiniMap(map, DZITileLayer, imageWidth, imageHeight, startLevel, maxZoom, state)
 */

(function() {
    'use strict';
    
    // IMMEDIATELY define the plugin - don't wait for any conditions
    console.log('Loading WorldMiniMap module...');
    
    // Force immediate definition
    if (typeof L !== 'undefined') {
        console.log('Defining L.Control.WorldMiniMap inline...');
        
        L.Control.WorldMiniMap = L.Control.extend({
            options: {
                position: 'bottomright',
                width: 300,
                height: 200,
                collapsedWidth: 30,
                collapsedHeight: 30,
                toggleDisplay: true,
                zoomLevelFixed: 0,
                centerFixed: true,
                layer: null,
                aimingRectOptions: {
                    color: '#ff0000',
                    weight: 2,
                    fillOpacity: 0.1,
                    interactive: false
                },
                shadowRectOptions: {
                    color: '#000000',
                    weight: 1,
                    fillOpacity: 0,
                    opacity: 0
                },
                strings: {
                    hideText: 'Hide with Key "V"',
                    showText: 'Show with Key "V"'
                }
            },
            
            initialize: function(options) {
                L.Util.setOptions(this, options);
                this._minimized = false;
                console.log('WorldMiniMap initialized with options:', this.options);
            },
            
            onAdd: function(map) {
                this._mainMap = map;
                console.log('WorldMiniMap onAdd called');
                console.log('Main map CRS:', this._mainMap.options.crs);
                console.log('Main map center:', this._mainMap.getCenter());
                console.log('Main map zoom:', this._mainMap.getZoom());
                console.log('Main map bounds:', this._mainMap.getBounds());
                
                // Create main container
                this._container = L.DomUtil.create('div', 'leaflet-control-worldminimap');
                this._container.style.position = 'relative';
                this._container.style.width = this.options.width + 'px';
                this._container.style.height = this.options.height + 'px';
                
                // Prevent events from propagating to main map
                L.DomEvent.disableClickPropagation(this._container);
                L.DomEvent.disableScrollPropagation(this._container);
                
                // Create minimap content wrapper (this will be hidden on minimize)
                this._mapContainer = L.DomUtil.create('div', 'leaflet-control-worldminimap-content', this._container);
                this._mapContainer.style.width = '100%';
                this._mapContainer.style.height = '100%';
                this._mapContainer.style.backgroundColor = '#f8f8f9';
                this._mapContainer.style.border = '2px solid rgba(0,0,0,0.2)';
                this._mapContainer.style.borderRadius = '4px';
                this._mapContainer.style.overflow = 'hidden';
                this._mapContainer.style.boxShadow = '0 1px 5px rgba(0,0,0,0.4)';
                
                // Create minimap with same CRS as main map
                console.log('Creating minimap with CRS:', this._mainMap.options.crs);
                this._miniMap = L.map(this._mapContainer, {
                    crs: this._mainMap.options.crs,
                    zoomControl: false,
                    attributionControl: false,
                    dragging: false, //!this.options.centerFixed,
                    scrollWheelZoom: false,
                    doubleClickZoom: false,
                    boxZoom: false,
                    keyboard: false,
                    touchZoom: false,
                    zoomAnimation: false
                });
                
                console.log('Minimap created');
                
                // Add layer to minimap
                if (this.options.layer) {
                    console.log('Adding layer to minimap:', this.options.layer);
                    this.options.layer.addTo(this._miniMap);
                    console.log('✓ Minimap tile layer added');
                    
                    // Add tile loading event listeners for debugging
                    this.options.layer.on('tileloadstart', function(e) {
                        console.log('Minimap tile load start:', e.coords);
                    });
                    this.options.layer.on('tileload', function(e) {
                        console.log('Minimap tile loaded:', e.coords);
                    });
                    this.options.layer.on('tileerror', function(e) {
                        console.error('Minimap tile error:', e.coords, e.error);
                    });
                } else {
                    console.error('❌ No layer provided to minimap!');
                }
                
                // Add toggle button if enabled (added AFTER map container, so it stays on top)
                if (this.options.toggleDisplay) {
                    this._addToggleButton();
                }
                
                // Set view BEFORE whenReady to ensure proper initialization
                const mainCenter = this._mainMap.getCenter();
                const mainBounds = this._mainMap.getBounds();
                
                console.log('Setting initial minimap view to center:', mainCenter, 'zoom:', this.options.zoomLevelFixed);
                this._miniMap.setView(mainCenter, this.options.zoomLevelFixed, {animate: false});
                
                // Wait for minimap to be ready before setting up viewport tracking
                this._miniMap.whenReady(L.Util.bind(function() {
                    console.log('✓ Minimap ready, setting up viewport tracking...');
                    console.log('Minimap view after ready - center:', this._miniMap.getCenter(), 'zoom:', this._miniMap.getZoom());
                    console.log('Minimap bounds:', this._miniMap.getBounds());
                    
                    // Create viewport rectangle showing main map bounds
                    console.log('Creating viewport rectangle with bounds:', mainBounds);
                    this._viewportRect = L.rectangle(
                        mainBounds,
                        this.options.aimingRectOptions
                    ).addTo(this._miniMap);
                    console.log('✓ Viewport rectangle created');
                    
                    // Bind main map events to update minimap
                    this._mainMap.on('moveend', this._onMainMapMove, this);
                    this._mainMap.on('zoomend', this._onMainMapMove, this);
                    
                    // Initial update
                    this._update();
                    
                    // Force minimap to recalculate size
                    setTimeout(L.Util.bind(function() {
                        console.log('Invalidating minimap size...');
                        this._miniMap.invalidateSize();
                        this._update();
                        console.log('✓ Minimap initialized and sized');
                        console.log('Final minimap state - center:', this._miniMap.getCenter(), 'zoom:', this._miniMap.getZoom());
                    }, this), 100);
                    
                }, this));
                
                return this._container;
            },
            
            onRemove: function(map) {
                console.log('WorldMiniMap onRemove called');
                this._mainMap.off('moveend', this._onMainMapMove, this);
                this._mainMap.off('zoomend', this._onMainMapMove, this);
                
                if (this._miniMap) {
                    this._miniMap.remove();
                }
            },
            
            _addToggleButton: function() {
                // Create toggle button at container level (not inside map container)
                this._toggleButton = L.DomUtil.create('a', 'leaflet-control-worldminimap-toggle', this._container);
                this._toggleButton.href = '#';
                this._toggleButton.innerHTML = '◀';
                this._toggleButton.title = this.options.strings.hideText;
                
                // Style toggle button - positioned absolutely within container
                this._toggleButton.style.position = 'absolute';
                this._toggleButton.style.top = '0';
                this._toggleButton.style.right = '0';
                this._toggleButton.style.width = this.options.collapsedWidth + 'px';
                this._toggleButton.style.height = this.options.collapsedHeight + 'px';
                this._toggleButton.style.backgroundColor = 'white';
                this._toggleButton.style.border = '2px solid #666';
                this._toggleButton.style.borderRadius = '3px';
                this._toggleButton.style.color = '#666';
                this._toggleButton.style.fontSize = '16px';
                this._toggleButton.style.fontWeight = 'bold';
                this._toggleButton.style.display = 'flex';
                this._toggleButton.style.alignItems = 'center';
                this._toggleButton.style.justifyContent = 'center';
                this._toggleButton.style.cursor = 'pointer';
                this._toggleButton.style.textDecoration = 'none';
                this._toggleButton.style.zIndex = '1000';
                this._toggleButton.style.boxShadow = '0 1px 3px rgba(0,0,0,0.3)';
                
                L.DomEvent.on(this._toggleButton, 'click', this._toggle, this);
                L.DomEvent.disableClickPropagation(this._toggleButton);
            },
            
            _toggle: function(e) {
                L.DomEvent.preventDefault(e);
                L.DomEvent.stopPropagation(e);
                
                if (this._minimized) {
                    this._restore();
                } else {
                    this._minimize();
                }
            },
            
            _minimize: function() {
                console.log('Minimizing minimap');
                
                // Hide the map content, but keep the container at button size
                this._mapContainer.style.display = 'none';
                
                // Resize container to just fit the button
                this._container.style.width = this.options.collapsedWidth + 'px';
                this._container.style.height = this.options.collapsedHeight + 'px';
                
                // Update button
                this._toggleButton.innerHTML = '▶';
                this._toggleButton.title = this.options.strings.showText;
                
                this._minimized = true;
            },
            
            _restore: function() {
                console.log('Restoring minimap');
                
                // Restore container size
                this._container.style.width = this.options.width + 'px';
                this._container.style.height = this.options.height + 'px';
                
                // Show the map content
                this._mapContainer.style.display = 'block';
                
                // Update button
                this._toggleButton.innerHTML = '◀';
                this._toggleButton.title = this.options.strings.hideText;
                
                this._minimized = false;
                
                // Recalculate minimap size after showing
                if (this._miniMap) {
                    this._miniMap.invalidateSize();
                    this._update();
                }
            },
            
            _onMainMapMove: function() {
                if (!this._minimized) {
                    this._update();
                }
            },
            
            _update: function() {
                if (this._minimized || !this._viewportRect || !this._miniMap) {
                    return;
                }
                
                // Update viewport rectangle to match main map bounds
                const mainBounds = this._mainMap.getBounds();
                this._viewportRect.setBounds(mainBounds);
                
                // Update minimap center if not fixed
                //if (!this.options.centerFixed) {
                    //const mainCenter = this._mainMap.getCenter();
                    //this._miniMap.panTo(mainCenter);
                //}
            }
        });
        
        // Factory function
        L.control.worldMiniMap = function(options) {
            return new L.Control.WorldMiniMap(options);
        };
        
        // Also expose as MiniMap for compatibility with existing check
        L.Control.MiniMap = L.Control.WorldMiniMap;
        L.control.miniMap = L.control.worldMiniMap;
        
        console.log('✓ L.Control.WorldMiniMap defined');
        console.log('✓ L.Control.MiniMap alias created for compatibility');
    } else {
        console.error('❌ Leaflet (L) is not available!');
    }
    
    /**
     * Initialize minimap with retry logic
     */
    window.initializeMiniMap = function(map, DZITileLayer, imageWidth, imageHeight, startLevel, maxZoom, state) {
        console.log('=== Initializing WorldMiniMap ===');
        console.log('  imageWidth:', imageWidth, 'imageHeight:', imageHeight);
        console.log('  startLevel:', startLevel, 'maxZoom:', maxZoom);
        console.log('  Main map zoom:', map.getZoom());
        console.log('  Main map center:', map.getCenter());
        console.log('  DZITileLayer:', DZITileLayer);
        
        function tryAddMiniMap(attempt) {
            attempt = attempt || 1;
            console.log('Checking for WorldMiniMap plugin (attempt ' + attempt + ')...');
            
            if (typeof L.Control.WorldMiniMap !== 'undefined' || typeof L.Control.MiniMap !== 'undefined') {
                console.log('✓ MiniMap plugin is available, creating minimap...');
                
                try {
                    // Remove existing minimap if it exists
                    if (state.miniMap) {
                        console.log('Removing existing minimap...');
                        map.removeControl(state.miniMap);
                        state.miniMap = null;
                    }
                    
                    // Create a separate tile layer for the minimap with DEBUGGING
                    console.log('Creating minimap tile layer with:', {
                        tileSize: 257,
                        noWrap: true,
                        minNativeZoom: 0,
                        maxNativeZoom: maxZoom - startLevel,
                        tms: false
                    });
                    
                    const minimapLayer = new DZITileLayer('', {
                        tileSize: 257,
                        noWrap: true,
                        minNativeZoom: 0,
                        maxNativeZoom: maxZoom - startLevel,
                        tms: false
                    });
                    
                    // Add debug event listeners
                    minimapLayer.on('tileloadstart', function(e) {
                        console.log('Minimap DZI tile load start:', e.coords);
                    });
                    minimapLayer.on('tileload', function(e) {
                        console.log('Minimap DZI tile loaded successfully:', e.coords);
                    });
                    minimapLayer.on('tileerror', function(e) {
                        console.error('Minimap DZI tile error:', e.coords, e.tile.src, e.error);
                    });
                    
                    console.log('✓ WorldMiniMap tile layer created');
                    
                    // Create WorldMiniMap control
                    const miniMap = L.control.worldMiniMap({
                        position: 'bottomright',
                        width: 300,
                        height: 200,
                        collapsedWidth: 30,
                        collapsedHeight: 30,
                        toggleDisplay: true,
                        zoomLevelFixed: 0,  // Always show at zoom level 0 (full image)
                        centerFixed: false,  // Follow main map center
                        layer: minimapLayer,
                        aimingRectOptions: {
                            color: '#ff0000',
                            weight: 2,
                            fillOpacity: 0.1,
                            interactive: false
                        }
                    }).addTo(map);
                    
                    // Store reference
                    state.miniMap = miniMap;
                    
                    console.log('✓ WorldMiniMap overlay added to map');
                    console.log('=== WorldMiniMap initialization complete ===');
                } catch (e) {
                    console.error('❌ Failed to create WorldMiniMap:', e);
                    console.error('Error details:', e.message);
                    console.error('Stack trace:', e.stack);
                }
            } else {
                if (attempt < 10) {
                    console.log('⏳ WorldMiniMap not ready yet, retrying in 200ms...');
                    setTimeout(function() { tryAddMiniMap(attempt + 1); }, 200);
                } else {
                    console.warn('⚠️ L.Control.WorldMiniMap not available after 10 attempts');
                }
            }
        }
        
        // Try to add minimap after a short delay
        setTimeout(function() { tryAddMiniMap(1); }, 500);
    };
    
})();