from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, NumberRange, Optional


class BookingForm(FlaskForm):
    seat_id = HiddenField('Seat', validators=[DataRequired()])
    voyage_id = HiddenField('Voyage', validators=[DataRequired()])

    passenger_name = StringField(
        'Passenger Name',
        validators=[DataRequired(), Length(min=2, max=120)]
    )
    passenger_phone = StringField(
        'Contact',
        validators=[
            DataRequired(),
            Length(min=7, max=30),
            Regexp(r'^[\d\s\+\-\(\)]+$', message='Phone must contain only digits and + - ( ) spaces')
        ]
    )
    gender = SelectField(
        'Gender',
        choices=[('M', 'Male'), ('F', 'Female')],
        validators=[DataRequired()]
    )

    # StringField so any stop name from RouteStops passes validation
    boarding_point = StringField('Boarding', validators=[DataRequired(), Length(max=120)])
    dropping_point = StringField('Dropping', validators=[DataRequired(), Length(max=120)])

    fare = DecimalField('Fare', validators=[DataRequired(), NumberRange(min=0)])
    advance_paid = DecimalField('Advance', validators=[Optional(), NumberRange(min=0)], default=0)

    confirm_gender_conflict = HiddenField('Confirm Gender Conflict', default='no')
    submit = SubmitField('Confirm Booking')
