import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    stock_data = []
    gtd = 0.0
    """Show portfolio of stocks"""

    # collate each users purchases
    rows = db.execute("SELECT stock, sname, SUM(shares) FROM purchases WHERE uid = :uid group by stock", uid= session["user_id"])
    print(rows)
    for row in rows:
        stock = row['stock']
        shares = row['SUM(shares)']

        price = lookup(stock)['price']
        total = float(price) * int(shares)
        gtd += total
        total = "{:.2f}".format(total)
        stock_data.append([stock, row['sname'], shares, price, total])


    # add the cash row
    cash_left = db.execute("SELECT cash FROM users WHERE id = :uid", uid= session["user_id"])[0]['cash']
    gtd += float(cash_left)
    cash_left = "{:.2f}".format(cash_left)
    stock_data.append(['CASH', None, None, None, cash_left])

    return render_template("index.html", sd = stock_data, gtd = round(gtd, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    shares = 0
    if request.method == "POST":
        """Buy shares of stock"""
        shares = request.form.get("shares")
        if not shares.isnumeric():
            return apology("Need a postive number of shares")
        if int(shares) <= 0:
            return apology("Need a postive number of shares")

        stock = request.form.get("symbol")
        # do we have enough of those shares?


        info = lookup(stock)
        if info == None:
            return apology("Stock not found")
        price = info["price"]
        sname = info["name"]
        # Query database for cash

        cash_left = db.execute("SELECT cash FROM users WHERE id = :uid", uid= session["user_id"])[0]['cash']

        spend = float(price) * int(shares)
        if cash_left < spend:
            return apology("you don't have money!")

        # create purchases table if not existing
        db.execute("create table if not exists purchases (id integer primary key, uid integer not null, stock text not null, sname text not null, shares integer not null, price real not null, pdate timestamp, foreign key(uid) references users(id))")

        # if table present, just insert the purchase by the user
        uid = session["user_id"]
        db.execute("insert into purchases (uid, stock, sname, shares, price, pdate) VALUES(?,?,?,?,?,?)", (uid, stock, sname, shares, price, datetime.now()))

        # update the latest cash holding
        newcash = cash_left - spend
        db.execute("update users set cash = :cash where id = :uid", uid = uid, cash=newcash)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    pd = []

    # collate each users purchases
    rows = db.execute("SELECT stock, shares, price, pdate FROM purchases WHERE uid = :uid", uid= session["user_id"])
    print(rows)
    for row in rows:
        pd.append([row['stock'], row['shares'], row['price'], row['pdate']])


    return render_template("history.html", sd = pd)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = request.form.get("symbol")
        info = lookup(stock)
        if info == None:
            return render_template("quoted.html", stock="NONE", price=0.0 )
        price = info["price"]
        cname = info["name"]
        return render_template("quoted.html", stock=cname, price=price )
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        uname = request.form.get("username")
        print(uname)

        if not uname:
            return apology("Need Name to register")
        p = request.form.get("password")
        c = request.form.get("confirmation")
        if len(p) == 0:
            return apology("Password cannot be blank")
        if p != c:
            return apology("Passwords do not match")

        #
        sq = "INSERT INTO users (username, hash, cash) VALUES(?,?,?)"
        h = generate_password_hash(p)
        cash = 10000.00
        db.execute(sq, (uname, h, cash ))
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    shares = 0
    holding = 0
    if request.method == "POST":
        """Buy shares of stock"""
        shares = request.form.get("shares")
        if not shares.isnumeric():
            return apology("Need a postive number of shares")
        if int(shares) <= 0:
            return apology("Need a postive number of shares")
        stock = request.form.get("symbol")

        # do we have enough of those?
        rows = db.execute("SELECT SUM(shares) FROM purchases WHERE stock = :stock group by stock", stock= stock)

        if len(rows) > 0:
            holding = rows[0]['SUM(shares)']
        else:
            return apology("You don't hold that stock")
        if int(holding) < int(shares):
            return apology("You don't hold those many shares to sell!")

        info = lookup(stock)
        if info == None:
            return apology("Stock listing not found")

        # all good - we can sell: get price, multiply, add to cash, insert purchases table with negative integer so sum works correctly
        price = info["price"]
        sale = float(price) * int(shares)
        # Query database for cash
        cash_left = db.execute("SELECT cash FROM users WHERE id = :uid", uid= session["user_id"])[0]['cash']
        newcash = cash_left + sale

        uid = session["user_id"]
        db.execute("update users set cash = :cash where id = :uid", uid = uid, cash=newcash)

        shares = int(shares)
        shares *= -1
        sname = info['name']
        db.execute("insert into purchases (uid, stock, sname, shares, price, pdate) VALUES(?,?,?,?,?,?)", (uid, stock, sname, shares, price, datetime.now()))

        return redirect("/")
    else:
        return render_template("sell.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
