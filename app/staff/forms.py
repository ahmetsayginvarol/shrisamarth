from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, NumberRange


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
            Length(min=7, max=20),
            Regexp(r'^[\d\s\+\-\(\)]+$', message='Phone must contain only digits and + - ( ) spaces')
        ]
    )
    gender = SelectField(
        'Gender',
        choices=[('M', 'Male'), ('F', 'Female')],
        validators=[DataRequired()]
    )

    boarding_point = SelectField(
        'Boarding',
        choices=[('Dadar', 'Dadar'), ('Andheri', 'Andheri'),
                 ('Borivali', 'Borivali'), ('Thane', 'Thane')],
        validators=[DataRequired()]
    )
    dropping_point = SelectField(
        'Dropping',
        choices=[('Shivajinagar', 'Shivajinagar'), ('Swargate', 'Swargate'),
                 ('Katraj', 'Katraj'), ('Hinjewadi', 'Hinjewadi')],
        validators=[DataRequired()]
    )

    fare = DecimalField('Fare', validators=[DataRequired(), NumberRange(min=0)])
    advance_paid = DecimalField('Advance', validators=[NumberRange(min=0)], default=0)

    confirm_gender_conflict = HiddenField('Confirm Gender Conflict', default='no')
    submit = SubmitField('Confirm Booking')