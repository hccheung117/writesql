# WriteSQL

[![PyPI](https://img.shields.io/pypi/v/writesql.svg)](https://pypi.org/project/writesql/)
[![CI](https://github.com/hccheung117/writesql/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hccheung117/writesql/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hccheung117/writesql/branch/main/graph/badge.svg)](https://codecov.io/gh/hccheung117/writesql)
[![License](https://img.shields.io/pypi/l/writesql.svg)](https://github.com/hccheung117/writesql/blob/main/LICENSE)

**No ORM, no DSL, just SQL.**

Write analytics in pure SQL. Make it dynamic, typed, and reusable in Python. No messy string concatenation. No ORMs hiding your queries.

---

## The Problem with Dynamic SQL

You're working on the data side of a new revenue dashboard. 

You do what you always do: you open DataGrip (or your favorite database console) and write a perfect, handcrafted SQL query. It's clean, it's standard SQL, and it runs flawlessly:

```sql
SELECT id, amount, user_id
FROM orders
WHERE status = 'completed'
  AND created_at >= '2024-01-01'
  AND created_at < '2024-02-01'
  AND region IN ('EU', 'US');
```

Beautiful. It's easy to read, test, and explain to anyone on the team. 

Now the camera pans to the dashboard backend. You need to put this query into a Python API endpoint. The catch? Those dates and regions need to be dynamic based on the user's request.

**The pain: How do you make this dynamic without ruining it?**

*   **Attempt 1: String Concatenation.**
    You try piecing the query together dynamically:
    ```python
    query = "SELECT id, amount, user_id FROM orders WHERE status = 'completed'"
    if start_date:
        query += f" AND created_at >= '{start_date}'"
    if end_date:
        query += f" AND created_at < '{end_date}'"
    if regions:
        query += f" AND region IN ({','.join(['?']*len(regions))})"
    ```
    *The Result:* It's ugly, error-prone (missing spaces, trailing `AND`s), and visually breaks the SQL. If you go back to this code a month later, you can no longer see the shape of the query.

*   **Attempt 2: The ORM.**
    You give up on strings and translate it to an ORM (like SQLAlchemy):
    ```python
    query = session.query(Order).filter(Order.status == 'completed')
    if start_date:
        query = query.filter(Order.created_at >= start_date)
    if end_date:
        query = query.filter(Order.created_at < end_date)
    if regions:
        query = query.filter(Order.region.in_(regions))
    ```
    *The Result:* The SQL is completely hidden. Your beautiful, standard SQL query has been replaced by a wall of Python methods. When you need to add complex analytical groupings later, you'll have to fight the ORM API instead of just writing SQL.

---

## How It Works

You want a truce. You want the joy of writing pure SQL in your data console, *and* you want typed, composable Python functions for the API.

### Write standard SQL

With WriteSQL, the SQL stays exactly as you wrote it, just wrapped in a Python function using native f-strings. 

```python
from writesql import statement

@statement
def get_orders(start_date: str, end_date: str, regions: list[str]) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders
    WHERE status = 'completed'
      AND created_at >= {start_date}
      AND created_at < {end_date}
      AND region IN {regions}
    """
```

*The Magic:* It's just a native Python f-string. The SQL shape is perfectly preserved. It's typed, editor-friendly, and WriteSQL smartly formats Python lists into SQL `IN` clauses (e.g., turning `['EU', 'US']` into `('EU', 'US')`) automatically so your SQL stays clean.

### Use identifiers for tables and columns

So far `start_date`, `end_date`, and `regions` are all *values* — WriteSQL quotes them as SQL literals. But sometimes the table or column name itself needs to be dynamic. Your dashboard might run against `orders` in production and `orders_staging` in preview, or an analyst might want to swap the whole `FROM` clause to query a materialized view.

A table name is not a value — it's an identifier. Quoting it as a string would produce invalid SQL. Annotate the parameter with `Table` (or `Column`) and WriteSQL will emit it verbatim after strict validation:

```python
from writesql import statement, Table

@statement
def get_orders(source: Table, start_date: str, end_date: str, regions: list[str]) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM {source}
    WHERE status = 'completed'
      AND created_at >= {start_date}
      AND created_at < {end_date}
      AND region IN {regions}
    """

get_orders(
    source="analytics.orders",
    start_date="2024-01-01",
    end_date="2024-02-01",
    regions=["EU", "US"],
)
# SELECT id, amount, user_id
# FROM analytics.orders
# WHERE status = 'completed'
#   AND created_at >= '2024-01-01'
#   ...
```

*The Magic:* The f-string still looks like SQL — no wrappers at the call site. `Table` and `Column` are type aliases for `str`, so your editor autocompletes and type-checks as normal. Values are validated against a strict identifier pattern (letters, digits, underscores, and dots), so unsafe input like `"orders; DROP TABLE users"` is rejected with `InvalidIdentifier` before it ever reaches the database.

### Compose reusable fragments

That's great for one query. But what if you have 5 different dashboard endpoints that *all* need that exact same date and region filtering logic? You don't want to copy-paste those `WHERE` clauses into every single statement.

We extract that shared logic into a reusable `@clause`. A clause renders the inside of a SQL block.

```python
from writesql import clause, statement

@clause
def dashboard_filters(start_date: str, end_date: str, regions: list[str]) -> str:
    return f"""
      AND created_at >= {start_date}
      AND created_at < {end_date}
      AND region IN {regions}
    """

@statement
def get_orders(
    start_date: str,
    end_date: str,
    regions: list[str],
    filters=dashboard_filters,
) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders
    WHERE status = 'completed'
      {filters}
    """
```

*The Magic:* The statement remains pure SQL structure. The dynamic logic is isolated, testable, and reusable. By injecting the clause as a default parameter, dependencies are beautifully explicit.

### Pass parameters naturally

Because these are just Python functions, you can always pass parameters explicitly when they belong to the statement you're calling. If you're in a FastAPI route, you can call that statement directly:

```python
@statement
def get_orders_for_range(start_date: str, end_date: str, regions: list[str]) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders
    WHERE status = 'completed'
      AND created_at >= {start_date}
      AND created_at < {end_date}
      AND region IN {regions}
    """

@app.get("/orders")
def api_get_orders(start_date: str, end_date: str, regions: list[str]):
    sql = get_orders_for_range(
        start_date=start_date,
        end_date=end_date,
        regions=regions
    )
    return db.execute(sql)
```

### Bind parameters for execution

The examples above render values as SQL literals, which keeps the SQL easy to inspect and preserves compatibility. For database execution, configure parameter binding once during application setup and WriteSQL will return a string-compatible compiled value with driver-ready SQL plus collected params:

```python
from writesql import parameterize, statement

parameterize("sequence", placeholder=lambda p: "?")

@statement
def get_orders_for_range(start_date: str, end_date: str, regions: list[str]) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders
    WHERE status = 'completed'
      AND created_at >= {start_date}
      AND created_at < {end_date}
      AND region IN {regions}
    """

sql = get_orders_for_range(
    start_date="2024-01-01",
    end_date="2024-02-01",
    regions=["EU", "US"],
)

cursor.execute(str(sql), sql.params)

str(sql)
# SELECT id, amount, user_id
# FROM orders
# WHERE status = 'completed'
#   AND created_at >= ?
#   AND created_at < ?
#   AND region IN (?, ?)

sql.params
# ["2024-01-01", "2024-02-01", "EU", "US"]

sql.debug_sql
# SELECT id, amount, user_id
# FROM orders
# WHERE status = 'completed'
#   AND created_at >= '2024-01-01'
#   AND created_at < '2024-02-01'
#   AND region IN ('EU', 'US')
```

`str(sql)` stays compatible with APIs that expect a normal string. `sql.params` is the value container to pass to your database driver. `sql.debug_sql` is for local debugging and test assertions, not for execution; it may contain sensitive values and is not a replacement for bound parameters.

### Share context globally

But what happens when your application grows? What if `get_orders` is buried three layers deep inside a reporting service? Or what if *every* query in your multi-tenant app needs a `tenant_id` filter?

Normally, you'd have to pass `tenant_id` down through every single Python function in your application just to get it to the SQL layer (prop-drilling).

With WriteSQL, you can just `share()` runtime context at the top of the request (like in a FastAPI dependency or middleware).

```python
from writesql import clause, statement, share

@clause
def tenant_filter(tenant_id: int) -> str:
    return f"AND tenant_id = {tenant_id}"

@statement
def get_orders(filters=tenant_filter) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders
    WHERE status = 'completed'
      {filters}
    """

# In a FastAPI Middleware or Dependency:
def set_tenant_context(request: Request):
    tenant_id = get_tenant_from_token(request)
    # Bind the context globally for this request
    share(tenant_filter, {"tenant_id": tenant_id})

@app.get("/orders")
def api_get_orders():
    # We don't have to pass tenant_id here!
    # get_orders() automatically resolves it from the shared context.
    sql = get_orders()
    return db.execute(sql)
```

### Map reusable filters to local columns

Sometimes the reusable filter logic is the same, but each statement needs different physical column names or table aliases. Keep the runtime values shared, and map the columns where the clause appears:

```python
from writesql import Columns, clause, share, statement

@clause
def dashboard_filters(
    columns: Columns,
    start_date: str,
    end_date: str,
    regions: list[str],
) -> str:
    return f"""
      AND {columns.date} >= {start_date}
      AND {columns.date} < {end_date}
      AND {columns.region} IN {regions}
    """

@statement
def get_orders(filters=dashboard_filters) -> str:
    return f"""
    SELECT id, amount, user_id
    FROM orders o
    WHERE status = 'completed'
      {filters.on(
          date="o.created_at",
          region="o.region",
      )}
    """

@statement
def get_users(filters=dashboard_filters) -> str:
    return f"""
    SELECT id, email
    FROM users u
    WHERE u.active = TRUE
      {filters.on(
          date="u.signup_at",
          region="u.region",
      )}
    """

share(dashboard_filters, {
    "start_date": "2024-01-01",
    "end_date": "2024-02-01",
    "regions": ["EU", "US"],
})
```

---

## Core Principles

WriteSQL exists to avoid query-building patterns, not to provide a nicer version of them.

1. **Native Python f-strings:** Autocomplete, type hints, variable resolution, and imports work out of the box without learning a custom template language.
2. **SQL-first statements:** The returned f-string should look like the final SQL. Reviewers shouldn't need to chase helper functions to understand the query shape.
3. **Flat Names and Explicit Namespaces:** Runtime values should use semantic local variables (e.g., `{start_date}`), not complex object attribute chains inside the SQL (e.g., `{ctx.filters.date_filter}`). Use explicit WriteSQL namespaces, such as `{columns.date}`, when they improve SQL readability by distinguishing identifiers from values.
4. **Declarative:** Avoid conditionally appending or procedurally assembling SQL string fragments. Keep query structure in statements; put unavoidable dynamic SQL assembly into named clauses.

---

## Roadmap

*   **v0.3 SQLModel integration:** First-class integration with SQLModel.
*   **v0.4 SQLAlchemy integration:** First-class integration with SQLAlchemy.
