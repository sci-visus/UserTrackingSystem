// Freehand Drawing Module for Leaflet
// This module provides freehand drawing capabilities with pen cursor and Shift key support

(function() {
    'use strict';
    
    // Variables for freehand drawing
    let freehandMode = false;
    let shiftPressed = false;
    let isDrawing = false;
    let freehandLine = null;
    let points = [];
    let selectedLayer = null;
    let currentLineColor = '#ffff00';
    let currentLineThickness = 4;
    
    // Thickness presets (mapped to keys 1-5)
    const thicknesses = [2, 4, 6, 8, 10];
    
    // Color palette
    const colorPalette = [
        { color: '#FFFF00', name: 'Yellow' },
        { color: '#FF0000', name: 'Red' },
        { color: '#00FF00', name: 'Green' },
        { color: '#0000FF', name: 'Blue' },
        { color: '#FF00FF', name: 'Magenta' },
        { color: '#00FFFF', name: 'Cyan' },
        { color: '#FFA500', name: 'Orange' },
        { color: '#800080', name: 'Purple' },
        { color: '#077a24ff', name: 'Dark Green' },
        { color: '#000000', name: 'Black' }
    ];
    let currentColorIndex = 0;
    
    // Freehand Button Control
    L.Control.FreehandButton = L.Control.extend({
        options: {
            position: 'topright'
        },
        
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
            const button = L.DomUtil.create('a', 'leaflet-draw-draw-polyline', container);
            button.href = '#';
            button.title = 'Freehand drawing (or hold Shift key)';
            button.innerHTML = '✏️';
            button.style.fontSize = '18px';
            button.style.lineHeight = '26px';
            button.style.textAlign = 'center';
            button.style.textDecoration = 'none';
            button.style.backgroundColor = 'white';
            button.style.width = '30px';
            button.style.height = '30px';
            button.style.display = 'block';
            
            button.onclick = function(e) {
                L.DomEvent.stopPropagation(e);
                L.DomEvent.preventDefault(e);
                
                freehandMode = !freehandMode;
                if (freehandMode) {
                    button.style.backgroundColor = '#ffcccc';
                    map.dragging.disable();
                    map.getContainer().classList.add('pen-cursor');
                    console.log('Freehand mode ON - Click and drag to draw');
                } else {
                    button.style.backgroundColor = 'white';
                    map.dragging.enable();
                    map.getContainer().classList.remove('pen-cursor');
                    console.log('Freehand mode OFF');
                }
            };
            
            return container;
        }
    });
    
    // Clear All Button Control
    L.Control.ClearAllButton = L.Control.extend({
        options: {
            position: 'topleft'
        },
        
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
            const button = L.DomUtil.create('a', '', container);
            button.href = '#';
            button.title = 'Clear all drawings\n(Ctrl/Cmd + Alt + Backspace)';
            button.innerHTML = '❌';
            button.style.fontSize = '18px';
            button.style.lineHeight = '26px';
            button.style.textAlign = 'center';
            button.style.textDecoration = 'none';
            button.style.backgroundColor = 'white';
            button.style.width = '30px';
            button.style.height = '30px';
            button.style.display = 'block';
            
            this._button = button;
            return container;
        }
    });
    
    // Delete Selected Line Button Control
    L.Control.DeleteLineButton = L.Control.extend({
        options: {
            position: 'topright'
        },
        
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
            const button = L.DomUtil.create('a', '', container);
            button.href = '#';
            button.title = 'Delete selected line (or press Backspace)';
            button.innerHTML = '🗑️';
            button.style.fontSize = '18px';
            button.style.lineHeight = '26px';
            button.style.textAlign = 'center';
            button.style.textDecoration = 'none';
            button.style.backgroundColor = 'white';
            button.style.width = '30px';
            button.style.height = '30px';
            button.style.display = 'block';
            button.style.opacity = '0.5';
            button.style.cursor = 'not-allowed';
            
            this._button = button;
            return container;
        },
        
        enable: function() {
            this._button.style.opacity = '1';
            this._button.style.cursor = 'pointer';
        },
        
        disable: function() {
            this._button.style.opacity = '0.5';
            this._button.style.cursor = 'not-allowed';
        }
    });
    
    // Line Thickness Control
    L.Control.LineThicknessControl = L.Control.extend({
        options: {
            position: 'topright'
        },
        
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
            container.style.backgroundColor = 'white';
            container.style.padding = '5px';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.gap = '5px';
            container.title = 'press Key (1-7) to change';
            
            const label = L.DomUtil.create('label', '', container);
            label.innerHTML = 'Size:';
            label.style.fontSize = '11px';
            label.style.fontWeight = 'bold';
            label.style.marginBottom = '2px';
            
            // Dropdown button to show current selection
            const dropdownButton = L.DomUtil.create('button', '', container);
            dropdownButton.style.display = 'flex';
            dropdownButton.style.alignItems = 'center';
            dropdownButton.style.padding = '5px 8px';
            dropdownButton.style.border = '1px solid #ccc';
            dropdownButton.style.backgroundColor = 'white';
            dropdownButton.style.cursor = 'pointer';
            dropdownButton.style.borderRadius = '3px';
            dropdownButton.style.width = '40px';
            dropdownButton.style.justifyContent = 'space-between';
            
            const buttonCircle = L.DomUtil.create('div', '', dropdownButton);
            buttonCircle.style.width = '5px';
            buttonCircle.style.height = '5px';
            buttonCircle.style.borderRadius = '50%';
            buttonCircle.style.backgroundColor = 'black';
            buttonCircle.style.marginRight = '6px';
            
            const buttonText = L.DomUtil.create('span', '', dropdownButton);
            buttonText.innerText = '4';
            buttonText.style.fontSize = '11px';
            buttonText.style.flexGrow = '1';
            
            const buttonArrow = L.DomUtil.create('span', '', dropdownButton);
            buttonArrow.innerText = '▼';
            buttonArrow.style.fontSize = '8px';
            buttonArrow.style.marginLeft = '4px';
            
            // Dropdown menu (hidden by default)
            const dropdown = L.DomUtil.create('div', 'custom-dropdown', container);
            dropdown.style.display = "none";
            dropdown.style.flexDirection = "row";
            dropdown.style.border = "1px solid #ccc";
            dropdown.style.padding = "8px";
            dropdown.style.gap = "8px";
            dropdown.style.backgroundColor = "white";
            dropdown.style.position = "absolute";
            dropdown.style.zIndex = "1000";
            dropdown.style.marginTop = "2px";
            dropdown.style.boxShadow = "0 2px 4px rgba(0,0,0,0.2)";
            dropdown.style.borderRadius = "3px";
            dropdown.style.alignItems = "center";
            dropdown.style.right = "0";
            dropdown.style.left = "auto";
            
            // Toggle dropdown on button click
            dropdownButton.onclick = function(e) {
                e.stopPropagation();
                if (dropdown.style.display === "none") {
                    dropdown.style.display = "flex";
                    buttonArrow.innerText = '▲';
                } else {
                    dropdown.style.display = "none";
                    buttonArrow.innerText = '▼';
                }
            };
            
            thicknesses.forEach((t, index) => {
                const item = L.DomUtil.create('div', 'dropdown-item', dropdown);
                item.style.display = 'flex';
                item.style.flexDirection = 'column';
                item.style.alignItems = 'center';
                item.style.cursor = 'pointer';
                item.style.padding = '6px';
                item.style.borderRadius = '3px';
                item.style.minWidth = '35px';
                item.title = `${t}`;
                
                // Highlight selected item
                if (t === 5) {
                    item.style.backgroundColor = '#e6f2ff';
                }
                
                item.onmouseover = function() {
                    if (currentLineThickness !== t) {
                        this.style.backgroundColor = '#f0f0f0';
                    }
                };
                
                item.onmouseout = function() {
                    if (currentLineThickness !== t) {
                        this.style.backgroundColor = 'transparent';
                    } else {
                        this.style.backgroundColor = '#e6f2ff';
                    }
                };
                
                // Add circle icon
                const circle = L.DomUtil.create('div', '', item);
                circle.style.width = `${t}px`;
                circle.style.height = `${t}px`;
                circle.style.borderRadius = "50%";
                circle.style.background = "black";
                circle.style.marginBottom = "4px";
                circle.style.flexShrink = "0";
                
                // Add label with number (1, 2, 3, etc.)
                const txt = L.DomUtil.create('span', '', item);
                txt.innerText = `${index + 1}`;
                txt.style.fontSize = '10px';
                
                item.onclick = function() {
                    currentLineThickness = t;
                    console.log("Thickness:", t);
                    
                    // Update button display
                    buttonCircle.style.width = `${t}px`;
                    buttonCircle.style.height = `${t}px`;
                    buttonText.innerText = `${index + 1}`;
                    
                    // Update selection highlight
                    Array.from(dropdown.children).forEach(child => {
                        child.style.backgroundColor = 'transparent';
                    });
                    this.style.backgroundColor = '#e6f2ff';
                    
                    // Close dropdown
                    dropdown.style.display = "none";
                    buttonArrow.innerText = '▼';
                };
            });
            
            // Store update function for keyboard control
            thicknessControlUpdate = function(index) {
                const t = thicknesses[index];
                currentLineThickness = t;
                buttonCircle.style.width = `${t}px`;
                buttonCircle.style.height = `${t}px`;
                buttonText.innerText = `${index + 1}`;
                
                // Update selection highlight
                Array.from(dropdown.children).forEach((child, i) => {
                    if (i === index) {
                        child.style.backgroundColor = '#e6f2ff';
                    } else {
                        child.style.backgroundColor = 'transparent';
                    }
                });
            };
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!container.contains(e.target)) {
                    dropdown.style.display = "none";
                    buttonArrow.innerText = '▼';
                }
            });
            
            // Prevent map interactions when using the control
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            
            return container;
        }
    });
    
    // Line Color Control
    L.Control.LineColorControl = L.Control.extend({
        options: {
            position: 'topright'
        },
        
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
            container.style.backgroundColor = 'white';
            container.style.padding = '8px';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.gap = '8px';
            container.style.position = 'relative';
            container.style.zIndex = '999';
            container.style.width = '60px';  // Fixed container width: 80px button + 16px padding (8px * 2)
            
            const label = L.DomUtil.create('label', '', container);
            label.innerHTML = 'Color:';
            label.style.fontSize = '11px';
            label.style.fontWeight = 'bold';
            label.style.marginBottom = '0';
            
            // Current color display button
            const colorButton = L.DomUtil.create('button', '', container);
            colorButton.style.width = '40px';
            colorButton.style.height = '20px';
            colorButton.style.backgroundColor = '#FFFF00';
            colorButton.style.border = '2px solid #333';
            colorButton.style.borderRadius = '3px';
            colorButton.style.cursor = 'pointer';
            colorButton.style.display = 'flex';
            colorButton.style.alignItems = 'center';
            colorButton.style.justifyContent = 'center';
            colorButton.style.padding = '0';
            colorButton.style.flexShrink = '0';  // Prevent shrinking
            colorButton.title = 'Click or Press key (C) to change';
            
            const dropArrow = L.DomUtil.create('span', '', colorButton);
            dropArrow.innerText = '▼';
            dropArrow.style.fontSize = '10px';
            dropArrow.style.color = '#000';
            
            // Color palette grid (hidden by default)
            const paletteGrid = L.DomUtil.create('div', '', container);
            paletteGrid.style.display = 'none';
            paletteGrid.style.gridTemplateColumns = 'repeat(10, 1fr)';
            paletteGrid.style.gap = '4px';
            paletteGrid.style.marginTop = '4px';
            paletteGrid.style.position = 'absolute';  // ADD: Position absolutely
            paletteGrid.style.right = '0';             // ADD: Align to left
            paletteGrid.style.top = '100%';           // ADD: Position below button
            paletteGrid.style.backgroundColor = 'white';  // ADD: White background
            paletteGrid.style.border = '1px solid #ccc';  // ADD: Border
            paletteGrid.style.padding = '8px';        // ADD: Padding
            paletteGrid.style.borderRadius = '3px';   // ADD: Rounded corners
            paletteGrid.style.boxShadow = '0 2px 4px rgba(0,0,0,0.2)';  // ADD: Shadow
            paletteGrid.style.zIndex = '1000';        // ADD: Above other elements
            paletteGrid.style.minWidth = '280px';     // Minimum width to fit all 10 colors
            
            let selectedSwatch = null;
            let currentColorName = 'Yellow';
            const allSwatches = [];
            
            // Toggle color palette visibility on button click
            colorButton.onclick = function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                if (paletteGrid.style.display === 'none') {
                    paletteGrid.style.display = 'grid';
                    dropArrow.innerText = '▲';
                } else {
                    paletteGrid.style.display = 'none';
                    dropArrow.innerText = '▼';
                }
            };
            
            colorPalette.forEach(({ color, name }, idx) => {
                const swatch = L.DomUtil.create('div', '', paletteGrid);
                swatch.style.width = '24px';
                swatch.style.height = '24px';
                swatch.style.backgroundColor = color;
                swatch.style.border = '2px solid #ccc';
                swatch.style.borderRadius = '3px';
                swatch.style.cursor = 'pointer';
                swatch.style.transition = 'all 0.2s';
                swatch.title = name;
                allSwatches.push(swatch);
                
                // Highlight default color (yellow)
                if (color === '#FFFF00') {
                    swatch.style.border = '2px solid #333';
                    swatch.style.boxShadow = '0 0 4px rgba(0,0,0,0.4)';
                    selectedSwatch = swatch;
                }
                
                // Special styling for white to make it visible
                if (color === '#FFFFFF') {
                    swatch.style.border = '2px solid #666';
                }
                
                swatch.onclick = function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Remove previous selection
                    if (selectedSwatch) {
                        selectedSwatch.style.border = '2px solid #ccc';
                        selectedSwatch.style.boxShadow = 'none';
                        if (selectedSwatch.style.backgroundColor === 'rgb(255, 255, 255)') {
                            selectedSwatch.style.border = '2px solid #666';
                        }
                    }
                    
                    // Highlight selected
                    swatch.style.border = '2px solid #333';
                    swatch.style.boxShadow = '0 0 4px rgba(0,0,0,0.4)';
                    selectedSwatch = swatch;
                    
                    currentLineColor = color;
                    currentColorName = name;
                    
                    // Update button display
                    colorButton.style.backgroundColor = color;
                    
                    // Adjust arrow color for visibility
                    if (color === '#000000' || color === '#0000FF' || color === '#800080') {
                        dropArrow.style.color = '#fff';
                    } else {
                        dropArrow.style.color = '#000';
                    }
                    
                    // Close palette
                    paletteGrid.style.display = 'none';
                    dropArrow.innerText = '▼';
                    
                    console.log('Line color set to:', color, `(${name})`);
                    currentColorIndex = idx;
                };
            });
            
            // Store update function for keyboard control
            colorControlUpdate = function(index) {
                const { color, name } = colorPalette[index];
                
                // Remove previous selection
                if (selectedSwatch) {
                    selectedSwatch.style.border = '2px solid #ccc';
                    selectedSwatch.style.boxShadow = 'none';
                    if (selectedSwatch.style.backgroundColor === 'rgb(255, 255, 255)') {
                        selectedSwatch.style.border = '2px solid #666';
                    }
                }
                
                // Highlight new selection
                const swatch = allSwatches[index];
                swatch.style.border = '2px solid #333';
                swatch.style.boxShadow = '0 0 4px rgba(0,0,0,0.4)';
                selectedSwatch = swatch;
                
                // Update button display
                colorButton.style.backgroundColor = color;
                
                // Adjust arrow color for visibility
                if (color === '#000000' || color === '#0000FF' || color === '#800080') {
                    dropArrow.style.color = '#fff';
                } else {
                    dropArrow.style.color = '#000';
                }
                
                currentLineColor = color;
                currentColorName = name;
            };
            
            // Close palette when clicking outside
            document.addEventListener('click', function(e) {
                if (!container.contains(e.target)) {
                    paletteGrid.style.display = 'none';
                    dropArrow.innerText = '▼';
                }
            });
            
            // Prevent map interactions when using the control
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            
            return container;
        }
    });
    
    // Helper functions to update UI controls
    let thicknessControlUpdate = null;
    let colorControlUpdate = null;
    
    function updateThicknessFromKeyboard(index) {
        if (index >= 0 && index < thicknesses.length) {
            currentLineThickness = thicknesses[index];
            if (thicknessControlUpdate) {
                thicknessControlUpdate(index);
            }
            console.log(`⌨️ Thickness set to ${currentLineThickness}px (${index + 1})`);
        }
    }
    
    function cycleColor() {
        currentColorIndex = (currentColorIndex + 1) % colorPalette.length;
        currentLineColor = colorPalette[currentColorIndex].color;
        if (colorControlUpdate) {
            colorControlUpdate(currentColorIndex);
        }
        console.log(`⌨️ Color set to ${colorPalette[currentColorIndex].name}`);
    }
    
    // Initialize freehand drawing on a map
    window.initializeFreehandDrawing = function(map, drawnItems) {
        console.log('Initializing freehand drawing module...');
        
        // Add freehand button
        const freehandButton = new L.Control.FreehandButton();
        freehandButton.addTo(map);
        console.log('✓ Freehand button added');
        
        // Add clear all button
        const clearAllButton = new L.Control.ClearAllButton();
        clearAllButton.addTo(map);
        clearAllButton._button.onclick = function(e) {
            L.DomEvent.stopPropagation(e);
            L.DomEvent.preventDefault(e);
            
            // Clear all layers from drawnItems
            drawnItems.clearLayers();
            selectedLayer = null;
            deleteLineButton.disable();
            console.log('All drawings cleared');
        };
        console.log('✓ Clear all button added');
        
        // Add delete line button
        const deleteLineButton = new L.Control.DeleteLineButton();
        deleteLineButton.addTo(map);
        deleteLineButton._button.onclick = function(e) {
            L.DomEvent.stopPropagation(e);
            L.DomEvent.preventDefault(e);
            
            if (selectedLayer) {
                drawnItems.removeLayer(selectedLayer);
                console.log('Selected line deleted');
                selectedLayer = null;
                deleteLineButton.disable();
            }
        };
        console.log('✓ Delete line button added');
        
        // Add line thickness control
        const thicknessControl = new L.Control.LineThicknessControl();
        thicknessControl.addTo(map);
        console.log('✓ Line thickness control added');
        
        // Add line color control
        const colorControl = new L.Control.LineColorControl();
        colorControl.addTo(map);
        console.log('✓ Line color control added');
        
        // Track Shift key state, Backspace for deletion, and drawing tool shortcuts
        document.addEventListener('keydown', function(e) {
            // Prevent shortcuts when typing in input fields
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }
            
            if (e.key === 'Shift' && !shiftPressed) {
                shiftPressed = true;
                map.dragging.disable();
                map.getContainer().classList.add('pen-cursor');
                console.log('Shift pressed - Freehand drawing mode ON');
            } else if (e.key === 'Backspace' && (e.ctrlKey || e.metaKey) && e.altKey) {
                // Ctrl/Cmd + Alt + Backspace: Clear all drawings
                e.preventDefault();
                drawnItems.clearLayers();
                selectedLayer = null;
                deleteLineButton.disable();
                console.log('⌨️ All drawings cleared via Ctrl/Cmd+Alt+Backspace');
            } else if (e.key === 'Backspace' && selectedLayer) {
                e.preventDefault(); // Prevent browser back navigation
                drawnItems.removeLayer(selectedLayer);
                console.log('Selected line deleted via Backspace');
                selectedLayer = null;
                deleteLineButton.disable();
            }
            // Number keys 1-5 for line thickness
            else if (e.key >= '1' && e.key <= '5' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                //e.preventDefault(); // Prevent default zoom behavior
                //e.stopPropagation(); // Stop event from bubbling up
                const index = parseInt(e.key) - 1;
                updateThicknessFromKeyboard(index);
            }
            // C key to cycle through colors
            else if (e.key.toLowerCase() === 'c' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                cycleColor();
            }
        });
        
        document.addEventListener('keyup', function(e) {
            if (e.key === 'Shift') {
                shiftPressed = false;
                if (!freehandMode) {
                    map.dragging.enable();
                    map.getContainer().classList.remove('pen-cursor');
                }
                
                // If currently drawing, finish the line
                if (isDrawing) {
                    finishDrawing(map, drawnItems);
                }
                console.log('Shift released - Pan mode ON');
            }
        });
        
        // Mouse event handlers
        map.on('mousedown', function(e) {
            if (freehandMode || shiftPressed) {
                startDrawing(e, map);
            }
        });
        
        map.on('mousemove', function(e) {
            if ((freehandMode || shiftPressed) && isDrawing) {
                continueDrawing(e);
            }
        });
        
        map.on('mouseup', function(e) {
            if ((freehandMode || shiftPressed) && isDrawing) {
                finishDrawing(map, drawnItems, deleteLineButton);
            }
        });
        
        // Handle layer selection
        drawnItems.on('click', function(e) {
            // Deselect previous layer
            if (selectedLayer) {
                const originalColor = selectedLayer.options.originalColor || currentLineColor;
                const originalWeight = selectedLayer.options.originalWeight || currentLineThickness;
                selectedLayer.setStyle({ color: originalColor, weight: originalWeight });
            }
            
            // Select new layer and store its original style
            selectedLayer = e.layer;
            if (!selectedLayer.options.originalColor) {
                selectedLayer.options.originalColor = selectedLayer.options.color;
                selectedLayer.options.originalWeight = selectedLayer.options.weight;
            }
            selectedLayer.setStyle({ color: '#ff0000', weight: selectedLayer.options.originalWeight + 1 });
            deleteLineButton.enable();
            console.log('Line selected');
        });
        
        // Deselect when clicking on map background
        map.on('click', function(e) {
            if (selectedLayer && !freehandMode && !shiftPressed) {
                const originalColor = selectedLayer.options.originalColor || currentLineColor;
                const originalWeight = selectedLayer.options.originalWeight || currentLineThickness;
                selectedLayer.setStyle({ color: originalColor, weight: originalWeight });
                selectedLayer = null;
                deleteLineButton.disable();
                console.log('Line deselected');
            }
        });
        
        console.log('✓ Freehand drawing initialized');
        console.log('  Keyboard shortcuts: 1-5 (line thickness), C (cycle colors), Shift (draw), Backspace (delete), Ctrl/Cmd+Alt+Backspace (clear all)');
    };
    
    // Start drawing
    function startDrawing(e, map) {
        isDrawing = true;
        points = [];
        points.push(e.latlng);
        
        if (freehandLine) {
            map.removeLayer(freehandLine);
        }
        
        freehandLine = L.polyline(points, {
            color: currentLineColor,
            weight: currentLineThickness,
            smoothFactor: 1
        }).addTo(map);
    }
    
    // Continue drawing
    function continueDrawing(e) {
        points.push(e.latlng);
        freehandLine.setLatLngs(points);
    }
    
    // Finish drawing
    function finishDrawing(map, drawnItems, deleteLineButton) {
        isDrawing = false;
        if (freehandLine && points.length > 1) {
            drawnItems.addLayer(freehandLine);
            console.log('Freehand line drawn with', points.length, 'points');
            console.log('GeoJSON:', JSON.stringify(freehandLine.toGeoJSON()));
        } else if (freehandLine) {
            map.removeLayer(freehandLine);
        }
        freehandLine = null;
        points = [];
    }
    
})();