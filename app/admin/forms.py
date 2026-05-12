from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, DecimalField
from wtforms import DateTimeLocalField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class BusForm(FlaskForm):
    registration = StringField('Registration Number',
        validators=[DataRequired(), Length(min=3, max=20)])
    name = StringField('Bus Name / Nickname',
        validators=[Optional(), Length(max=80)])
    total_seats = IntegerField('Total Seats',
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        default=49)
    notes = TextAreaField('Notes', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Bus')


class VoyageForm(FlaskForm):
    origin = StringField('Origin',
        validators=[DataRequired(), Length(max=80)])
    destination = StringField('Destination',
        validators=[DataRequired(), Length(max=80)])
    departure_at = DateTimeLocalField('Departure',
        format='%Y-%m-%dT%H:%M',
        validators=[DataRequired()])
    arrival_at = DateTimeLocalField('Estimated Arrival',
        format='%Y-%m-%dT%H:%M',
        validators=[Optional()])
    bus_id = SelectField('Bus', coerce=int, validators=[DataRequired()])
    driver_id = SelectField('Driver', coerce=int, validators=[Optional()])
    base_fare = DecimalField('Base Fare (₹)',
        validators=[DataRequired(), NumberRange(min=0)],
        default=800)
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Voyage')