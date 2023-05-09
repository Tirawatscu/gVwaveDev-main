from flask import Blueprint, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from flask_login import login_user, login_required, logout_user

auth_bp = Blueprint('auth_bp', __name__, template_folder='templates', static_folder='static')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.find_by_username(username)

        if not user or not check_password_hash(user.password, password):
            flash('Please check your login details and try again.')
            return redirect(url_for('auth_bp.login'))

        login_user(user, remember=remember)
        return redirect(url_for('map'))  # Change 'main' to 'map' to redirect to the map view
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth_bp.login'))

@auth_bp.route('/signup')
def signup():
    return render_template('signup.html')

@auth_bp.route('/signup', methods=['POST'])
def signup_post():
    # code to validate and add user to database goes here
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')

    user = User.find_by_email(email)  # if this returns a user, then the email already exists in database

    if user:  # if a user is found, we want to flash a message and redirect back to the signup page so the user can try again
        flash('Email address already exists')
        return redirect(url_for('auth_bp.signup'))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(None, name, email, generate_password_hash(password, method='sha256'))

    # add the new user to the database
    User.add_user(new_user)

    return redirect(url_for('auth_bp.login'))



