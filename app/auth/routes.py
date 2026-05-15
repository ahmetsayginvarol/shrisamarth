from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse

from app.extensions import db
from app.models import User
from app.auth.forms import LoginForm
from app.logging import log_activity

auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('staff.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('auth.login'))

        if not user.is_active_account:
            flash('This account has been disabled.', 'error')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        log_activity('user_login', f'{user.full_name} signed in', 'user', user.id)

        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            if user.role == 'admin':
                next_page = url_for('admin.dashboard')
            else:
                next_page = url_for('staff.dashboard')

        flash(f'Welcome back, {user.full_name}.', 'success')
        return redirect(next_page)

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    log_activity('user_logout', f'{current_user.full_name} signed out', 'user', current_user.id)

    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))