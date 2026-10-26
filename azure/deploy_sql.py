"""Apply the Lekha T-SQL layer to an Azure SQL Database (NOT executed by the repo author; see azure/README.md).

Env: AZURE_SQL_SERVER, AZURE_SQL_DB, AZURE_SQL_USER, AZURE_SQL_PASSWORD.
Strips the two statements Azure SQL Database does not allow inside a script (CREATE DATABASE / USE) and reuses lekha.sqlserver.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import pymssql  # noqa: E402

from lekha import sqlserver  # noqa: E402
from lekha.tables import AS_OF, build  # noqa: E402


def azure_script(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^IF DB_ID\('lekha'\) IS NULL CREATE DATABASE lekha;\s*$", "", text, flags=re.M)
    return re.sub(r"^USE lekha;\s*$", "", text, flags=re.M)


def main(scale: float) -> None:
    conn = pymssql.connect(server=os.environ["AZURE_SQL_SERVER"], user=os.environ["AZURE_SQL_USER"], password=os.environ["AZURE_SQL_PASSWORD"],
                           database=os.environ["AZURE_SQL_DB"], autocommit=True, login_timeout=60)
    tmp = Path(__file__).parent / "_tmp"
    tmp.mkdir(exist_ok=True)
    scripts = []
    for f in ["01_schema.sql", "02_clean.sql", "03_views.sql", "04_indexed_view.sql"]:
        p = tmp / f
        p.write_text(azure_script(sqlserver.SQL_DIR / f), encoding="utf-8")
        scripts.append(p)
    _, truth, stg, _, _ = build(42, scale)
    sqlserver.run_script(conn, scripts[0])
    sqlserver.run_script(conn, scripts[1])
    for name in sqlserver.GL_LOAD:
        sqlserver.bulk_insert(conn, f"dbo.{name}", truth[name])
    for name, df in stg.items():
        sqlserver.bulk_insert(conn, f"stg.{name}", df)
    conn.cursor().execute("UPDATE dbo.Params SET AsOfDate = %s", (str(AS_OF.date()),))
    conn.cursor().execute("EXEC dbo.usp_CleanAll")
    sqlserver.run_script(conn, scripts[2])
    sqlserver.run_script(conn, scripts[3])
    print("done. Try: SELECT * FROM dbo.vw_AR_Aging")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.2)
    main(ap.parse_args().scale)
