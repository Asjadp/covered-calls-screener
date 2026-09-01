import os
import json
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

                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS weekly_top_picks (
                        id SERIAL PRIMARY KEY,
                        batch_id VARCHAR(50) NOT NULL,
                        generated_at VARCHAR(50) NOT NULL,
                        target_type VARCHAR(50) NOT NULL,
                        rank INTEGER NOT NULL,
                        ticker VARCHAR(20) NOT NULL,
                        stock_price DOUBLE PRECISION NOT NULL,
                        term VARCHAR(50),
                        expiration_date VARCHAR(50) NOT NULL,
                        dte INTEGER NOT NULL,
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
                        breakeven_price DOUBLE PRECISION NOT NULL,
                        cushion_pct DOUBLE PRECISION,
                        score DOUBLE PRECISION NOT NULL,
                        earnings_date VARCHAR(50)
                    )
                '''))

                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) NOT NULL,
                        name VARCHAR(150),
                        subscribed_at VARCHAR(50) NOT NULL,
                        source VARCHAR(100) DEFAULT 'Weekly Leaderboard',
                        status VARCHAR(50) DEFAULT 'active'
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_top_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            target_type TEXT NOT NULL,
            rank INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            stock_price REAL NOT NULL,
            term TEXT,
            expiration_date TEXT NOT NULL,
            dte INTEGER NOT NULL,
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
            cushion_pct REAL,
            score REAL NOT NULL,
            earnings_date TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT,
            subscribed_at TEXT NOT NULL,
            source TEXT DEFAULT 'Weekly Leaderboard',
            status TEXT DEFAULT 'active'
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

def load_history(ticker: Optional[str] = None, limit: int = 20) -> pd.DataFrame:
    """Fetch historical screening data from cloud PostgreSQL or local SQLite (displays latest N rows)."""
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
    query += f" ORDER BY r.timestamp DESC LIMIT {int(limit)}"

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
    sqlite_query += f" ORDER BY r.timestamp DESC LIMIT {int(limit)}"

    df = pd.read_sql_query(sqlite_query, conn)
    conn.close()
    return df

def get_latest_snapshot(ticker: str) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Retrieve the most recent screening snapshot that contains valid option contracts from the database."""
    engine = _get_sqlalchemy_engine()
    
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                snap_row = conn.execute(
                    text("SELECT id, timestamp, ticker, current_price, purchase_price, earnings_date FROM stock_snapshots WHERE UPPER(ticker) = :t AND id IN (SELECT DISTINCT snapshot_id FROM option_results) ORDER BY id DESC LIMIT 1"),
                    {"t": ticker.upper()}
                ).mappings().first()
                
                if snap_row:
                    snapshot = dict(snap_row)
                    opt_rows = conn.execute(
                        text("SELECT expiration_date, dte, target_type, strike_price, bid, ask, premium, implied_volatility_pct, delta, prob_itm_pct, prob_touch_pct, premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct, breakeven_price FROM option_results WHERE snapshot_id = :sid ORDER BY dte ASC, strike_price ASC"),
                        {"sid": snapshot["id"]}
                    ).mappings().all()
                    
                    if not opt_rows:
                        return None
                        
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
        "SELECT id, timestamp, ticker, current_price, purchase_price, earnings_date FROM stock_snapshots WHERE UPPER(ticker) = ? AND id IN (SELECT DISTINCT snapshot_id FROM option_results) ORDER BY id DESC LIMIT 1",
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
    
    if not opt_rows:
        return None
        
    results = []
    for r in opt_rows:
        row_dict = dict(r)
        term_label = "2-Month" if row_dict["dte"] <= 75 else "3-Month"
        row_dict["term"] = f"{term_label} (~{row_dict['dte']}d)"
        results.append(row_dict)
    return snapshot, results

def save_weekly_top_picks(batch_id: str, picks_5pct: List[Dict[str, Any]], picks_10pct: List[Dict[str, Any]], timestamp: Optional[str] = None) -> str:
    """Persist weekly top covered call picks to PostgreSQL or SQLite."""
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_picks = []
    for rank, p in enumerate(picks_5pct, start=1):
        item = dict(p)
        item["target_type"] = "5% OTM"
        item["rank"] = rank
        all_picks.append(item)

    for rank, p in enumerate(picks_10pct, start=1):
        item = dict(p)
        item["target_type"] = "10% OTM"
        item["rank"] = rank
        all_picks.append(item)

    engine = _get_sqlalchemy_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.begin() as conn:
                insert_stmt = text('''
                    INSERT INTO weekly_top_picks (
                        batch_id, generated_at, target_type, rank, ticker, stock_price,
                        term, expiration_date, dte, strike_price, bid, ask, premium,
                        implied_volatility_pct, delta, prob_itm_pct, prob_touch_pct,
                        premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct,
                        breakeven_price, cushion_pct, score, earnings_date
                    ) VALUES (
                        :batch_id, :gen_at, :target_type, :rank, :ticker, :stock_price,
                        :term, :exp_date, :dte, :strike_price, :bid, :ask, :premium,
                        :iv, :delta, :prob_itm, :prob_touch,
                        :prem_roi, :ann_prem_roi, :max_roi, :ann_max_roi,
                        :breakeven, :cushion, :score, :earnings_date
                    )
                ''')
                for row in all_picks:
                    conn.execute(insert_stmt, {
                        "batch_id": batch_id,
                        "gen_at": timestamp,
                        "target_type": row.get("target_type", "5% OTM"),
                        "rank": row.get("rank", 1),
                        "ticker": row["ticker"].upper(),
                        "stock_price": float(row.get("stock_price", 0.0)),
                        "term": row.get("term", ""),
                        "exp_date": row.get("expiration_date", ""),
                        "dte": int(row.get("dte", 0)),
                        "strike_price": float(row.get("strike_price", 0.0)),
                        "bid": float(row.get("bid", 0.0) or 0.0),
                        "ask": float(row.get("ask", 0.0) or 0.0),
                        "premium": float(row.get("premium", 0.0)),
                        "iv": row.get("implied_volatility_pct"),
                        "delta": row.get("delta"),
                        "prob_itm": row.get("prob_itm_pct"),
                        "prob_touch": row.get("prob_touch_pct"),
                        "prem_roi": float(row.get("premium_roi_pct", 0.0)),
                        "ann_prem_roi": float(row.get("ann_premium_roi_pct", 0.0)),
                        "max_roi": float(row.get("max_roi_pct", 0.0)),
                        "ann_max_roi": float(row.get("ann_max_roi_pct", 0.0)),
                        "breakeven": float(row.get("breakeven_price", 0.0)),
                        "cushion": float(row.get("cushion_pct", 0.0)),
                        "score": float(row.get("score", 0.0)),
                        "earnings_date": row.get("earnings_date", "N/A")
                    })
            return batch_id
        except Exception as e:
            print(f"[Warning] Cloud DB saving weekly top picks failed: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for row in all_picks:
        cursor.execute('''
            INSERT INTO weekly_top_picks (
                batch_id, generated_at, target_type, rank, ticker, stock_price,
                term, expiration_date, dte, strike_price, bid, ask, premium,
                implied_volatility_pct, delta, prob_itm_pct, prob_touch_pct,
                premium_roi_pct, ann_premium_roi_pct, max_roi_pct, ann_max_roi_pct,
                breakeven_price, cushion_pct, score, earnings_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            batch_id, timestamp, row.get("target_type", "5% OTM"), row.get("rank", 1),
            row["ticker"].upper(), float(row.get("stock_price", 0.0)), row.get("term", ""), row.get("expiration_date", ""),
            int(row.get("dte", 0)), float(row.get("strike_price", 0.0)), float(row.get("bid", 0.0) or 0.0), float(row.get("ask", 0.0) or 0.0), float(row.get("premium", 0.0)),
            row.get("implied_volatility_pct"), row.get("delta"), row.get("prob_itm_pct"), row.get("prob_touch_pct"),
            float(row.get("premium_roi_pct", 0.0)), float(row.get("ann_premium_roi_pct", 0.0)), float(row.get("max_roi_pct", 0.0)), float(row.get("ann_max_roi_pct", 0.0)),
            float(row.get("breakeven_price", 0.0)), float(row.get("cushion_pct", 0.0)), float(row.get("score", 0.0)), row.get("earnings_date", "N/A")
        ))
    conn.commit()
    conn.close()
    return batch_id

def _seed_weekly_picks_if_empty() -> Dict[str, Any]:
    """Auto-seed weekly top picks from bundled weekly_top_picks.json if database has no records."""
    json_path = os.path.join(os.path.dirname(__file__), "data", "weekly_top_picks.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                records = json.load(f)
            if records:
                gen_at = records[0].get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                batch_id = "weekly-initial-seed"
                picks_5 = [r for r in records if r.get("target_type") == "5% OTM" or r.get("list") == "+5% OTM"]
                picks_10 = [r for r in records if r.get("target_type") == "10% OTM" or r.get("list") == "+10% OTM"]
                save_weekly_top_picks(batch_id, picks_5, picks_10, timestamp=gen_at)
                return {"5% OTM": picks_5, "10% OTM": picks_10, "batch_id": batch_id, "generated_at": gen_at}
        except Exception as e:
            print(f"[Warning] Auto-seeding from weekly_top_picks.json failed: {e}")
    return {"5% OTM": [], "10% OTM": [], "batch_id": None, "generated_at": None}

def get_latest_weekly_top_picks() -> Dict[str, Any]:
    """Retrieve the most recent batch of weekly top picks categorized by target type."""
    engine = _get_sqlalchemy_engine()
    
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                latest_batch_row = conn.execute(
                    text("SELECT batch_id, generated_at FROM weekly_top_picks WHERE batch_id NOT LIKE 'test-%' ORDER BY id DESC LIMIT 1")
                ).mappings().first()
                if not latest_batch_row:
                    # Fallback to any batch if only test batches exist
                    latest_batch_row = conn.execute(
                        text("SELECT batch_id, generated_at FROM weekly_top_picks ORDER BY id DESC LIMIT 1")
                    ).mappings().first()
                if not latest_batch_row:
                    return _seed_weekly_picks_if_empty()
                
                b_id = latest_batch_row["batch_id"]
                gen_at = latest_batch_row["generated_at"]
                
                rows = conn.execute(
                    text("SELECT * FROM weekly_top_picks WHERE batch_id = :bid ORDER BY rank ASC"),
                    {"bid": b_id}
                ).mappings().all()
                
                picks_5 = [dict(r) for r in rows if r["target_type"] == "5% OTM"]
                picks_10 = [dict(r) for r in rows if r["target_type"] == "10% OTM"]
                if not picks_5 and not picks_10:
                    return _seed_weekly_picks_if_empty()
                return {"5% OTM": picks_5, "10% OTM": picks_10, "batch_id": b_id, "generated_at": gen_at}
        except Exception as e:
            print(f"[Warning] Loading weekly picks from cloud DB failed: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT batch_id, generated_at FROM weekly_top_picks WHERE batch_id NOT LIKE 'test-%' ORDER BY id DESC LIMIT 1")
    latest_batch_row = cursor.fetchone()
    if not latest_batch_row:
        # Fallback to any batch
        cursor.execute("SELECT batch_id, generated_at FROM weekly_top_picks ORDER BY id DESC LIMIT 1")
        latest_batch_row = cursor.fetchone()
        
    if not latest_batch_row:
        conn.close()
        return _seed_weekly_picks_if_empty()
        
    b_id = latest_batch_row["batch_id"]
    gen_at = latest_batch_row["generated_at"]
    
    cursor.execute("SELECT * FROM weekly_top_picks WHERE batch_id = ? ORDER BY rank ASC", (b_id,))
    rows = cursor.fetchall()
    conn.close()
    
    picks_5 = [dict(r) for r in rows if r["target_type"] == "5% OTM"]
    picks_10 = [dict(r) for r in rows if r["target_type"] == "10% OTM"]
    if not picks_5 and not picks_10:
        return _seed_weekly_picks_if_empty()
    return {"5% OTM": picks_5, "10% OTM": picks_10, "batch_id": b_id, "generated_at": gen_at}

def swap_weekly_pick(target_type: str, old_ticker: str, new_pick: Dict[str, Any]) -> bool:
    """
    Swap an existing pick in the active weekly batch with a new challenger idea,
    re-ranking the list based on composite score.
    """
    latest = get_latest_weekly_top_picks()
    b_id = latest.get("batch_id")
    if not b_id:
        return False
        
    existing_list = latest.get(target_type, [])
    # Remove old ticker and ensure new ticker isn't already duplicated
    updated_list = [p for p in existing_list if p["ticker"].upper() != old_ticker.upper() and p["ticker"].upper() != new_pick["ticker"].upper()]
    
    # Add new pick
    new_item = dict(new_pick)
    new_item["target_type"] = target_type
    if "generated_at" not in new_item or not new_item["generated_at"]:
        new_item["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_list.append(new_item)
    
    # Sort by score descending
    updated_list.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    
    # Re-assign ranks 1..N
    for i, p in enumerate(updated_list, start=1):
        p["rank"] = i
        
    # Re-save the updated batch
    picks_5 = updated_list if target_type == "5% OTM" else latest.get("5% OTM", [])
    picks_10 = updated_list if target_type == "10% OTM" else latest.get("10% OTM", [])
    
    # Save as a revised batch
    revised_batch_id = f"{b_id}-rev-{datetime.now().strftime('%H%M%S')}"
    save_weekly_top_picks(revised_batch_id, picks_5, picks_10, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return True

def save_subscriber(email: str, name: str = "", source: str = "Weekly Leaderboard") -> bool:
    """Save a user's email address to the newsletter/report subscriber database."""
    cleaned_email = email.strip().lower()
    if not cleaned_email or "@" not in cleaned_email or "." not in cleaned_email:
        return False

    init_db()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    engine = _get_sqlalchemy_engine()
    
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.begin() as conn:
                conn.execute(text('''
                    INSERT INTO newsletter_subscribers (email, name, subscribed_at, source, status)
                    VALUES (:email, :name, :ts, :src, 'active')
                '''), {
                    "email": cleaned_email,
                    "name": name.strip(),
                    "ts": timestamp,
                    "src": source
                })
            return True
        except Exception as e:
            print(f"[Warning] Cloud DB saving subscriber failed: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO newsletter_subscribers (email, name, subscribed_at, source, status)
        VALUES (?, ?, ?, ?, 'active')
    ''', (cleaned_email, name.strip(), timestamp, source))
    conn.commit()
    conn.close()
    return True

def get_subscribers() -> pd.DataFrame:
    """Fetch list of all collected subscriber emails."""
    init_db()
    engine = _get_sqlalchemy_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                return pd.read_sql_query(text("SELECT id, email, name, subscribed_at, source, status FROM newsletter_subscribers ORDER BY id DESC"), conn)
        except Exception as e:
            print(f"[Warning] Cloud DB loading subscribers failed: {e}. Falling back to SQLite.")

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id, email, name, subscribed_at, source, status FROM newsletter_subscribers ORDER BY id DESC", conn)
    conn.close()
    return df