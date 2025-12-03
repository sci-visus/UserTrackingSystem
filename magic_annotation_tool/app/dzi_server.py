from flask import Flask, send_from_directory, abort, render_template_string
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Base directory for DZI files
DZI_BASE_DIR = "/data/dzi_datasets"

# HTML template for directory listing
DIRECTORY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Directory Listing - {{ path }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        ul { list-style: none; padding: 0; }
        li { padding: 5px 0; }
        a { text-decoration: none; color: #0066cc; }
        a:hover { text-decoration: underline; }
        .folder::before { content: "📁 "; }
        .file::before { content: "📄 "; }
        .back::before { content: "⬆️ "; }
    </style>
</head>
<body>
    <h1>Directory: {{ path }}</h1>
    <ul>
        {% if parent %}
        <li><a href="{{ parent }}" class="back">Parent Directory</a></li>
        {% endif %}
        {% for item in items %}
        <li><a href="{{ item.url }}" class="{{ item.type }}">{{ item.name }}</a></li>
        {% endfor %}
    </ul>
</body>
</html>
"""

@app.route('/')
def serve_root():
    """Serve root directory listing"""
    return list_directory('')

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (minimap CSS/JS)"""
    return send_from_directory('/app', filename)

@app.route('/<path:filepath>')
def serve_file(filepath):
    """
    Serve DZI descriptor files, tile images, or directory listings
    Handles both .dzi XML files and tile images in _files directories
    """
    try:
        file_path = os.path.join(DZI_BASE_DIR, filepath)
        
        if not os.path.exists(file_path):
            # Suppress logging for expected missing edge tiles (PNG files in _files directories)
            if not (filepath.endswith('.png') and '_files/' in filepath):
                logger.warning(f"File not found: {filepath}")
            abort(404)
        
        # If it's a directory, show listing
        if os.path.isdir(file_path):
            return list_directory(filepath)
        
        # If it's a file, serve it
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        # Only log non-tile files to reduce noise
        if not filepath.endswith('.png'):
            logger.info(f"Serving file: {filepath}")
        return send_from_directory(directory, filename)
        
    except Exception as e:
        # Only log errors for non-404 exceptions
        if not (hasattr(e, 'code') and e.code == 404):
            logger.error(f"Error serving {filepath}: {e}", exc_info=True)
        abort(500)

def list_directory(path):
    """Generate HTML directory listing"""
    full_path = os.path.join(DZI_BASE_DIR, path)
    
    if not os.path.exists(full_path) or not os.path.isdir(full_path):
        abort(404)
    
    try:
        entries = os.listdir(full_path)
        items = []
        
        for entry in sorted(entries):
            entry_path = os.path.join(full_path, entry)
            is_dir = os.path.isdir(entry_path)
            
            item_url = os.path.join('/', path, entry) if path else f'/{entry}'
            items.append({
                'name': entry + ('/' if is_dir else ''),
                'url': item_url,
                'type': 'folder' if is_dir else 'file'
            })
        
        # Parent directory link
        parent = None
        if path:
            parent_path = os.path.dirname(path)
            parent = f'/{parent_path}' if parent_path else '/'
        
        display_path = '/' + path if path else '/'
        logger.info(f"Listing directory: {display_path}")
        
        return render_template_string(DIRECTORY_TEMPLATE, 
                                     path=display_path, 
                                     items=items, 
                                     parent=parent)
    except Exception as e:
        logger.error(f"Error listing directory {path}: {e}", exc_info=True)
        abort(500)

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "dzi_server"}

if __name__ == '__main__':
    # Get port from environment variable with default fallback
    port = int(os.getenv('DZI_SERVER_PORT', 10566))
    
    logger.info(f"Starting DZI tile server")
    logger.info(f"Serving files from: {DZI_BASE_DIR}")
    logger.info(f"Port: {port}")
    
    # List available DZI files
    if os.path.exists(DZI_BASE_DIR):
        dzi_files = [f for f in os.listdir(DZI_BASE_DIR) if f.endswith('.dzi')]
        logger.info(f"Available DZI files: {dzi_files}")
    
    app.run(host='0.0.0.0', port=port, debug=False)