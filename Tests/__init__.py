import sys
from pathlib import Path

#add the src directory to Python Path to allow importing core and other modules
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert (0, str(src_path))