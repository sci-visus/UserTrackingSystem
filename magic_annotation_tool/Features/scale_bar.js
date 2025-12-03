/**
 * Custom Scale Bar Module for Leaflet Map
 * 
 * Provides a scale bar that automatically adjusts units (nm, μm, mm, cm)
 * based on the current zoom level and image resolution.
 * 
 * Usage:
 *   initializeScaleBar(map, mmPerPixel, startLevel, maxZoom)
 * 
 * Parameters:
 *   - map: Leaflet map instance
 *   - mmPerPixel: mm/pixel ratio at base resolution (DZI max zoom level)
 *   - startLevel: DZI level to use as Leaflet zoom 0
 *   - maxZoom: Maximum DZI zoom level
 */

(function() {
    'use strict';
    
    /**
     * Initialize scale bar on the map
     * @param {L.Map} map - Leaflet map instance
     * @param {number} mmPerPixel - mm/pixel ratio at base resolution
     * @param {number} startLevel - DZI level at Leaflet zoom 0
     * @param {number} maxZoom - Maximum DZI zoom level
     */
    window.initializeScaleBar = function(map, mmPerPixel, startLevel, maxZoom) {
        console.log('Initializing custom scale bar...');
        console.log('  mmPerPixel:', mmPerPixel);
        console.log('  startLevel:', startLevel);
        console.log('  maxZoom:', maxZoom);
        
        // Define custom scale bar control
        L.Control.CustomScaleBar = L.Control.extend({
            options: {
                position: 'bottomleft',
                maxWidth: 200,
                metric: true
            },
            
            onAdd: function(mapInstance) {
                this._map = mapInstance;
                this._container = L.DomUtil.create('div', 'leaflet-control-scale leaflet-bar');
                this._container.style.fontSize = '11px';
                this._container.style.lineHeight = '1.1';
                this._container.style.padding = '5px 10px';
                this._container.style.background = 'rgba(255, 255, 255, 0.8)';
                this._container.style.borderRadius = '4px';
                
                mapInstance.on('zoom zoomend move', this._update, this);
                this._update();
                
                return this._container;
            },
            
            onRemove: function(mapInstance) {
                mapInstance.off('zoom zoomend move', this._update, this);
            },
            
            _update: function() {
                const currentMap = this._map;
                const maxWidth = this.options.maxWidth;
                
                // Get current zoom scale factor
                const zoom = currentMap.getZoom();
                const dziZoom = startLevel + zoom;
                const scale = Math.pow(2, dziZoom - maxZoom);  // Scale relative to full resolution
                
                // Calculate effective mm per screen pixel
                const effectiveMmPerScreenPixel = mmPerPixel / scale;
                
                // Calculate distance in mm for maxWidth pixels
                let distanceMm = maxWidth * effectiveMmPerScreenPixel;
                
                // Auto-select unit and round to nice number
                let label, width;
                
                if (distanceMm < 0.001) {
                    // Use nanometers
                    const nm = distanceMm * 1000000;
                    const rounded = this._getRoundNum(nm);
                    label = rounded + ' nm';
                    width = (rounded / nm) * maxWidth;
                } else if (distanceMm < 1) {
                    // Use micrometers
                    const um = distanceMm * 1000;
                    const rounded = this._getRoundNum(um);
                    label = rounded + ' μm';
                    width = (rounded / um) * maxWidth;
                } else if (distanceMm < 1000) {
                    // Use millimeters
                    const rounded = this._getRoundNum(distanceMm);
                    label = rounded + ' mm';
                    width = (rounded / distanceMm) * maxWidth;
                } else {
                    // Use centimeters
                    const cm = distanceMm / 10;
                    const rounded = this._getRoundNum(cm);
                    label = rounded + ' cm';
                    width = (rounded / cm) * maxWidth;
                }
                
                this._container.innerHTML = 
                    '<div style="border-bottom: 2px solid #777; border-left: 2px solid #777; border-right: 2px solid #777; height: 5px; width: ' + width + 'px;"></div>' +
                    '<div style="text-align: center; margin-top: 2px;">' + label + '</div>';
            },
            
            _getRoundNum: function(num) {
                const pow10 = Math.pow(10, (Math.floor(num) + '').length - 1);
                let d = num / pow10;
                
                d = d >= 10 ? 10 :
                    d >= 5 ? 5 :
                    d >= 3 ? 3 :
                    d >= 2 ? 2 : 1;
                
                return pow10 * d;
            }
        });
        
        // Add the custom scale bar to the map
        const scaleBar = new L.Control.CustomScaleBar({
            position: 'bottomleft',
            maxWidth: 200
        }).addTo(map);
        
        console.log('✓ Custom scale bar added');
        
        return scaleBar;
    };
    
})();
