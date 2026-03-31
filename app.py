from flask import Flask, render_template, request, jsonify
import base64
import gc
import io
import os
import uuid
import time
import json
import tempfile
from datetime import datetime, timezone
from threading import Lock
from werkzeug.utils import secure_filename
from typing import Tuple, Optional, Any, Dict, List
import pandas as pd

from data_processor import DataProcessor
from visualizer import Visualizer


# ==========================================================
# APP CONFIGURATION
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, 'docs')
STATIC_DIR = os.path.join(DOCS_DIR, 'static')
IS_SERVERLESS = bool(
    os.getenv('VERCEL')
    or os.getenv('AWS_LAMBDA_FUNCTION_NAME')
    or os.getenv('SERVERLESS')
)
DEFAULT_UPLOAD_FOLDER = (
    os.path.join(tempfile.gettempdir(), 'quantvista_uploads')
    if IS_SERVERLESS
    else os.path.join(BASE_DIR, 'uploads')
)
DEFAULT_DASHBOARD_STORAGE = (
    os.path.join(tempfile.gettempdir(), 'quantvista_dashboards.json')
    if IS_SERVERLESS
    else os.path.join(BASE_DIR, 'dashboards.json')
)

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=DOCS_DIR)

app.config.update(  # type: ignore
    UPLOAD_FOLDER=DEFAULT_UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    ALLOWED_EXTENSIONS={'csv', 'xlsx', 'xls', 'json'},
    FILE_CACHE_TIMEOUT=3600,  # 1 hour
    FILE_CLEANUP_AGE=7200,    # 2 hours
    MAX_CACHE_ITEMS=10,       # Prevent memory explosion
    DASHBOARD_STORAGE=DEFAULT_DASHBOARD_STORAGE,
    MAX_DASHBOARDS=100
)

# Type-safe config constants
UPLOAD_FOLDER: str = str(app.config['UPLOAD_FOLDER'])  # type: ignore
FILE_CACHE_TIMEOUT: float = float(app.config['FILE_CACHE_TIMEOUT'])  # type: ignore
FILE_CLEANUP_AGE: float = float(app.config['FILE_CLEANUP_AGE'])  # type: ignore
MAX_CACHE_ITEMS: int = int(app.config['MAX_CACHE_ITEMS'])  # type: ignore
ALLOWED_EXTENSIONS: set = app.config['ALLOWED_EXTENSIONS']  # type: ignore
DASHBOARD_STORAGE: str = str(app.config['DASHBOARD_STORAGE'])  # type: ignore
MAX_DASHBOARDS: int = int(app.config['MAX_DASHBOARDS'])  # type: ignore
MAX_CONTENT_LENGTH: int = int(app.config['MAX_CONTENT_LENGTH'])  # type: ignore

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

data_processor = DataProcessor()
visualizer = Visualizer()

from collections import OrderedDict

# Cache structure: OrderedDict {filename: (df, timestamp)}
df_cache: OrderedDict[str, Tuple[pd.DataFrame, float]] = OrderedDict()
cache_lock = Lock()
dashboard_lock = Lock()


# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

def allowed_file(filename: Optional[str]) -> bool:
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_filename(filename: Optional[str]) -> bool:
    if not filename:
        return False
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    return allowed_file(filename)


def is_safe_upload_path(filepath: str) -> bool:
    try:
        real_path = os.path.realpath(filepath)
        real_upload = os.path.realpath(UPLOAD_FOLDER)
        return os.path.commonpath([real_path, real_upload]) == real_upload
    except ValueError:
        return False


def remove_file_safely(filepath: str, retries: int = 3) -> None:
    last_error: Optional[OSError] = None
    for attempt in range(retries):
        try:
            os.remove(filepath)
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            gc.collect()
            time.sleep(0.05 * (attempt + 1))

    if last_error:
        raise last_error


def cleanup_old_files() -> None:
    if not os.path.isdir(UPLOAD_FOLDER):
        return

    current_time = time.time()
    max_age = FILE_CLEANUP_AGE

    for filename in os.listdir(UPLOAD_FOLDER):
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        if os.path.isfile(filepath):
            file_age = current_time - os.path.getmtime(filepath)

            if file_age > max_age:
                try:
                    remove_file_safely(filepath)
                    with cache_lock:
                        df_cache.pop(filename, None)
                except PermissionError:
                    # File might be in use, skip for now
                    pass
                except Exception:
                    pass


def get_cached_dataframe(filename: str) -> pd.DataFrame:
    with cache_lock:
        if filename in df_cache:
            df, timestamp = df_cache[filename]
            if time.time() - timestamp < FILE_CACHE_TIMEOUT:
                return df
            df_cache.pop(filename, None)

    filepath = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        raise FileNotFoundError("File not found")

    if not is_safe_upload_path(filepath):
        raise ValueError("Invalid file path")

    df = data_processor.load_data(filepath)

    with cache_lock:
        if len(df_cache) >= MAX_CACHE_ITEMS:
            df_cache.popitem(last=False)

        df_cache[filename] = (df, time.time())

    return df


def cache_dataframe(filename: str, df: pd.DataFrame) -> None:
    with cache_lock:
        if len(df_cache) >= MAX_CACHE_ITEMS:
            df_cache.popitem(last=False)
        df_cache[filename] = (df, time.time())


def get_request_dataframe(data: Dict[str, Any]) -> pd.DataFrame:
    inline_content = data.get('file_content')
    if inline_content is not None:
        if not isinstance(inline_content, str) or not inline_content.strip():
            raise ValueError("Invalid inline file payload")

        inline_name = secure_filename(str(data.get('original_filename') or data.get('filename') or 'upload.csv'))
        if not inline_name or not allowed_file(inline_name):
            raise ValueError("Unsupported inline file type")

        try:
            file_bytes = base64.b64decode(inline_content, validate=True)
        except Exception as exc:
            raise ValueError("Invalid inline file encoding") from exc

        if len(file_bytes) > MAX_CONTENT_LENGTH:
            raise ValueError("File too large (Max 16MB)")

        file_extension = inline_name.rsplit('.', 1)[1].lower()
        return data_processor.load_data(io.BytesIO(file_bytes), file_extension)

    filename = data.get('filename')
    if not filename:
        raise ValueError("Filename required")

    if not validate_filename(filename) or ".." in filename:
        raise ValueError("Invalid filename")

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath) or not is_safe_upload_path(filepath):
        raise FileNotFoundError("File not found or access denied")

    return get_cached_dataframe(filename)


def _load_dashboards() -> List[Dict[str, Any]]:
    if not os.path.exists(DASHBOARD_STORAGE):
        return []
    try:
        with open(DASHBOARD_STORAGE, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def _save_dashboards(dashboards: List[Dict[str, Any]]) -> None:
    temp_path = f"{DASHBOARD_STORAGE}.tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(dashboards, f, ensure_ascii=True, indent=2)
    try:
        os.replace(temp_path, DASHBOARD_STORAGE)
    except PermissionError:
        # Windows can occasionally lock the target file; fall back to direct rewrite.
        with open(DASHBOARD_STORAGE, 'w', encoding='utf-8') as f:
            json.dump(dashboards, f, ensure_ascii=True, indent=2)
        try:
            os.remove(temp_path)
        except OSError:
            pass


# ==========================================================
# ERROR HANDLERS
# ==========================================================

@app.before_request
def handle_preflight() -> Optional[Tuple[str, int]]:
    if request.method == 'OPTIONS':
        return '', 204
    return None


@app.after_request
def apply_cors_headers(response: Any) -> Any:
    origin = request.headers.get('Origin', '').strip()
    configured_origins = [
        item.strip() for item in os.getenv('QUANTVISTA_ALLOWED_ORIGINS', '*').split(',')
        if item.strip()
    ]

    if configured_origins == ['*']:
        response.headers['Access-Control-Allow-Origin'] = '*' if not origin else origin
    elif origin in configured_origins:
        response.headers['Access-Control-Allow-Origin'] = origin

    response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,DELETE,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.errorhandler(413)
def file_too_large(e: Exception) -> Tuple[Any, int]:
    return jsonify({'error': 'File too large (Max 16MB)'}), 413


# ==========================================================
# ROUTES
# ==========================================================

@app.route('/')
def index():
    cleanup_old_files()
    return render_template('index.html')


# -----------------------------
# FILE UPLOAD
# -----------------------------

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        file = request.files.get('file')

        if not file or not file.filename or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Unsupported file type'}), 400

        original_filename = secure_filename(file.filename)
        if not original_filename:
            return jsonify({'error': 'Invalid filename'}), 400

        file_extension = original_filename.rsplit('.', 1)[1].lower()
        file_bytes = file.read()
        df = data_processor.load_data(io.BytesIO(file_bytes), file_extension)

        unique_filename = f"{uuid.uuid4().hex[:8]}_{original_filename}"

        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        try:
            with open(filepath, 'wb') as saved_file:
                saved_file.write(file_bytes)
            cache_dataframe(unique_filename, df)
        except Exception:
            with cache_lock:
                df_cache.pop(unique_filename, None)
            remove_file_safely(filepath)
            raise

        return jsonify({
            'success': True,
            'filename': unique_filename,
            'original_filename': original_filename,
            'summary': data_processor.get_summary(df),
            'columns': data_processor.get_columns(df),
            'row_count': len(df),
            'column_count': len(df.columns)
        })

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


# -----------------------------
# VISUALIZATION
# -----------------------------

@app.route('/visualize', methods=['POST'])
def visualize():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid request'}), 400

        chart_type = data.get('chart_type')

        if not chart_type:
            return jsonify({'error': 'chart_type required'}), 400

        raw_auto_scale = data.get('auto_scale', True)
        if isinstance(raw_auto_scale, bool):
            auto_scale = raw_auto_scale
        elif isinstance(raw_auto_scale, str):
            auto_scale = raw_auto_scale.strip().lower() in {'1', 'true', 'yes', 'on'}
        else:
            auto_scale = bool(raw_auto_scale)

        df = get_request_dataframe(data)

        fig = visualizer.create_chart(
            df=df,
            chart_type=chart_type,
            x=data.get('x_column'),
            y=data.get('y_column'),
            z=data.get('z_column'),
            color=data.get('color_column'),
            agg=data.get('aggregation', 'sum'),
            auto_scale=auto_scale,
            title=data.get('title', 'Data Visualization')
        )

        import base64
        import json
        import numpy as np

        def decode_bdata(obj: Any) -> Any:
            if isinstance(obj, dict):
                if 'bdata' in obj and 'dtype' in obj:
                    try:
                        arr = np.frombuffer(base64.b64decode(obj['bdata']), dtype=obj['dtype'])  # type: ignore
                        if 'shape' in obj:
                            arr = arr.reshape(tuple(map(int, str(obj['shape']).split(','))))  # type: ignore
                        return arr.tolist()
                    except Exception:
                        pass
                for k, v in list(obj.items()):  # type: ignore
                    obj[k] = decode_bdata(v)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):  # type: ignore
                    obj[i] = decode_bdata(v)
            return obj  # type: ignore

        raw_json = str(fig.to_json())  # type: ignore
        raw_dict = json.loads(raw_json)
        clean_dict = decode_bdata(raw_dict)
        graph_json = json.dumps(clean_dict)

        return jsonify({
            'success': True,
            'graph': graph_json
        })

    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Visualization failed: {str(e)}'}), 500


# -----------------------------
# DATA ANALYSIS
# -----------------------------

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid request'}), 400

        df = get_request_dataframe(data)

        return jsonify({
            'success': True,
            'analysis': data_processor.get_detailed_analysis(df)
        })

    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


# -----------------------------
# SAVED DASHBOARDS
# -----------------------------

@app.route('/dashboards', methods=['GET'])
def list_dashboards():
    with dashboard_lock:
        dashboards = _load_dashboards()
    dashboards = sorted(dashboards, key=lambda d: str(d.get('created_at', '')), reverse=True)
    return jsonify({'success': True, 'dashboards': dashboards})


@app.route('/dashboards', methods=['POST'])
def save_dashboard():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request'}), 400

    name = str(data.get('name', '')).strip()
    config = data.get('config')

    if not name:
        return jsonify({'error': 'Dashboard name is required'}), 400
    if len(name) > 80:
        return jsonify({'error': 'Dashboard name too long (max 80 chars)'}), 400
    if not isinstance(config, dict):
        return jsonify({'error': 'Dashboard config must be an object'}), 400

    safe_config = {
        'chart_type': str(config.get('chart_type', '')).strip(),
        'x_column': str(config.get('x_column', '')).strip(),
        'y_column': str(config.get('y_column', '')).strip(),
        'z_column': str(config.get('z_column', '')).strip(),
        'color_column': str(config.get('color_column', '')).strip(),
        'aggregation': str(config.get('aggregation', 'sum')).strip() or 'sum',
        'title': str(config.get('title', 'Data Visualization')).strip() or 'Data Visualization',
        'auto_scale': bool(config.get('auto_scale', True))
    }

    if not safe_config['chart_type']:
        return jsonify({'error': 'chart_type is required in dashboard config'}), 400

    dashboard = {
        'id': uuid.uuid4().hex[:10],
        'name': name,
        'config': safe_config,
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    with dashboard_lock:
        dashboards = _load_dashboards()
        dashboards.insert(0, dashboard)
        dashboards = dashboards[:MAX_DASHBOARDS]
        _save_dashboards(dashboards)

    return jsonify({'success': True, 'dashboard': dashboard})


@app.route('/dashboards/<dashboard_id>', methods=['DELETE'])
def delete_dashboard(dashboard_id: str):
    if not dashboard_id:
        return jsonify({'error': 'Dashboard ID required'}), 400

    with dashboard_lock:
        dashboards = _load_dashboards()
        original_count = len(dashboards)
        dashboards = [d for d in dashboards if str(d.get('id')) != dashboard_id]
        if len(dashboards) == original_count:
            return jsonify({'error': 'Dashboard not found'}), 404
        _save_dashboards(dashboards)

    return jsonify({'success': True})


# ==========================================================
# RUN APP
# ==========================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  SERVER STARTING ON PORT 5000")
    print("  Go to: http://127.0.0.1:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
