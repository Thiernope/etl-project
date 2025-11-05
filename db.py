# db.py
import os
from getpass import getpass
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from contextlib import contextmanager
from IPython.core.magic import register_cell_magic

# optional: load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def _env_or_prompt(name, prompt_text=None, default=None):
    val = os.getenv(name)
    if val:
        return val
    if default is not None:
        return default
    if prompt_text is None:
        prompt_text = f"{name}: "
    return getpass(prompt_text)  # masked prompt for secrets

def get_engine(
    user_env="DB_USER",
    pass_env="DB_PASS",
    host_env="DB_HOST",
    port_env="DB_PORT",
    db_env="DB_NAME",
    driver_env="DB_DRIVER",
    default_driver="mysql+mysqlconnector"
):
    """
    Build and return a SQLAlchemy engine.
    Reads environment variables in this order:
      DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME, DB_DRIVER
    If a value is missing it prompts (password is masked).
    """
    user = _env_or_prompt(user_env, prompt_text="DB user (if empty use root): ", default="root")
    password = _env_or_prompt(pass_env, prompt_text=f"Password for {user}@DB: ")
    host = _env_or_prompt(host_env, default="127.0.0.1")
    port = _env_or_prompt(port_env, default="3306")
    dbname = _env_or_prompt(db_env, prompt_text="Database name: ")
    driver = os.getenv(driver_env, default_driver)

    # ensure password is URL-encoded
    pw_esc = quote_plus(password)
    conn_str = f"{driver}://{user}:{pw_esc}@{host}:{port}/{dbname}"
    engine = create_engine(conn_str, future=True)
    return engine

@contextmanager
def get_conn(engine):
    """Context manager: with get_conn(engine) as conn: ..."""
    with engine.connect() as conn:
        yield conn

def _pretty_print(cols, rows):
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i,c in enumerate(cols)]
    fmt = " | ".join(f"{{:{w}}}" for w in widths)
    print(fmt.format(*cols))
    print("-+-".join("-"*w for w in widths))
    for r in rows:
        print(fmt.format(*[("" if x is None else str(x)) for x in r]))

def run_sql(sql_text, engine=None, return_results=False):
    """
    Execute SQL and print results.
    - If return_results=True -> returns (cols, rows)
    - engine: SQLAlchemy engine (if None, will build one interactively via get_engine())
    """
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        # try single block execution
        try:
            res = conn.exec_driver_sql(sql_text)
        except Exception as e:
            # fallback: split by semicolon and run separately
            stmts = [s.strip() for s in sql_text.split(";") if s.strip()]
            for s in stmts:
                res = conn.exec_driver_sql(s)
                if getattr(res, "returns_rows", False):
                    rows = res.fetchall()
                    cols = res.keys()
                    _pretty_print(cols, rows)
                else:
                    print(f"{res.rowcount} rows affected.")
            return None if not return_results else ([], [])
        if getattr(res, "returns_rows", False):
            rows = res.fetchall()
            cols = res.keys()
            _pretty_print(cols, rows)
            return (cols, rows) if return_results else None
        else:
            print(f"{res.rowcount} rows affected.")
            return None if not return_results else ([], [])

def register_magic(engine=None):
    """
    Register a '%%runsql' cell magic in the current IPython session.
    After calling register_magic(engine), you can use:
        %%runsql
        SELECT * FROM table;
    """
    @register_cell_magic
    def runsql(line, cell):
        nonlocal engine
        if engine is None:
            engine = get_engine()
        sql_text = cell
        run_sql(sql_text, engine=engine)
    # return the engine for convenience
    return engine
