import sqlite3
from flask import Flask, render_template_string, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret"   # needed for login sessions


# ---------- Database ----------
def db(sql, args=()):
    """Run any SQL command and return the rows."""
    conn = sqlite3.connect("worthit.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, args).fetchall()
    conn.commit()
    conn.close()
    return rows


db("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
   "email TEXT, password TEXT, wage REAL)")
db("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
   "user_id INTEGER, title TEXT, amount REAL, verdict TEXT)")


# ---------- HTML (every page = TOP + page + BOTTOM) ----------
TOP = """
<!doctype html>
<html>
<head>
  <title>WorthIt</title>
  <style>
    body { font-family: Arial; max-width: 700px; margin: 30px auto; padding: 0 15px; background: #f2f5f9; }
    .box { background: white; padding: 15px; margin-bottom: 15px; border-radius: 6px; }
    .red { color: crimson; }
    table { width: 100%; }
    td, th { text-align: left; padding: 6px; }
  </style>
</head>
<body>
  <h1>WorthIt - Spend Smarter</h1>
  {% if user %}<p>{{ user.email }} - <a href="/logout">Log out</a></p>{% endif %}
"""

BOTTOM = "</body></html>"

LOGIN_PAGE = TOP + """
<div class="box">
  <h3>Log in</h3>
  {% if error %}<p class="red">{{ error }}</p>{% endif %}
  <form method="post">
    <p><input name="email" type="email" placeholder="Email" required></p>
    <p><input name="password" type="password" placeholder="Password" required></p>
    <button>Log in</button>
  </form>
  <p>New here? <a href="/register">Create an account</a></p>
</div>
""" + BOTTOM

REGISTER_PAGE = TOP + """
<div class="box">
  <h3>Create your account</h3>
  {% if error %}<p class="red">{{ error }}</p>{% endif %}
  <form method="post">
    <p><input name="email" type="email" placeholder="Email" required></p>
    <p><input name="password" type="password" placeholder="Password" required></p>
    <p><input name="wage" type="number" step="0.01" min="1" placeholder="Your hourly wage" required></p>
    <button>Sign up</button>
  </form>
  <p>Already have an account? <a href="/login">Log in</a></p>
</div>
""" + BOTTOM

DASHBOARD_PAGE = TOP + """
<div class="box">
  <p>Total spent: <b>{{ total }}</b></p>
  <p>Hours of work spent: <b>{{ hours }}</b></p>
  <p>Lost to regret: <b class="red">{{ regret_total }}</b></p>
</div>

<div class="box">
  <h3>Add an expense</h3>
  <form method="post" action="/add">
    <input name="title" placeholder="What did you buy?" required>
    <input name="amount" type="number" step="0.01" min="0" placeholder="Amount" required>
    <button>Add</button>
  </form>
</div>

<div class="box">
  <h3>Your expenses</h3>
  <table>
    <tr><th>Item</th><th>Amount</th><th>Work hours</th><th>Worth it?</th><th></th></tr>
    {% for e in expenses %}
    <tr>
      <td>{{ e.title }}</td>
      <td>{{ e.amount }}</td>
      <td>{{ (e.amount / user.wage)|round(1) }}</td>
      <td>
        {{ e.verdict or "not rated" }}
        <a href="/rate/{{ e.id }}/worth">😍</a>
        <a href="/rate/{{ e.id }}/meh">😐</a>
        <a href="/rate/{{ e.id }}/regret">😭</a>
      </td>
      <td><a href="/delete/{{ e.id }}">Delete</a></td>
    </tr>
    {% endfor %}
  </table>
</div>
""" + BOTTOM


# ---------- Helper ----------
def get_user():
    """Return the logged-in user, or None."""
    if "user_id" in session:
        rows = db("SELECT * FROM users WHERE id = ?", (session["user_id"],))
        if rows:
            return rows[0]
    return None


# ---------- Pages ----------
@app.route("/")
def home():
    return redirect("/dashboard")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        if db("SELECT id FROM users WHERE email = ?", (email,)):
            return render_template_string(REGISTER_PAGE, error="Email already registered.")

        password = generate_password_hash(request.form["password"])
        db("INSERT INTO users (email, password, wage) VALUES (?, ?, ?)",
           (email, password, float(request.form["wage"])))
        session["user_id"] = db("SELECT id FROM users WHERE email = ?", (email,))[0]["id"]
        return redirect("/dashboard")
    return render_template_string(REGISTER_PAGE)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        rows = db("SELECT * FROM users WHERE email = ?", (request.form["email"],))
        if rows and check_password_hash(rows[0]["password"], request.form["password"]):
            session["user_id"] = rows[0]["id"]
            return redirect("/dashboard")
        return render_template_string(LOGIN_PAGE, error="Wrong email or password.")
    return render_template_string(LOGIN_PAGE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/dashboard")
def dashboard():
    user = get_user()
    if user is None:
        return redirect("/login")

    # Only this user's expenses, so every user sees only their own data
    expenses = db("SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user["id"],))

    total = 0
    regret_total = 0
    for e in expenses:
        total = total + e["amount"]
        if e["verdict"] == "regret":
            regret_total = regret_total + e["amount"]

    hours = round(total / user["wage"], 1)   # work hours the spending cost
    return render_template_string(DASHBOARD_PAGE, user=user, expenses=expenses,
                                  total=round(total, 2), hours=hours,
                                  regret_total=round(regret_total, 2))


@app.route("/add", methods=["POST"])
def add():
    user = get_user()
    if user is None:
        return redirect("/login")
    db("INSERT INTO expenses (user_id, title, amount) VALUES (?, ?, ?)",
       (user["id"], request.form["title"], float(request.form["amount"])))
    return redirect("/dashboard")


@app.route("/rate/<int:expense_id>/<verdict>")
def rate(expense_id, verdict):
    user = get_user()
    if user is None:
        return redirect("/login")
    db("UPDATE expenses SET verdict = ? WHERE id = ? AND user_id = ?",
       (verdict, expense_id, user["id"]))
    return redirect("/dashboard")


@app.route("/delete/<int:expense_id>")
def delete(expense_id):
    user = get_user()
    if user is None:
        return redirect("/login")
    db("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user["id"]))
    return redirect("/dashboard")


if __name__ == "__main__":
    app.run(debug=True)
