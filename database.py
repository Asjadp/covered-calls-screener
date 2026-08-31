import os
import sqlite3
from datetime import datetime
import pandas as pd
from typing import Optional, Tuple, Dict, Any, List

DB_FILE = "covered_calls.db"

def get_database_url() -> Optional[str]:
    """
    Retrieve database URL from Streamlit secrets or environment variables.
    Supports free cloud PostgreSQL (Supabase, Neon, ElephantSQL, etc.).
    """
    # 1. Check Streamlit Secrets if running in Streamlit
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            url = st.secrets["DATABASE_URL"]
            if url:
                # SQLAlchemy requires postgresql:// instead of postgres://
                if url.startswith("postgres://"):
                    url = url.replace("postgres://", "postgresql://", 1)
                return url
    except Exception:
        pass

    # 2. Check Environment Variables
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        if env_url.startswith("postgres://"):
            env_url = env_url.replace("postgres://", "postgresql://", 1)
        return env_url

    return None

def get_db_status() -> Dict[str, Any]:
    """Return database connection status and backend details for UI display."""
    db_url = get_database_url()
    if db_url:
        if "supabase" in db_url.lower():
            label = "☁️ Supabase Cloud (PostgreSQL)"
        elif "neon" in db_url.lower():
            label = "☁️ Neon Cloud (PostgreSQL)"
        else:
            label = "☁️ Cloud Database (PostgreSQL)"
        return {"backend": "PostgreSQL", "is_cloud": True, "label": label}
    return {"backend": "SQLite", "is_cloud": False, "label": "💾 Local Storage (SQLite)"}

def _get_sqlalchemy_engine():
    """Create a SQLAlchemy engine if cloud database is configured."""
    db_url = get_database_url()
    if db_url:
        try:
            from sqlalchemy import create_engine
            return create_engine(db_url, pool_pre_ping=True)
        except Exception as e:
            print(f"[Warning] Could not initialize cloud DB engine: {e}. Falling back to SQLite.")
    return None

def init_db():
    """Initialize database schema on PostgreSQL (cloud) or SQLite (local)."""
    engine = _get_sqlalchemy_engine()
    
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.begin() as conn:
                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS stock_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp VARCHAR(50) NOT NULL,
                        ticker VARCHAR(20) NOT NULL,
                        current_price DOUBLE PRECISION NOT NULL,
                        purchase_price DOUBLE PRECISION NOT NULL,
                        earnings_date VARCHAR(50)
                    )
                '''))
                
                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS option_results (
                        id SERIAL PRIMARY KEY,
                        snapshot_id INTEGER NOT NULL REFERENCES stock_snapshots(id) ON DELETE CASCADE,
                        timestamp VARCHAR(50) NOT NULL,
                        ticker VARCHAR(20) NOT NULL,
                        expiration_date VARCHAR(50) NOT NULL,
                        dte INTEGER NOT NULL,
                        target_type VARCHAR(50) NOT NULL,
                        strike_price DOUBLE PRECISION NOT NULL,
                        bid DOUBLE PRECISION,
                        ask DOUBLE PRECISION,
                        premium DOUBLE PRECISION NOT NULL,
                        implied_volatility_pct DOUBLE PRECISION,
                        delta DOUBLE PRECISION,
                        prob_itm_pct DOUBLE PRECISION,
                        prob_touch_pct DOUBLE PRECISION,
                        premium_roi_pct DOUBLE PRECISION NOT NULL,
                        ann_premium_roi_pct DOUBLE PRECISION NOT NULL,
                        max_roi_pct DOUBLE PRECISION NOT NULL,
                        ann_max_roi_pct DOUBLE PRECISION NOT NULL,
                        breakeven_price DOUBLE PRECISION NOT NULL
                    )
                '''))
            return
        except Exception as e:
            print(f"[Warning] Cloud DB initialization failed: {e}. Falling back to local SQLite.")

    # SQLite fallback / default
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            current_price REAL NOT NULL,
            purchase_price REAL NOT NULL,
            earnings_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS option_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            expiration_date TEXT NOT NULL,
            dte INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            strike_price REAL NOT NULL,
            bid REAL,
            ask REAL,
            premium REAL NOT NULL,
            implied_volatility_pct REAL,
            delta REAL,
            prob_itm_pct REAL,
            prob_touch_pct REAL,
            premium_roi_pct REAL NOT NULL,
            ann_premium_roi_pct REAL NOT NULL,
            max_roi_pct REAL NOT NULL,
            ann_max_roi_pct REAL NOT NULL,
            breakeven_price REAL NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES stock_snapshots (id)
        )
    ''')

    # Automatic schema migration for existing SQLite databases
    cursor.execute("PRAGMA table_info(option_results)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'implied_volatility_pct' not in columns:
        cursor.execute("ALTER TABLE option_results ADD COLUMN implied_volatility_pct REAL")
    if 'delta' not in columns:
        cursor.execute("ALTER TABLE option_results ADD COLUMN delta REAL")
    if 'prob_itm_pct' not in columns:
        cursor.execute("ALTER TABLE option_results ADD COLUMN prob_itm_pct REAL")
    if 'prob_touch_pct' not in columns:
        cursor.execute("ALTER TABLE option_results ADD COLUMN prob_touch_pct REAL")
    
    conn.commit()
    conn.close()

def save_screen_results(ticker: str, current_price: float, purchase_price: float, earnings_date: str, results: List[Dict[str, Any]]) -> int:
    """Save a screening session and its results to cloud PostgreSQL or local SQLite."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    engine = _get_sqlalchemy_engine()

    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.begin() as conn:
                insert_snap = text('''
                    INSERT INTO stock_snapshots (timestamp, ticker, current_price, purchase_price, earnings_date)
                    VALUES (:ts, :ticker, :curr_p, :purch_p, :e_date)
                    RETURNING id
                ''')
                res = conn.execute(insert_snap, {
                    "ts": timestamp,
                    "ticker": ticker.upper(),
                    "curr_p": current_price,
                    "purch_p": purchase_price,
                    "e_date": earnings_date
                })
                snapshot_id = res.scalar()

                insert_opt = text('''
                    INSERT INTO option_results (
                        snapshot_id, timestamp, ticker, expiration_date, dte, target_type,
                        strike_price, bid, ask, premium, implied_volatility_pct, delta,
                        prob_itm_pct, prob_touch_pct,
                        premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct, breakeven_price
                    ) VALUES (
                        :snap_id, :ts, :ticker, :exp_date, :dte, :target_type,
                        :strike_p, :bid, :ask, :premium, :iv, :delta,
                        :prob_itm, :prob_touch,
                        :prem_roi, :ann_prem_roi, :max_roi, :ann_max_roi, :breakeven
                    )
                ''')
                
                for row in results:
                    conn.execute(insert_opt, {
                        "snap_id": snapshot_id,
                        "ts": timestamp,
                        "ticker": ticker.upper(),
                        "exp_date": row['expiration_date'],
                        "dte": row['dte'],
                        "target_type": row['target_type'],
                        "strike_p": row['strike_price'],
                        "bid": row.get('bid'),
                        "ask": row.get('ask'),
                        "premium": row['premium'],
                        "iv": row.get('implied_volatility_pct'),
                        "delta": row.get('delta'),
                        "prob_itm": row.get('prob_itm_pct'),
                        "prob_touch": row.get('prob_touch_pct'),
                        "prem_roi": row['premium_roi_pct'],
                        "ann_prem_roi": row['ann_premium_roi_pct'],
                        "max_roi": row['max_roi_pct'],
                        "ann_max_roi": row['ann_max_roi_pct'],
                        "breakeven": row['breakeven_price']
                    })
                return snapshot_id
        except Exception as e:
            print(f"[Warning] Saving to cloud DB failed: {e}. Falling back to SQLite.")

    # SQLite fallback / default
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO stock_snapshots (timestamp, ticker, current_price, purchase_price, earnings_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, ticker.upper(), current_price, purchase_price, earnings_date))
    
    snapshot_id = cursor.lastrowid
    
    for row in results:
        cursor.execute('''
            INSERT INTO option_results (
                snapshot_id, timestamp, ticker, expiration_date, dte, target_type,
                strike_price, bid, ask, premium, implied_volatility_pct, delta,
                prob_itm_pct, prob_touch_pct,
                premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct, breakeven_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            snapshot_id, timestamp, ticker.upper(), row['expiration_date'], row['dte'],
            row['target_type'], row['strike_price'], row.get('bid'), row.get('ask'), row['premium'],
            row.get('implied_volatility_pct'), row.get('delta'),
            row.get('prob_itm_pct'), row.get('prob_touch_pct'),
            row['premium_roi_pct'], row['ann_premium_roi_pct'], row['max_roi_pct'],
            row['ann_max_roi_pct'], row['breakeven_price']
        ))
        
    conn.commit()
    conn.close()
    return snapshot_id

def load_history(ticker: Optional[str] = None) -> pd.DataFrame:
    """Fetch historical screening data from cloud PostgreSQL or local SQLite."""
    engine = _get_sqlalchemy_engine()

    query = '''
        SELECT r.timestamp, r.ticker, s.current_price, s.purchase_price, s.earnings_date,
               r.expiration_date, r.dte, r.target_type, r.strike_price, r.premium,
               r.implied_volatility_pct, r.delta, r.prob_itm_pct, r.prob_touch_pct,
               r.premium_roi_pct, r.ann_premium_roi_pct, r.max_roi_pct, r.ann_max_roi_pct
        FROM option_results r
        JOIN stock_snapshots s ON r.snapshot_id = s.id
    '''
    params = {}
    if ticker:
        query += " WHERE UPPER(r.ticker) = :ticker"
        params["ticker"] = ticker.upper()
    query += " ORDER BY r.timestamp DESC"

    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                df = pd.read_sql_query(text(query), conn, params=params if ticker else None)
                return df
        except Exception as e:
            print(f"[Warning] Loading history from cloud DB failed: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    sqlite_query = '''
        SELECT r.timestamp, r.ticker, s.current_price, s.purchase_price, s.earnings_date,
               r.expiration_date, r.dte, r.target_type, r.strike_price, r.premium,
               r.implied_volatility_pct, r.delta, r.prob_itm_pct, r.prob_touch_pct,
               r.premium_roi_pct, r.ann_premium_roi_pct, r.max_roi_pct, r.ann_max_roi_pct
        FROM option_results r
        JOIN stock_snapshots s ON r.snapshot_id = s.id
    '''
    if ticker:
        sqlite_query += f" WHERE UPPER(r.ticker) = '{ticker.upper()}'"
    sqlite_query += " ORDER BY r.timestamp DESC"

    df = pd.read_sql_query(sqlite_query, conn)
    conn.close()
    return df

def get_latest_snapshot(ticker: str) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Retrieve the most recent screening snapshot and option contracts for a given ticker from the database."""
    engine = _get_sqlalchemy_engine()
    
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                snap_row = conn.execute(
                    text("SELECT id, timestamp, ticker, current_price, purchase_price, earnings_date FROM stock_snapshots WHERE UPPER(ticker) = :t ORDER BY id DESC LIMIT 1"),
                    {"t": ticker.upper()}
                ).mappings().first()
                
                if snap_row:
                    snapshot = dict(snap_row)
                    opt_rows = conn.execute(
                        text("SELECT expiration_date, dte, target_type, strike_price, bid, ask, premium, implied_volatility_pct, delta, prob_itm_pct, prob_touch_pct, premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct, breakeven_price FROM option_results WHERE snapshot_id = :sid ORDER BY dte ASC, strike_price ASC"),
                        {"sid": snapshot["id"]}
                    ).mappings().all()
                    
                    results = []
                    for r in opt_rows:
                        row_dict = dict(r)
                        term_label = "2-Month" if row_dict["dte"] <= 75 else "3-Month"
                        row_dict["term"] = f"{term_label} (~{row_dict['dte']}d)"
                        results.append(row_dict)
                    return snapshot, results
        except Exception as e:
            print(f"[Warning] Loading snapshot from cloud DB failed: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, timestamp, ticker, current_price, purchase_price, earnings_date FROM stock_snapshots WHERE UPPER(ticker) = ? ORDER BY id DESC LIMIT 1",
        (ticker.upper(),)
    )
    snap_row = cursor.fetchone()
    
    if not snap_row:
        conn.close()
        return None
        
    snapshot = dict(snap_row)
    cursor.execute(
        "SELECT expiration_date, dte, target_type, strike_price, bid, ask, premium, implied_volatility_pct, delta, prob_itm_pct, prob_touch_pct, premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct, breakeven_price FROM option_results WHERE snapshot_id = ? ORDER BY dte ASC, strike_price ASC",
        (snapshot["id"],)
    )
    opt_rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in opt_rows:
        row_dict = dict(r)
        term_label = "2-Month" if row_dict["dte"] <= 75 else "3-Month"
        row_dict["term"] = f"{term_label} (~{row_dict['dte']}d)"
        results.append(row_dict)
        
    return snapshot, results