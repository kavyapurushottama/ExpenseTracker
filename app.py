# A simple Flask application. It includes routes for user registration, login, logout, adding expenses, and fetching expenses. It also includes a route for fetching the total expenses per category for displaying graphs.

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from bson.objectid import ObjectId
from collections import defaultdict
import config

app = Flask(__name__)
app.config.from_object(config)

mongo = PyMongo(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
app.secret_key = config.SECRET_KEY  # Required for flash messages

# User Model
class User(UserMixin):
    def __init__(self, username, email, password, _id=None):
        self.username = username
        self.email = email
        self.password = password
        self.id = _id

    def save_to_db(self):
        hashed_pw = bcrypt.generate_password_hash(self.password).decode("utf-8")
        user_data = {"username": self.username, "email": self.email, "password": hashed_pw}
        return mongo.db.users.insert_one(user_data)

    @staticmethod
    def find_by_email(email):
        return mongo.db.users.find_one({"email": email})

@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    return User(user_data["username"], user_data["email"], user_data["password"], str(user_data["_id"])) if user_data else None

# Routes
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        if User.find_by_email(email):
            flash("Email already exists!", "danger")
            return redirect(url_for("register"))
        
        new_user = User(username, email, password)
        new_user.save_to_db()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user_data = User.find_by_email(email)
        
        if user_data and bcrypt.check_password_hash(user_data["password"], password):
            user = User(user_data["username"], user_data["email"], user_data["password"], str(user_data["_id"]))
            login_user(user)
            return redirect(url_for("dashboard"))  # Redirect to manage expenses

        flash("Invalid credentials!", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        category = request.form["category"]
        amount = float(request.form["amount"])
        date_str = request.form["date"]
        date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        expense_data = {
            "user_id": str(current_user.id),
            "category": category,
            "amount": amount,
            "date": date,
            "type": "Debit"  
        }
        mongo.db.expenses.insert_one(expense_data)
        flash("Expense added successfully!", "success")
        return redirect(url_for("dashboard"))  
    return render_template("dashboard.html")  


@app.route("/manage_expenses", methods=["GET", "POST"])
@login_required
def manage_expenses():
    if request.method == "POST":
        category = request.form["category"]
        amount = float(request.form["amount"])
        date_str = request.form["date"]
        transaction_type = request.form.get("transaction_type")  
        if transaction_type not in ["Credit", "Debit"]:
            return jsonify({"error": "Invalid transaction type"}), 400
        date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        expense_data = {
            "user_id": str(current_user.id),
            "category": category,
            "amount": amount,
            "date": date,
            "type": transaction_type
        }
        mongo.db.expenses.insert_one(expense_data)
        flash("Transaction added successfully!", "success")
    expenses = list(mongo.db.expenses.find({"user_id": str(current_user.id)}))

    for expense in expenses:
        expense["_id"] = str(expense["_id"])
        expense["date"] = expense["date"]

    total_income = sum(exp["amount"] for exp in expenses if exp.get("type") == "Credit")
    total_expense = sum(exp["amount"] for exp in expenses if exp.get("type") == "Debit")
    total_cash = total_income - total_expense  
    warning_message = None
    if total_cash <= 0:
        warning_message = "⚠️ Warning! You have spent all your cash!"
    elif total_cash <= (total_income * 0.1):  # 90% spent
        warning_message = "⚠️ Warning! You have used more than 90% of your cash!"
    elif total_cash <= (total_income * 0.5):  # 50% spent
        warning_message = "⚠️ Alert! You have used more than 50% of your cash!"

    return render_template(
    "manage_expenses.html", 
    expenses=expenses, 
    total_cash=total_cash,
    total_income=total_income,
    total_expense=total_expense,
    warning_message=warning_message
)

@app.route("/plans", methods=["GET", "POST"])
@login_required
def plans():
    if request.method == "POST":
        plan_name = request.form["plan_name"]
        amount = float(request.form["amount"])
        date_str = request.form["date"]
        status = request.form["status"]
        date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")

        plan_data = {
            "user_id": str(current_user.id),
            "plan_name": plan_name,
            "amount": amount,
            "date": date,
            "status": status
        }
        mongo.db.plans.insert_one(plan_data)
        flash("Plan added successfully!", "success")

    plans = list(mongo.db.plans.find({"user_id": str(current_user.id)}))
    for plan in plans:
        plan["_id"] = str(plan["_id"])
    return render_template("plans.html", plans=plans)

@app.route("/delete_plan/<plan_id>", methods=["POST"])
@login_required
def delete_plan(plan_id):
    mongo.db.plans.delete_one({"_id": ObjectId(plan_id), "user_id": str(current_user.id)})
    flash("Plan deleted successfully!", "success")
    return redirect(url_for("plans"))


@app.route("/reports")
@login_required
def reports():
    user_id = str(current_user.id)
    debited_expenses = list(mongo.db.expenses.find({"user_id": user_id, "type": "Debit"}))

    for expense in debited_expenses:
        expense["_id"] = str(expense["_id"])

    monthly_expenses = defaultdict(float)
    yearly_expenses = defaultdict(float)
    category_totals = defaultdict(float)  

    for expense in debited_expenses:
        date_obj = datetime.strptime(expense["date"], "%Y-%m-%d")
        month_year = date_obj.strftime("%B %Y")  # Example: "March 2025"
        year = date_obj.strftime("%Y")  # Example: "2025"
        monthly_expenses[month_year] += expense["amount"]
        yearly_expenses[year] += expense["amount"]
        category_totals[expense["category"]] += expense["amount"]
    total_expense = sum(exp["amount"] for exp in debited_expenses) 

    return render_template(
        "reports.html", 
        expenses=debited_expenses, 
        monthly_expenses=dict(monthly_expenses),  # Convert defaultdict to dict
        yearly_expenses=dict(yearly_expenses),
        total_expense=total_expense,  # Pass the total expense
        category_totals=dict(category_totals)  # Convert defaultdict to dict
    )

@app.route("/delete_expense/<expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    mongo.db.expenses.delete_one({"_id": ObjectId(expense_id)})  
    flash("Expense deleted successfully!", "success")
    return redirect(url_for("manage_expenses"))

@app.route("/get_expenses")
@login_required
def get_expenses():
    user_id = str(current_user.id)
    transactions = list(mongo.db.expenses.find({"user_id": user_id}))

    for transaction in transactions:
        transaction["_id"] = str(transaction["_id"])  # Convert ObjectId to string
        transaction["date"] = transaction["date"]  # Ensure date is correctly formatted

    return jsonify(transactions)


if __name__ == "__main__":
    app.run(debug=True)
