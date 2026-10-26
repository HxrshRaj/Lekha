# Azure readiness (NOT deployed to Azure by the author)

Nothing in this folder has been run against Azure. It is a prepared set of steps and configuration so that the same
SQL layer and API can be put on **Azure SQL Database** and **Azure App Service**. When you do it, capture the screenshots
listed at the bottom and only then describe it as "deployed on Azure".

All data is SYNTHETIC and SAP-STYLE (simplified).

## What differs on Azure SQL Database
The scripts in `sql/` target SQL Server (Docker / CI). Azure SQL Database needs two small adjustments, which
`deploy_sql.py` applies at run time (the files in `sql/` are not changed):

| Script content | Azure SQL Database | Handling |
|---|---|---|
| `IF DB_ID('lekha') IS NULL CREATE DATABASE lekha;` | cannot create or switch databases inside a script | line removed; create the DB with `az sql db create` |
| `USE lekha;` | not supported | line removed; the connection already targets the database |

`MERGE`, `PERCENTILE_CONT ... OVER`, `FOR JSON` and schema-bound indexed views are supported on Azure SQL Database
(not verified here - this is the first thing to check when you run it).

## Step 1 - SQL layer (Azure SQL Database)
```bash
az login
az group create -n lekha-rg -l westeurope
az sql server create -g lekha-rg -n <unique-sql-server-name> -l westeurope -u lekhaadmin -p "<strong-password>"
az sql server firewall-rule create -g lekha-rg -s <unique-sql-server-name> -n myip --start-ip-address <your-ip> --end-ip-address <your-ip>
# General Purpose serverless with auto-pause is the cheapest option for a demo (check current pricing / free offer in the portal)
az sql db create -g lekha-rg -s <unique-sql-server-name> -n lekha --edition GeneralPurpose --family Gen5 --capacity 1 --compute-model Serverless --auto-pause-delay 60
```
Then from the repo root:
```bash
pip install -r backend/requirements-dev.txt
export AZURE_SQL_SERVER=<unique-sql-server-name>.database.windows.net
export AZURE_SQL_DB=lekha AZURE_SQL_USER=lekhaadmin AZURE_SQL_PASSWORD="<strong-password>"
python azure/deploy_sql.py --scale 0.2      # schema, staging load, usp_CleanAll, views
```
Check in the portal Query editor: `SELECT * FROM dbo.vw_AR_Aging; SELECT REASON, COUNT(*) FROM dbo.Quarantine GROUP BY REASON;`

## Step 2 - API on Azure App Service
The API serves precomputed results, so it does not need the database. (Pointing it at Azure SQL would be a code change that is not made here.)
```bash
az appservice plan create -g lekha-rg -n lekha-plan --is-linux --sku B1
az webapp create -g lekha-rg -p lekha-plan -n <unique-app-name> --runtime "PYTHON:3.11"
az webapp config set -g lekha-rg -n <unique-app-name> --startup-file "bash startup.sh"
az webapp config appsettings set -g lekha-rg -n <unique-app-name> --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
(cd frontend && npm ci && npm run build) && rm -rf backend/static && cp -r frontend/dist backend/static
cp azure/startup.sh backend/startup.sh
(cd backend && zip -r ../lekha.zip . -x "tests/*" "__pycache__/*" "*.pyc")
az webapp deploy -g lekha-rg -n <unique-app-name> --src-path lekha.zip --type zip
```
Browse to `https://<unique-app-name>.azurewebsites.net/` (dashboard) and `/docs` (API).

## Screenshots to capture (evidence)
1. Azure portal: resource group `lekha-rg` listing the SQL server, SQL database and App Service.
2. Azure SQL Query editor result of `SELECT * FROM dbo.vw_AR_Aging` and of the quarantine summary.
3. The App Service URL open on `/` and on `/docs`, with the URL bar visible.
4. App Service "Log stream" or "Deployment Center" showing a successful start.

Delete the resource group afterwards to stop charges: `az group delete -n lekha-rg`.
