# Chatbot BE

Python Flask + SQLAlchemy + MySQL backend for the Chatbot application.

---

## Database Setup

### Fresh installation

Run `mysql.sql` against your MySQL database to create all tables with the correct schema:

```bash
mysql -h <host> -P <port> -u <user> -p <database> < mysql.sql
```

### Migrating an existing Railway database

If your Railway database was provisioned from an older version of `mysql.sql` that was missing the `Role` column, the application will crash with:

```
Unknown column 'users.Role' in 'field list'
```

Apply the migration script to add the missing column:

```bash
mysql -h <host> -P <port> -u <user> -p <database> < src/migrations/add_role_column.sql
```

The script uses `ADD COLUMN IF NOT EXISTS`, so it is safe to run more than once.

#### Using Railway CLI

```bash
# Open an interactive MySQL session via the Railway CLI
railway connect MySQL

# Then inside the MySQL shell:
source src/migrations/add_role_column.sql
```

---

## Running the application

```bash
pip install -r requirements.txt
python -m src.app
```
