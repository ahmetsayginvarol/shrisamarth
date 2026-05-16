from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class CustomerLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')


class CustomerProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(2, 120)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    current_password = PasswordField('Current Password')
    new_password = PasswordField('New Password', validators=[Optional(), Length(min=6)])
    submit = SubmitField('Save Changes')


class CustomerRegisterForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(2, 120)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('Phone', validators=[DataRequired(), Length(7, 20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create Account')
