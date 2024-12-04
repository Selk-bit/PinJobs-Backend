from django import forms
from django_celery_beat.models import CrontabSchedule


class CrontabScheduleAdminForm(forms.ModelForm):
    # Add a time picker field
    time = forms.TimeField(
        widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        required=False,
        label='Time (HH:MM)',
    )

    class Meta:
        model = CrontabSchedule
        fields = ['time', 'day_of_week', 'day_of_month', 'month_of_year']

    def save(self, commit=True):
        # Parse the time input into hour and minute fields
        time = self.cleaned_data.get('time')
        if time:
            self.instance.hour = time.hour
            self.instance.minute = time.minute
        return super().save(commit=commit)
