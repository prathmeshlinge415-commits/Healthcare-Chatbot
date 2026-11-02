"""Create/upgrade the database. Usage:  python init_db.py"""
from config import Config
import db

if __name__ == "__main__":
    cfg = {k: getattr(Config, k) for k in dir(Config) if k.isupper()}
    db.init_schema(cfg)
    print(f"Database ready ({cfg['DB_BACKEND']}: {cfg['DB_NAME'] if cfg['DB_BACKEND']=='mysql' else cfg['SQLITE_PATH']}).")
