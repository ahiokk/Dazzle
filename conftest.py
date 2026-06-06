import os
import sys

# Гарантируем, что пакет tirika_importer импортируется при запуске pytest из корня.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
