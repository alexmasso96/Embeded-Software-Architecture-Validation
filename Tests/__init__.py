import sys
from pathlib import Path

# Add the src directory to the Python path so tests can import the backend and
# the Application_Logic layer (the single source root after the Phase-4 cutover).
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))